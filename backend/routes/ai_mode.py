"""
AI mode toggle endpoints.

GET  /ai/mode        → current mode + provider status (always reads fresh settings)
POST /ai/mode        → toggle between 'ai' and 'mock'
POST /ai/reload      → reload .env without server restart (picks up new API keys)
"""
from __future__ import annotations
import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.config import reload_settings
from backend.dependencies import get_current_user
from backend.models import User
from backend.services.llm_service import get_ai_mode, set_force_mock

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ai", tags=["ai-mode"])


class ModePayload(BaseModel):
    mode: str   # "ai" or "mock"


@router.get("/mode")
def read_mode(_: User = Depends(get_current_user)):
    """
    Return current AI / Mock mode and which LLM providers are configured.
    Always reloads settings so API key changes in .env are visible immediately.
    """
    reload_settings()   # clear lru_cache → pick up any .env changes
    return get_ai_mode()


@router.post("/mode")
def set_mode(payload: ModePayload, _: User = Depends(get_current_user)):
    """
    Switch between AI and Mock modes at runtime.
    Also reloads settings so the new mode uses the latest API keys from .env.
    """
    reload_settings()   # pick up latest .env before deciding chain
    force = payload.mode.lower() == "mock"
    set_force_mock(force)
    result = get_ai_mode()
    logger.info(
        "AI mode changed to %s. Providers: %s",
        result["mode"].upper(),
        result["providers_configured"],
    )
    return result


@router.post("/reload")
def reload_config(_: User = Depends(get_current_user)):
    """
    Reload API keys and settings from .env without restarting the server.
    Call this after editing .env to add or change API keys.
    """
    s = reload_settings()
    result = get_ai_mode()
    logger.info("Settings reloaded. Providers: %s", result["providers_configured"])
    return {
        **result,
        "reloaded": True,
        "message": "Settings reloaded from .env successfully.",
    }
