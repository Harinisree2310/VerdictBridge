"""
Dashboard endpoints.

Provides:
  - Department-scoped document list with filters
  - Statistics (counts by status, alert levels, pending actions)
  - Audit log chain verification
  - Serve uploaded files (for PDF viewer)
"""
from __future__ import annotations
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user, require_role
from models import ActionPlan, AlertLevel, Document, DocumentStatus, User, UserRole
from schemas import AuditLogRead, DashboardStats, DocumentList, DocumentRead
from services.audit_service import get_recent_logs, verify_chain

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _base_query(db: Session, current_user: User):
    """Return a Document query scoped to the user's department (unless admin)."""
    q = db.query(Document)
    if current_user.role != UserRole.ADMIN:
        q = q.filter(Document.department == current_user.department)
    return q


@router.get("/stats", response_model=DashboardStats)
def get_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return dashboard statistics scoped to the user's department."""
    q = _base_query(db, current_user)
    total = q.count()

    by_status = {s.value: q.filter(Document.status == s).count() for s in DocumentStatus}

    # Pending actions = approved documents whose action plan is still pending
    pending_actions = (
        db.query(ActionPlan)
        .join(Document)
        .filter(
            ActionPlan.is_approved == True,
            ActionPlan.status == "pending",
        )
        .count()
    )

    red_alert = (
        db.query(ActionPlan)
        .join(Document)
        .filter(ActionPlan.alert_level == AlertLevel.RED)
        .count()
    )
    warning_alert = (
        db.query(ActionPlan)
        .join(Document)
        .filter(ActionPlan.alert_level == AlertLevel.WARNING)
        .count()
    )

    recent = q.order_by(Document.uploaded_at.desc()).limit(5).all()

    return DashboardStats(
        total_documents=total,
        by_status=by_status,
        pending_actions=pending_actions,
        red_alert_count=red_alert,
        warning_alert_count=warning_alert,
        recent_documents=recent,
    )


@router.get("/documents", response_model=DocumentList)
def list_documents(
    doc_status: DocumentStatus | None = Query(default=None, alias="status"),
    alert: AlertLevel | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List documents with optional status/alert filters and pagination."""
    q = _base_query(db, current_user)

    if doc_status:
        q = q.filter(Document.status == doc_status)

    if alert:
        q = q.join(ActionPlan).filter(ActionPlan.alert_level == alert)

    total = q.count()
    items = q.order_by(Document.uploaded_at.desc()).offset(skip).limit(limit).all()
    return DocumentList(total=total, items=items)


@router.get("/documents/{document_id}", response_model=DocumentRead)
def get_document(
    document_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve a single document by ID."""
    q = _base_query(db, current_user)
    document = q.filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found.")
    return document


@router.get("/audit-logs", response_model=list[AuditLogRead])
def get_audit_logs(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return recent audit log entries."""
    return get_recent_logs(db, limit=limit)


@router.get("/audit-chain/verify")
def verify_audit_chain(
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
):
    """
    Verify the integrity of the SHA-256 chained audit log.
    Admin only. Returns whether the chain is intact and any detected tampering.
    """
    is_valid, errors = verify_chain(db)
    return {
        "chain_valid": is_valid,
        "errors": errors,
        "message": "Audit chain is intact." if is_valid else f"{len(errors)} integrity error(s) detected.",
    }


@router.get("/files/{filename}")
def serve_file(
    filename: str,
    current_user: User = Depends(get_current_user),
):
    """
    Serve an uploaded document file for the in-browser PDF viewer.
    Validates that the filename doesn't contain path traversal sequences.
    """
    # Security: prevent path traversal
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename.")

    from backend.config import get_settings
    settings = get_settings()
    file_path = Path(settings.upload_dir) / filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found.")

    return FileResponse(
        path=str(file_path),
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename={filename}"},
    )
