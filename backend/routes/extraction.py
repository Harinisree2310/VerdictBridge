"""
Extraction status and result endpoints.

GET  /extraction/{document_id}        → full extraction result (fields + action plan)
POST /extraction/{document_id}/retry  → re-queue extraction
GET  /tasks/{task_id}                 → Celery task status
"""
from __future__ import annotations
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.dependencies import get_current_user, get_document_for_user
from backend.models import Document, DocumentStatus, User
from backend.schemas import ExtractionResult, TaskStatus

router = APIRouter(tags=["extraction"])


@router.get("/extraction/{document_id}", response_model=ExtractionResult)
def get_extraction_result(
    document: Document = Depends(get_document_for_user),
    db: Session = Depends(get_db),
):
    """
    Return the full extraction result for a document.
    Includes all extracted fields (with source highlighting data) and the action plan.
    """
    flagged = sum(1 for f in document.extracted_fields if f.is_flagged)
    return ExtractionResult(
        document_id=document.id,
        status=document.status,
        llm_provider_used=document.llm_provider_used,
        fields=document.extracted_fields,
        action_plan=document.action_plan,
        flagged_count=flagged,
    )


@router.post("/extraction/{document_id}/retry", response_model=dict)
def retry_extraction(
    document: Document = Depends(get_document_for_user),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Re-run extraction synchronously (no Celery needed)."""
    if document.status == DocumentStatus.PROCESSING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Extraction is already in progress.",
        )

    from backend.tasks import _run_pipeline
    from backend.services.audit_service import log_event

    try:
        result = _run_pipeline(str(document.id), db)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    db.refresh(document)

    log_event(
        db,
        event_type="extraction_retried",
        description=f"Extraction re-run for document {document.id}",
        document_id=document.id,
        actor_id=current_user.id,
        actor_label=current_user.full_name,
    )

    return {
        "status": "success",
        "document_id": str(document.id),
        "document_status": document.status.value,
        **result,
    }


@router.get("/tasks/{task_id}", response_model=TaskStatus)
def get_task_status(task_id: str):
    """Poll the status of an async Celery extraction task."""
    from backend.worker import celery_app
    result = celery_app.AsyncResult(task_id)

    state = result.state
    meta = result.info or {}

    if state == "FAILURE":
        return TaskStatus(
            task_id=task_id,
            state=state,
            error=str(meta) if not isinstance(meta, dict) else meta.get("exc_message", str(meta)),
        )

    return TaskStatus(
        task_id=task_id,
        state=state,
        document_id=meta.get("document_id") if isinstance(meta, dict) else None,
        progress=meta.get("progress") if isinstance(meta, dict) else None,
    )
