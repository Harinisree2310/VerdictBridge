"""
VerdictBridge – Celery async tasks.

The main extraction pipeline runs as a Celery task so that:
  - Large PDFs don't block the HTTP request
  - Progress can be polled via /api/v1/tasks/{task_id}
  - Failures are retried automatically

Pipeline stages:
  1. Load PDF → extract text (PyMuPDF)
  2. OCR fallback if text is sparse (Tesseract)
  3. PII masking before LLM call
  4. LLM field extraction (Claude → Gemini → GPT-4o → Mock)
  5. Source passage location (bounding box per field)
  6. Action plan generation (second LLM pass)
  7. Deadline calculation
  8. Persist results to DB
  9. Audit log entry
"""
from __future__ import annotations
import logging
from datetime import datetime
from uuid import UUID

from celery import Task
from sqlalchemy.orm import Session

from backend.worker import celery_app
from backend.database import SessionLocal as _make_session
from backend.models import (
    ActionPlan, Document, DocumentStatus,
    ExtractedField, LLMProvider,
)
from backend.services import pdf_service, ocr_service, llm_service
from backend.services.pii_service import mask_pii
from backend.services.audit_service import log_event
from backend.utils.deadline_calculator import compute_deadline, compute_alert_level

logger = logging.getLogger(__name__)

CONFIDENCE_FLAG_THRESHOLD = 0.70


class ExtractionTask(Task):
    """Base task class with DB session management."""
    _db: Session | None = None

    @property
    def db(self) -> Session:
        if self._db is None:
            self._db = _make_session()
        return self._db

    def after_return(self, *args, **kwargs):
        if self._db is not None:
            self._db.close()
            self._db = None


@celery_app.task(
    bind=True,
    base=ExtractionTask,
    name="backend.tasks.run_extraction_pipeline",
    max_retries=2,
    default_retry_delay=30,
    soft_time_limit=300,   # 5 min soft limit
    time_limit=360,        # 6 min hard limit
)
def run_extraction_pipeline(self: ExtractionTask, document_id: str) -> dict:
    """
    Full extraction pipeline for a single document (Celery entry point).
    Delegates to _run_pipeline which can also be called synchronously.
    """
    try:
        return _run_pipeline(document_id, self.db)
    except Exception as exc:
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        raise


def _run_pipeline(document_id: str, db: Session) -> dict:
    """
    Core extraction pipeline — no Celery dependency.
    Called directly by upload.py for synchronous execution (no Redis needed),
    and also by the Celery task for async background execution.

    Args:
        document_id: UUID string of the Document record.
        db: Active SQLAlchemy session.

    Returns:
        {"status": "success", "document_id": ..., "field_count": ..., "provider": ...}
    """
    doc_uuid = UUID(document_id)

    # ── Load document ──────────────────────────────────────────────────────────
    document = db.query(Document).filter(Document.id == doc_uuid).first()
    if not document:
        raise ValueError(f"Document {document_id} not found.")

    document.status = DocumentStatus.PROCESSING
    db.commit()

    try:
        # ── Stage 1: PDF text extraction ───────────────────────────────────────
        logger.info("[%s] Stage 1: PDF extraction", document_id)
        pdf_content = pdf_service.extract_content(document.file_path)
        document.page_count = pdf_content.page_count
        db.commit()

        text = pdf_content.full_text

        # ── Stage 2: OCR fallback ──────────────────────────────────────────────
        if ocr_service.needs_ocr(text):
            logger.info("[%s] Stage 2: OCR fallback triggered", document_id)
            page_images = pdf_service.render_pages_to_images(document.file_path)
            text = ocr_service.ocr_pages(page_images)

        if not text.strip():
            raise ValueError("No text could be extracted from the document.")

        # ── Stage 3: PII masking ───────────────────────────────────────────────
        logger.info("[%s] Stage 3: PII masking", document_id)
        masked_text, token_map = mask_pii(text)

        # ── Stage 4: LLM field extraction ─────────────────────────────────────
        logger.info("[%s] Stage 4: LLM extraction", document_id)
        extraction = llm_service.extract_judgment_fields(masked_text)

        # ── Stage 5: Source passage location ──────────────────────────────────
        logger.info("[%s] Stage 5: Source highlighting", document_id)

        # Delete any previous extraction for this document
        db.query(ExtractedField).filter(ExtractedField.document_id == doc_uuid).delete()
        db.commit()

        flagged_count = 0
        for field_name, field_result in extraction.fields.items():
            # Try to locate the source passage in the PDF
            bbox_data = None
            if field_result.source_passage:
                bbox_data = pdf_service.find_passage_bbox(
                    document.file_path, field_result.source_passage
                )

            is_flagged = field_result.confidence < CONFIDENCE_FLAG_THRESHOLD
            if is_flagged:
                flagged_count += 1

            ef = ExtractedField(
                document_id=doc_uuid,
                field_name=field_name,
                field_value=field_result.value,
                confidence=f"{field_result.confidence:.2f}",
                is_flagged=is_flagged,
                source_page=bbox_data["page"] if bbox_data else None,
                source_text=bbox_data["source_text"] if bbox_data else field_result.source_passage,
                bbox_x0=str(bbox_data["bbox"][0]) if bbox_data else None,
                bbox_y0=str(bbox_data["bbox"][1]) if bbox_data else None,
                bbox_x1=str(bbox_data["bbox"][2]) if bbox_data else None,
                bbox_y1=str(bbox_data["bbox"][3]) if bbox_data else None,
            )
            db.add(ef)

        db.commit()

        # ── Stage 6: Action plan generation ───────────────────────────────────
        logger.info("[%s] Stage 6: Action plan generation", document_id)
        action_result = llm_service.generate_action_plan(extraction.fields, masked_text)

        # ── Stage 7: Deadline calculation ──────────────────────────────────────
        order_date_field = extraction.fields.get("date_of_order")
        order_date: datetime | None = None
        if order_date_field and order_date_field.value:
            try:
                order_date = datetime.fromisoformat(order_date_field.value)
            except ValueError:
                pass

        explicit_deadline_field = extraction.fields.get("explicit_deadline")
        explicit_deadline_text = (
            explicit_deadline_field.value if explicit_deadline_field else None
        )

        deadline, deadline_basis = compute_deadline(
            order_date=order_date,
            explicit_deadline_text=explicit_deadline_text,
        )
        # Use LLM deadline if it parsed one and we couldn't
        if deadline is None and action_result.limitation_deadline:
            deadline = action_result.limitation_deadline
            deadline_basis = action_result.deadline_basis

        alert_level = compute_alert_level(deadline)

        # ── Stage 8: Persist action plan ───────────────────────────────────────
        existing_plan = db.query(ActionPlan).filter(ActionPlan.document_id == doc_uuid).first()
        if existing_plan:
            db.delete(existing_plan)
            db.commit()

        plan = ActionPlan(
            document_id=doc_uuid,
            recommended_action=action_result.recommended_action,
            action_description=action_result.action_description,
            responsible_dept=action_result.responsible_dept,
            limitation_deadline=deadline,
            deadline_basis=deadline_basis,
            alert_level=alert_level,
            llm_reasoning=action_result.llm_reasoning,
        )
        db.add(plan)

        document.status = DocumentStatus.EXTRACTED
        document.llm_provider_used = extraction.provider
        document.extraction_error = None
        db.commit()

        # ── Stage 9: Audit log ─────────────────────────────────────────────────
        log_event(
            db,
            event_type="extraction_completed",
            description=(
                f"Extracted {len(extraction.fields)} fields via {extraction.provider.value}. "
                f"{flagged_count} field(s) flagged for review. "
                f"Action: {action_result.recommended_action.value}. "
                f"Deadline: {deadline.date().isoformat() if deadline else 'unknown'}."
            ),
            document_id=doc_uuid,
            metadata={
                "provider": extraction.provider.value,
                "field_count": len(extraction.fields),
                "flagged_count": flagged_count,
                "alert_level": alert_level.value,
            },
        )

        logger.info("[%s] Extraction pipeline complete.", document_id)
        return {
            "status": "success",
            "document_id": document_id,
            "field_count": len(extraction.fields),
            "flagged_count": flagged_count,
            "provider": extraction.provider.value,
            "alert_level": alert_level.value,
        }

    except Exception as exc:
        logger.error("[%s] Extraction pipeline failed: %s", document_id, exc, exc_info=True)
        document.status = DocumentStatus.FAILED
        document.extraction_error = str(exc)
        db.commit()

        log_event(
            db,
            event_type="extraction_failed",
            description=str(exc),
            document_id=doc_uuid,
            metadata={"error": str(exc)},
        )
        raise
