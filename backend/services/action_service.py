"""Create and manage follow-up actions for documents."""
from datetime import datetime
from uuid import UUID
from sqlalchemy.orm import Session

from backend.models import Action, ActionStatus
from backend.schemas import ActionCreate, ActionUpdate
from backend.services.audit_service import log_event


def create_actions_from_suggestions(
    db: Session,
    document_id: UUID,
    suggestions: list[dict],
) -> list[Action]:
    """
    Persist a list of LLM-suggested actions for a document.

    Args:
        db: Database session.
        document_id: Parent document UUID.
        suggestions: List of dicts with keys action_type, description, due_date.

    Returns:
        List of created Action ORM objects.
    """
    created = []
    for suggestion in suggestions:
        due_date = None
        raw_due = suggestion.get("due_date")
        if raw_due:
            try:
                due_date = datetime.fromisoformat(raw_due)
            except ValueError:
                pass

        action = Action(
            document_id=document_id,
            action_type=suggestion.get("action_type", "unknown"),
            description=suggestion.get("description"),
            due_date=due_date,
            status=ActionStatus.PENDING,
        )
        db.add(action)
        created.append(action)

    db.commit()
    for action in created:
        db.refresh(action)

    log_event(
        db,
        event_type="actions_created",
        description=f"{len(created)} action(s) created for document {document_id}",
        document_id=document_id,
    )
    return created


def get_actions_for_document(db: Session, document_id: UUID) -> list[Action]:
    return db.query(Action).filter(Action.document_id == document_id).all()


def update_action_status(
    db: Session, action_id: UUID, update: ActionUpdate
) -> Action | None:
    action = db.query(Action).filter(Action.id == action_id).first()
    if not action:
        return None
    action.status = update.status
    db.commit()
    db.refresh(action)
    return action


def get_pending_actions_count(db: Session) -> int:
    return (
        db.query(Action)
        .filter(Action.status == ActionStatus.PENDING)
        .count()
    )
