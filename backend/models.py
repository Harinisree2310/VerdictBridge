"""
VerdictBridge – SQLAlchemy ORM models.

Key design decisions:
- UUIDs as primary keys stored as CHAR(36) strings — works with SQLite AND PostgreSQL
- AuditLog uses SHA-256 chaining for tamper-evidence
- ExtractedField stores PDF bounding-box coordinates for source highlighting
- All timestamps are UTC
"""
import uuid
import enum
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Enum as SAEnum,
    ForeignKey, Integer, JSON, String, Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.types import TypeDecorator, CHAR


class UUIDType(TypeDecorator):
    """
    Cross-database UUID column.
    Stored as CHAR(36) string — compatible with SQLite and PostgreSQL.
    Python-side values are always uuid.UUID objects.
    """
    impl = CHAR(36)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return uuid.UUID(str(value))


def _new_uuid():
    return uuid.uuid4()


from backend.database import Base


# ── Enumerations ───────────────────────────────────────────────────────────────

class DocumentStatus(str, enum.Enum):
    UPLOADED    = "uploaded"
    QUEUED      = "queued"
    PROCESSING  = "processing"
    EXTRACTED   = "extracted"
    REVIEWING   = "reviewing"
    APPROVED    = "approved"
    REJECTED    = "rejected"
    FAILED      = "failed"


class ActionType(str, enum.Enum):
    COMPLY             = "comply"
    CONSIDER_APPEAL    = "consider_appeal"
    FILE_APPEAL        = "file_appeal"
    SEEK_CLARIFICATION = "seek_clarification"
    NO_ACTION          = "no_action"


class ActionStatus(str, enum.Enum):
    PENDING   = "pending"
    COMPLETED = "completed"
    SKIPPED   = "skipped"
    OVERDUE   = "overdue"


class AlertLevel(str, enum.Enum):
    NORMAL  = "normal"
    WARNING = "warning"
    RED     = "red"


class UserRole(str, enum.Enum):
    OFFICER  = "officer"
    REVIEWER = "reviewer"
    ADMIN    = "admin"


class LLMProvider(str, enum.Enum):
    CLAUDE = "claude"
    GEMINI = "gemini"
    OPENAI = "openai"
    MOCK   = "mock"


# ── Users ──────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id              = Column(UUIDType, primary_key=True, default=_new_uuid)
    email           = Column(String(255), unique=True, nullable=False, index=True)
    full_name       = Column(String(255), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    department      = Column(String(255), nullable=False)
    role            = Column(SAEnum(UserRole), default=UserRole.OFFICER, nullable=False)
    is_active       = Column(Boolean, default=True)
    created_at      = Column(DateTime, default=datetime.utcnow, nullable=False)

    documents  = relationship("Document", back_populates="uploaded_by_user")
    audit_logs = relationship("AuditLog", back_populates="actor_user")


# ── Documents ──────────────────────────────────────────────────────────────────

class Document(Base):
    __tablename__ = "documents"

    id                = Column(UUIDType, primary_key=True, default=_new_uuid)
    filename          = Column(String(512), nullable=False)
    original_filename = Column(String(512), nullable=False)
    file_path         = Column(String(1024), nullable=False)
    file_size_kb      = Column(Integer)
    mime_type         = Column(String(100))
    page_count        = Column(Integer)
    status            = Column(SAEnum(DocumentStatus), default=DocumentStatus.UPLOADED, nullable=False)
    department        = Column(String(255))
    celery_task_id    = Column(String(255))
    llm_provider_used = Column(SAEnum(LLMProvider))
    extraction_error  = Column(Text)
    uploaded_by       = Column(UUIDType, ForeignKey("users.id"), nullable=True)
    uploaded_at       = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at        = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    uploaded_by_user = relationship("User", back_populates="documents")
    extracted_fields = relationship("ExtractedField", back_populates="document",
                                    cascade="all, delete-orphan")
    action_plan      = relationship("ActionPlan", back_populates="document",
                                    uselist=False, cascade="all, delete-orphan")
    audit_logs       = relationship("AuditLog", back_populates="document",
                                    cascade="all, delete-orphan")


# ── Extracted Fields ───────────────────────────────────────────────────────────

class ExtractedField(Base):
    """
    One extracted field from a judgment.
    bbox_* columns store the PDF bounding box of the source passage
    so the frontend can scroll-to and highlight it.
    """
    __tablename__ = "extracted_fields"

    id             = Column(UUIDType, primary_key=True, default=_new_uuid)
    document_id    = Column(UUIDType, ForeignKey("documents.id"), nullable=False)
    field_name     = Column(String(100), nullable=False)
    field_value    = Column(Text)
    original_value = Column(Text)
    confidence     = Column(String(10))
    is_flagged     = Column(Boolean, default=False)
    is_edited      = Column(Boolean, default=False)
    is_approved    = Column(Boolean, default=False)

    # Source highlighting — PDF page + bounding box
    source_page = Column(Integer)
    source_text = Column(Text)
    bbox_x0     = Column(String(20))
    bbox_y0     = Column(String(20))
    bbox_x1     = Column(String(20))
    bbox_y1     = Column(String(20))

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    document = relationship("Document", back_populates="extracted_fields")


# ── Action Plan ────────────────────────────────────────────────────────────────

class ActionPlan(Base):
    """AI-generated action plan — one per document."""
    __tablename__ = "action_plans"

    id                  = Column(UUIDType, primary_key=True, default=_new_uuid)
    document_id         = Column(UUIDType, ForeignKey("documents.id"), nullable=False, unique=True)
    recommended_action  = Column(SAEnum(ActionType), nullable=False)
    action_description  = Column(Text)
    responsible_dept    = Column(String(255))
    limitation_deadline = Column(DateTime)
    deadline_basis      = Column(Text)
    alert_level         = Column(SAEnum(AlertLevel), default=AlertLevel.NORMAL)
    status              = Column(SAEnum(ActionStatus), default=ActionStatus.PENDING)
    llm_reasoning       = Column(Text)
    is_approved         = Column(Boolean, default=False)
    approved_by         = Column(UUIDType, ForeignKey("users.id"), nullable=True)
    approved_at         = Column(DateTime)
    created_at          = Column(DateTime, default=datetime.utcnow)
    updated_at          = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    document         = relationship("Document", back_populates="action_plan")
    approved_by_user = relationship("User", foreign_keys=[approved_by])


# ── Audit Log (SHA-256 chained) ────────────────────────────────────────────────

class AuditLog(Base):
    """
    Tamper-evident append-only audit log.
    Each entry stores a SHA-256 hash of (previous_hash + this_entry_content).
    Retrospective tampering is detectable by re-computing the chain.
    """
    __tablename__ = "audit_logs"

    id            = Column(UUIDType, primary_key=True, default=_new_uuid)
    seq           = Column(Integer, nullable=True)
    document_id   = Column(UUIDType, ForeignKey("documents.id"), nullable=True)
    event_type    = Column(String(100), nullable=False)
    description   = Column(Text)
    actor_id      = Column(UUIDType, ForeignKey("users.id"), nullable=True)
    actor_label   = Column(String(100), default="system")
    metadata_json = Column(JSON, default=dict)
    entry_hash    = Column(String(64))
    prev_hash     = Column(String(64))
    created_at    = Column(DateTime, default=datetime.utcnow, nullable=False)

    document   = relationship("Document", back_populates="audit_logs")
    actor_user = relationship("User", back_populates="audit_logs")
