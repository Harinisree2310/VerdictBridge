"""
VerdictBridge – Tamper-evident audit log service.

Every audit entry is SHA-256 chained to the previous entry, making
retrospective tampering cryptographically detectable.

Chain structure:
  entry_hash = SHA256(prev_hash + event_type + description + timestamp + actor_id)

The first entry in the chain has prev_hash = "GENESIS".
"""
from __future__ import annotations
import hashlib
import json
import logging
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.models import AuditLog

logger = logging.getLogger(__name__)
settings = get_settings()

GENESIS_HASH = "GENESIS"


def _compute_hash(
    prev_hash: str,
    event_type: str,
    description: str,
    created_at: datetime,
    actor_id,
) -> str:
    """Compute SHA-256 hash of an audit entry.
    Uses isoformat truncated to seconds for cross-DB consistency.
    """
    # Truncate to seconds to avoid microsecond precision differences across DBs
    ts = created_at.replace(microsecond=0).isoformat()
    payload = f"{prev_hash}|{event_type}|{description}|{ts}|{actor_id}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _get_next_seq(db: Session) -> int:
    """Get the next sequence number for the audit chain."""
    from sqlalchemy import func
    result = db.query(func.max(AuditLog.seq)).scalar()
    return (result or 0) + 1


def _get_last_hash(db: Session) -> str:
    """Retrieve the hash of the most recent audit log entry (by sequence)."""
    last = db.query(AuditLog).order_by(AuditLog.seq.desc()).first()
    return last.entry_hash if last and last.entry_hash else GENESIS_HASH


def log_event(
    db: Session,
    event_type: str,
    description: str | None = None,
    document_id: UUID | None = None,
    actor_id: UUID | None = None,
    actor_label: str = "system",
    metadata: dict[str, Any] | None = None,
) -> AuditLog:
    """
    Create a tamper-evident audit log entry.

    Args:
        db: Database session.
        event_type: Short identifier (e.g. "document_uploaded", "field_edited").
        description: Human-readable description.
        document_id: Associated document UUID.
        actor_id: User UUID who triggered the event.
        actor_label: Fallback display name if actor_id is None.
        metadata: Extra JSON data.

    Returns:
        The persisted AuditLog instance.
    """
    created_at = datetime.utcnow().replace(microsecond=0)  # truncate for hash consistency

    if settings.audit_chain_enabled:
        prev_hash = _get_last_hash(db)
        entry_hash = _compute_hash(prev_hash, event_type, description or "", created_at, actor_id)
    else:
        prev_hash = None
        entry_hash = None

    seq = _get_next_seq(db)

    entry = AuditLog(
        seq=seq,
        document_id=document_id,
        event_type=event_type,
        description=description,
        actor_id=actor_id,
        actor_label=actor_label,
        metadata_json=metadata or {},
        entry_hash=entry_hash,
        prev_hash=prev_hash,
        created_at=created_at,   # already truncated to seconds
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def verify_chain(db: Session) -> tuple[bool, list[str]]:
    """
    Verify the integrity of the entire audit log chain.

    Returns:
        (is_valid, list_of_errors)
    """
    if not settings.audit_chain_enabled:
        return True, ["Chain verification disabled in config."]

    entries = (
        db.query(AuditLog)
        .order_by(AuditLog.seq.asc())
        .all()
    )
    if not entries:
        return True, []

    errors: list[str] = []
    expected_prev = GENESIS_HASH

    for entry in entries:
        if entry.prev_hash != expected_prev:
            errors.append(
                f"Entry {entry.id} prev_hash mismatch: expected {expected_prev}, got {entry.prev_hash}"
            )

        computed = _compute_hash(
            entry.prev_hash or GENESIS_HASH,
            entry.event_type,
            entry.description or "",
            entry.created_at,   # _compute_hash already truncates microseconds
            entry.actor_id,
        )
        if entry.entry_hash != computed:
            errors.append(
                f"Entry {entry.id} hash mismatch: expected {computed}, got {entry.entry_hash}"
            )

        expected_prev = entry.entry_hash

    return len(errors) == 0, errors


def get_logs_for_document(db: Session, document_id: UUID, limit: int = 100) -> list[AuditLog]:
    return (
        db.query(AuditLog)
        .filter(AuditLog.document_id == document_id)
        .order_by(AuditLog.seq.desc())
        .limit(limit)
        .all()
    )


def get_recent_logs(db: Session, limit: int = 50) -> list[AuditLog]:
    return (
        db.query(AuditLog)
        .order_by(AuditLog.seq.desc())
        .limit(limit)
        .all()
    )
