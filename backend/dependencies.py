"""
VerdictBridge – FastAPI dependency injection helpers.

Provides:
  - get_current_user: validates JWT and returns User
  - require_role: role-based access guard
  - get_document_for_user: fetches document with department scoping
"""
from __future__ import annotations
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Document, User, UserRole
from backend.services.auth_service import decode_token, get_user_by_id

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        token_data = decode_token(token)
    except ValueError:
        raise credentials_exc

    user = get_user_by_id(db, token_data.user_id)
    if not user or not user.is_active:
        raise credentials_exc
    return user


def require_role(*roles: UserRole):
    """Dependency factory: raises 403 if user's role is not in allowed roles."""
    def _check(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{current_user.role}' is not permitted for this action.",
            )
        return current_user
    return _check


def get_document_for_user(
    document_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Document:
    """
    Fetch a document, enforcing department scoping for non-admin users.
    Admins can access all documents; officers only see their department's.
    """
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    if current_user.role != UserRole.ADMIN:
        if document.department and document.department != current_user.department:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this document.",
            )
    return document
