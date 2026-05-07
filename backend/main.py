"""
VerdictBridge – FastAPI application entry point.

Startup sequence:
  1. Initialize database (create tables)
  2. Create a default admin user if none exists
  3. Mount all routers
  4. Configure CORS

Run with:
  uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from database import init_db, SessionLocal
from routes import auth, upload, extraction, review, dashboard, ai_mode

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)
settings = get_settings()


def _seed_admin() -> None:
    """Create a default admin account if no users exist."""
    db = SessionLocal()
    try:
        from backend.models import User
        if db.query(User).count() == 0:
            from backend.services.auth_service import create_user
            from backend.models import UserRole
            admin = create_user(
                db,
                email="admin@verdictbridge.gov.in",
                full_name="System Administrator",
                password="Admin@1234",
                department="Administration",
                role=UserRole.ADMIN,
            )
            logger.info(
                "Default admin created: %s  (change password immediately!)",
                admin.email,
            )
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("VerdictBridge starting — initialising database…")
    init_db()
    _seed_admin()
    logger.info("VerdictBridge ready.")
    yield
    logger.info("VerdictBridge shutting down.")


app = FastAPI(
    title="VerdictBridge API",
    description=(
        "AI-Powered Court Judgment Intelligence for Government Action.\n\n"
        "Transforms Karnataka High Court judgment PDFs into verified, "
        "department-routed action plans with full audit trails."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ───────────────────────────────────────────────────────────────────────
# IMPORTANT: CORSMiddleware must be added FIRST, before any other middleware,
# so that OPTIONS preflight requests are handled before they reach route handlers.
#
# allow_credentials=True requires an explicit origin list (not "*").
# The list is driven by settings.cors_origins_list so it can be overridden
# via the CORS_ORIGINS environment variable without code changes.

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "Accept",
        "Origin",
        "X-Requested-With",
        "X-CSRF-Token",
    ],
    expose_headers=["Content-Disposition"],
    max_age=600,
)

# ── Routers ────────────────────────────────────────────────────────────────────
PREFIX = "/api/v1"

app.include_router(auth.router,       prefix=PREFIX)
app.include_router(upload.router,     prefix=PREFIX)
app.include_router(extraction.router, prefix=PREFIX)
app.include_router(review.router,     prefix=PREFIX)
app.include_router(dashboard.router,  prefix=PREFIX)
app.include_router(ai_mode.router,    prefix=PREFIX)


# ── Health ─────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["health"])
def health():
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": "1.0.0",
        "llm_primary": (
            "claude" if settings.anthropic_api_key else
            "gemini" if settings.google_api_key else
            "openai" if settings.openai_api_key else
            "mock"
        ),
        "cors_origins": settings.cors_origins_list,
    }
