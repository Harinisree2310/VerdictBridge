"""
Human review endpoints.

Officers can:
  - View extracted fields with source highlighting coordinates
  - Edit individual field values (original preserved)
  - Approve / reject individual fields
  - Update action plan details
  - Approve or reject the full document
  - View audit trail

Every action is logged to the tamper-evident audit log.
"""
from __future__ import annotations
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.dependencies import get_current_user, get_document_for_user, require_role
from backend.models import (
    ActionPlan, Document, DocumentStatus,
    ExtractedField, User, UserRole,
)
from backend.schemas import (
    ActionPlanRead, ActionPlanUpdate,
    DocumentRead, ExtractedFieldRead, ExtractedFieldUpdate,
)
from backend.services.audit_service import log_event, get_logs_for_document
from backend.schemas import AuditLogRead


class _ActionItem(ActionPlanRead):
    """ActionPlan surfaced as a list item for the review UI."""
    # Aliases the action plan fields to names the frontend already uses
    description: str | None = None
    action_type: str | None = None
    due_date: str | None = None

    model_config = {"from_attributes": True}

    @classmethod
    def from_plan(cls, plan: "ActionPlan") -> "_ActionItem":
        obj = cls.model_validate(plan)
        obj.description = plan.action_description
        obj.action_type = plan.recommended_action.value if plan.recommended_action else None
        obj.due_date = (
            plan.limitation_deadline.isoformat() if plan.limitation_deadline else None
        )
        return obj

router = APIRouter(prefix="/review", tags=["review"])


# ── Fields ─────────────────────────────────────────────────────────────────────

@router.get("/{document_id}/fields", response_model=list[ExtractedFieldRead])
def list_fields(
    document: Document = Depends(get_document_for_user),
):
    """Return all extracted fields for a document, sorted by field name."""
    return sorted(document.extracted_fields, key=lambda f: f.field_name)


@router.patch("/{document_id}/fields/{field_id}", response_model=ExtractedFieldRead)
def update_field(
    field_id: UUID,
    update: ExtractedFieldUpdate,
    document: Document = Depends(get_document_for_user),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Edit an extracted field value.

    - Preserves the original LLM-extracted value in original_value on first edit.
    - Marks the field as edited and clears the flagged status.
    - Logs the change with old and new values.
    """
    field = (
        db.query(ExtractedField)
        .filter(ExtractedField.id == field_id, ExtractedField.document_id == document.id)
        .first()
    )
    if not field:
        raise HTTPException(status_code=404, detail="Field not found.")

    old_value = field.field_value

    if not field.is_edited:
        field.original_value = field.field_value

    field.field_value = update.field_value
    field.is_edited = True
    field.is_flagged = False   # human edit clears the flag
    db.commit()
    db.refresh(field)

    log_event(
        db,
        event_type="field_edited",
        description=f"Field '{field.field_name}' edited on document {document.id}",
        document_id=document.id,
        actor_id=current_user.id,
        actor_label=current_user.full_name,
        metadata={
            "field_id": str(field_id),
            "field_name": field.field_name,
            "old_value": old_value,
            "new_value": update.field_value,
        },
    )
    return field


@router.post("/{document_id}/fields/{field_id}/approve", response_model=ExtractedFieldRead)
def approve_field(
    field_id: UUID,
    document: Document = Depends(get_document_for_user),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark a single extracted field as approved by the reviewer."""
    field = (
        db.query(ExtractedField)
        .filter(ExtractedField.id == field_id, ExtractedField.document_id == document.id)
        .first()
    )
    if not field:
        raise HTTPException(status_code=404, detail="Field not found.")

    field.is_approved = True
    field.is_flagged = False
    db.commit()
    db.refresh(field)

    log_event(
        db,
        event_type="field_approved",
        description=f"Field '{field.field_name}' approved",
        document_id=document.id,
        actor_id=current_user.id,
        actor_label=current_user.full_name,
    )
    return field


# ── Actions list (frontend list contract) ─────────────────────────────────────

@router.get("/{document_id}/actions", response_model=list[_ActionItem])
def list_actions(document: Document = Depends(get_document_for_user)):
    """
    Return the action plan as a single-item list.
    The frontend ReviewPage expects a list of action objects; we adapt the
    single ActionPlan record into that shape here without a schema migration.
    """
    if not document.action_plan:
        return []
    return [_ActionItem.from_plan(document.action_plan)]


@router.patch("/{document_id}/actions/{action_id}", response_model=_ActionItem)
def update_action_status(
    action_id: UUID,
    update: ActionPlanUpdate,
    document: Document = Depends(get_document_for_user),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Update the status (or other fields) of an action.
    ``action_id`` must match the document's action plan id.
    """
    plan = document.action_plan
    if not plan or str(plan.id) != str(action_id):
        raise HTTPException(status_code=404, detail="Action not found.")

    changes: dict = {}
    if update.status is not None:
        changes["status"] = update.status.value
        plan.status = update.status
    if update.recommended_action is not None:
        changes["recommended_action"] = update.recommended_action.value
        plan.recommended_action = update.recommended_action
    if update.action_description is not None:
        changes["action_description"] = update.action_description
        plan.action_description = update.action_description
    if update.responsible_dept is not None:
        changes["responsible_dept"] = update.responsible_dept
        plan.responsible_dept = update.responsible_dept

    db.commit()
    db.refresh(plan)

    log_event(
        db,
        event_type="action_updated",
        description=f"Action status updated on document {document.id}",
        document_id=document.id,
        actor_id=current_user.id,
        actor_label=current_user.full_name,
        metadata=changes,
    )
    return _ActionItem.from_plan(plan)


# ── Action Plan ────────────────────────────────────────────────────────────────

@router.get("/{document_id}/action-plan", response_model=ActionPlanRead)
def get_action_plan(document: Document = Depends(get_document_for_user)):
    """Return the AI-generated action plan for a document."""
    if not document.action_plan:
        raise HTTPException(status_code=404, detail="Action plan not yet generated.")
    return document.action_plan


@router.patch("/{document_id}/action-plan", response_model=ActionPlanRead)
def update_action_plan(
    update: ActionPlanUpdate,
    document: Document = Depends(get_document_for_user),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Allow a reviewer to modify the action plan before approval."""
    plan = document.action_plan
    if not plan:
        raise HTTPException(status_code=404, detail="Action plan not found.")

    changes: dict = {}
    if update.recommended_action is not None:
        changes["recommended_action"] = update.recommended_action.value
        plan.recommended_action = update.recommended_action
    if update.action_description is not None:
        changes["action_description"] = update.action_description
        plan.action_description = update.action_description
    if update.responsible_dept is not None:
        changes["responsible_dept"] = update.responsible_dept
        plan.responsible_dept = update.responsible_dept
    if update.status is not None:
        changes["status"] = update.status.value
        plan.status = update.status

    db.commit()
    db.refresh(plan)

    log_event(
        db,
        event_type="action_plan_updated",
        description=f"Action plan updated on document {document.id}",
        document_id=document.id,
        actor_id=current_user.id,
        actor_label=current_user.full_name,
        metadata=changes,
    )
    return plan


# ── Document approval / rejection ──────────────────────────────────────────────

@router.post("/{document_id}/approve", response_model=DocumentRead)
def approve_document(
    document: Document = Depends(get_document_for_user),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.REVIEWER, UserRole.ADMIN)),
):
    """
    Approve a document after human review.
    Only REVIEWER and ADMIN roles can approve.
    Marks the action plan as approved and promotes the document to the dashboard.
    """
    if document.status in (DocumentStatus.APPROVED, DocumentStatus.REJECTED):
        raise HTTPException(
            status_code=409,
            detail=f"Document is already '{document.status}' and cannot be approved again.",
        )

    document.status = DocumentStatus.APPROVED
    if document.action_plan:
        document.action_plan.is_approved = True
        document.action_plan.approved_by = current_user.id
        document.action_plan.approved_at = __import__("datetime").datetime.utcnow()
    db.commit()
    db.refresh(document)

    log_event(
        db,
        event_type="document_approved",
        description=f"Document '{document.original_filename}' approved",
        document_id=document.id,
        actor_id=current_user.id,
        actor_label=current_user.full_name,
    )
    return document


@router.post("/{document_id}/reject", response_model=DocumentRead)
def reject_document(
    document: Document = Depends(get_document_for_user),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.REVIEWER, UserRole.ADMIN)),
):
    """Reject a document — it will not appear in the action dashboard."""
    document.status = DocumentStatus.REJECTED
    db.commit()
    db.refresh(document)

    log_event(
        db,
        event_type="document_rejected",
        description=f"Document '{document.original_filename}' rejected",
        document_id=document.id,
        actor_id=current_user.id,
        actor_label=current_user.full_name,
    )
    return document


# ── Audit trail ────────────────────────────────────────────────────────────────

@router.get("/{document_id}/audit", response_model=list[AuditLogRead])
def get_audit_trail(
    document: Document = Depends(get_document_for_user),
    db: Session = Depends(get_db),
):
    """Return the full audit trail for a document."""
    return get_logs_for_document(db, document.id)
