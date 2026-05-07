"""
VerdictBridge – Pydantic v2 request/response schemas.
"""
from __future__ import annotations
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from backend.models import (
    ActionStatus, ActionType, AlertLevel,
    DocumentStatus, LLMProvider, UserRole,
)


# ── Auth ───────────────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    email: EmailStr
    full_name: str
    password: str
    department: str
    role: UserRole = UserRole.OFFICER


class UserRead(BaseModel):
    id: UUID
    email: str
    full_name: str
    department: str
    role: UserRole
    is_active: bool
    created_at: datetime
    model_config = {"from_attributes": True}


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    user_id: Optional[UUID] = None
    department: Optional[str] = None
    role: Optional[UserRole] = None


# ── Documents ──────────────────────────────────────────────────────────────────

class DocumentRead(BaseModel):
    id: UUID
    filename: str                           # disk name (UUID-prefixed) — used for file serving
    original_filename: str
    file_size_kb: Optional[int] = None
    page_count: Optional[int] = None
    status: DocumentStatus
    department: Optional[str] = None
    llm_provider_used: Optional[LLMProvider] = None
    extraction_error: Optional[str] = None
    celery_task_id: Optional[str] = None
    uploaded_at: datetime
    updated_at: Optional[datetime] = None
    model_config = {"from_attributes": True}


class DocumentList(BaseModel):
    total: int
    items: list[DocumentRead]


# ── Extracted Fields ───────────────────────────────────────────────────────────

class ExtractedFieldRead(BaseModel):
    id: UUID
    document_id: UUID
    field_name: str
    field_value: Optional[str] = None
    original_value: Optional[str] = None
    confidence: Optional[str] = None
    is_flagged: bool
    is_edited: bool
    is_approved: bool
    source_page: Optional[int] = None
    source_text: Optional[str] = None
    bbox_x0: Optional[str] = None
    bbox_y0: Optional[str] = None
    bbox_x1: Optional[str] = None
    bbox_y1: Optional[str] = None
    model_config = {"from_attributes": True}


class ExtractedFieldUpdate(BaseModel):
    field_value: str


# ── Action Plan ────────────────────────────────────────────────────────────────

class ActionPlanRead(BaseModel):
    id: UUID
    document_id: UUID
    recommended_action: ActionType
    action_description: Optional[str] = None
    responsible_dept: Optional[str] = None
    limitation_deadline: Optional[datetime] = None
    deadline_basis: Optional[str] = None
    alert_level: AlertLevel
    status: ActionStatus
    llm_reasoning: Optional[str] = None
    is_approved: bool
    approved_at: Optional[datetime] = None
    created_at: datetime
    model_config = {"from_attributes": True}


class ActionPlanUpdate(BaseModel):
    recommended_action: Optional[ActionType] = None
    action_description: Optional[str] = None
    responsible_dept: Optional[str] = None
    status: Optional[ActionStatus] = None


# ── Audit Log ──────────────────────────────────────────────────────────────────

class AuditLogRead(BaseModel):
    id: UUID
    document_id: Optional[UUID] = None
    event_type: str
    description: Optional[str] = None
    actor_label: str
    metadata_json: Optional[dict[str, Any]] = None
    entry_hash: Optional[str] = None
    prev_hash: Optional[str] = None
    created_at: datetime
    model_config = {"from_attributes": True}


# ── Full extraction result ─────────────────────────────────────────────────────

class ExtractionResult(BaseModel):
    document_id: UUID
    status: DocumentStatus
    llm_provider_used: Optional[LLMProvider] = None
    fields: list[ExtractedFieldRead]
    action_plan: Optional[ActionPlanRead] = None
    flagged_count: int = 0


# ── Dashboard ──────────────────────────────────────────────────────────────────

class DashboardStats(BaseModel):
    total_documents: int
    by_status: dict[str, int]
    pending_actions: int
    red_alert_count: int
    warning_alert_count: int
    recent_documents: list[DocumentRead]


# ── Task status (Celery) ───────────────────────────────────────────────────────

class TaskStatus(BaseModel):
    task_id: str
    state: str                          # PENDING / STARTED / SUCCESS / FAILURE
    document_id: Optional[UUID] = None
    progress: Optional[str] = None
    error: Optional[str] = None
