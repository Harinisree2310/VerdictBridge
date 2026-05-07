"""
Authentication routes — login, register, me.

Two login endpoints are provided:
  POST /auth/login       — OAuth2 form-encoded (username + password fields)
                           Required by FastAPI's built-in /docs "Authorize" button.
  POST /auth/login/json  — JSON body (email + password)
                           Used by the React frontend to avoid form-encoding issues.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user
from models import User
from schemas import Token, UserCreate, UserRead
from services.auth_service import authenticate_user, create_access_token, create_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


# ── Shared token builder ───────────────────────────────────────────────────────

def _build_token(user: User) -> Token:
    return Token(
        access_token=create_access_token({
            "sub": str(user.id),
            "department": user.department,
            "role": user.role.value,
        })
    )


def _check_credentials(db: Session, email: str, password: str) -> User:
    """Authenticate and return user, or raise 401."""
    user = authenticate_user(db, email.strip(), password)
    if not user:
        logger.warning("Failed login attempt for email: %s", email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


# ── Register ───────────────────────────────────────────────────────────────────

@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, db: Session = Depends(get_db)):
    """Register a new government officer account."""
    from sqlalchemy import select
    existing = db.execute(
        select(User).where(User.email == payload.email.strip().lower())
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered.")
    user = create_user(
        db,
        email=payload.email.strip().lower(),
        full_name=payload.full_name,
        password=payload.password,
        department=payload.department,
        role=payload.role,
    )
    logger.info("New user registered: %s (%s)", user.email, user.role)
    return user


# ── Login — form-encoded (OAuth2 standard, used by /docs) ─────────────────────

@router.post("/login", response_model=Token)
def login_form(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """
    Login with form-encoded credentials.
    Content-Type must be: application/x-www-form-urlencoded
    Fields: username (email), password
    """
    user = _check_credentials(db, form_data.username, form_data.password)
    logger.info("User logged in (form): %s", user.email)
    return _build_token(user)


# ── Login — JSON body (used by React frontend) ─────────────────────────────────

class LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/login/json", response_model=Token)
def login_json(payload: LoginRequest, db: Session = Depends(get_db)):
    """
    Login with a JSON body.
    Content-Type: application/json
    Body: {"email": "...", "password": "..."}

    This is the endpoint used by the React frontend.
    """
    user = _check_credentials(db, payload.email, payload.password)
    logger.info("User logged in (json): %s", user.email)
    return _build_token(user)


# ── Me ─────────────────────────────────────────────────────────────────────────

@router.get("/me", response_model=UserRead)
def me(current_user: User = Depends(get_current_user)):
    """Return the currently authenticated user's profile."""
    return current_user


# ── Change password ────────────────────────────────────────────────────────────

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Change the current user's password."""
    from backend.services.auth_service import verify_password, hash_password
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    if len(payload.new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters.")
    current_user.hashed_password = hash_password(payload.new_password)
    db.commit()
    logger.info("Password changed for user: %s", current_user.email)
