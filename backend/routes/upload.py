"""
Document upload endpoint.

Accepts PDF / image files, saves to disk, creates DB record,
and enqueues the async extraction pipeline via Celery.
"""
from __future__ import annotations
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.database import get_db
from backend.dependencies import get_current_user
from backend.models import Document, DocumentStatus, User
from backend.schemas import DocumentRead
from backend.services.audit_service import log_event
from backend.services.pdf_service import get_page_count

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/upload", tags=["upload"])
settings = get_settings()

ALLOWED_MIME = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/tiff",
    "image/tif",
}
MAX_BYTES = settings.max_upload_size_mb * 1024 * 1024


@router.post("/", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Upload a court judgment PDF or scanned image.

    - Validates MIME type and file size.
    - Saves to the configured upload directory.
    - Creates a Document record with status=QUEUED.
    - Enqueues the async extraction pipeline.
    - Returns the document record immediately (poll /tasks/{task_id} for progress).
    """
    if file.content_type not in ALLOWED_MIME:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type '{file.content_type}'. Allowed: PDF, PNG, JPEG, TIFF.",
        )

    contents = await file.read()
    if len(contents) > MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {settings.max_upload_size_mb} MB limit.",
        )

    # Save to disk
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = f"{uuid.uuid4().hex}_{Path(file.filename).name}"
    file_path = upload_dir / safe_name

    with open(file_path, "wb") as f:
        f.write(contents)

    # Quick page count for PDFs (non-blocking)
    page_count = None
    if file.content_type == "application/pdf":
        try:
            page_count = get_page_count(str(file_path))
        except Exception:
            pass

    # Create DB record
    document = Document(
        filename=safe_name,
        original_filename=file.filename,
        file_path=str(file_path),
        file_size_kb=len(contents) // 1024,
        mime_type=file.content_type,
        page_count=page_count,
        status=DocumentStatus.QUEUED,
        department=current_user.department,
        uploaded_by=current_user.id,
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    # Run extraction synchronously (no Redis/Celery required).
    # _run_pipeline is a plain function — no broker connection needed.
    try:
        from backend.tasks import _run_pipeline
        _run_pipeline(str(document.id), db)
    except Exception as e:
        logger.error("Extraction failed: %s", e)
        document.status = DocumentStatus.FAILED
        db.commit()

    # Refresh so the returned object reflects the status the pipeline committed
    # (EXTRACTED on success, FAILED on error) rather than the pre-pipeline QUEUED state.
    db.refresh(document)

    log_event(
        db,
        event_type="document_uploaded",
        description=f"'{file.filename}' uploaded ({len(contents)//1024} KB, {page_count or '?'} pages)",
        document_id=document.id,
        actor_id=current_user.id,
        actor_label=current_user.full_name,
    )

    logger.info("Document %s extraction complete", document.id)
    return document
