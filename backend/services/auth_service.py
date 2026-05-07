"""
VerdictBridge – Authentication service.

JWT-based auth with role-based access control.
Officers are scoped to their own department's documents.
"""
from __future__ import annotations
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from config import get_settings
from models import User, UserRole
from schemas import TokenData

settings = get_settings()

ALGORITHM = "HS256"
# Use sha256_crypt as primary scheme — avoids passlib/bcrypt version conflicts.
# bcrypt is kept as a deprecated fallback for any existing hashes.
pwd_context = CryptContext(schemes=["sha256_crypt", "bcrypt"], deprecated=["bcrypt"])


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    to_encode["exp"] = expire
    return jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)


def decode_token(token: str) -> TokenData:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        department = payload.get("department")
        role = payload.get("role")
        if user_id is None:
            raise JWTError("Missing sub claim")
        return TokenData(user_id=UUID(user_id), department=department, role=UserRole(role))
    except JWTError as exc:
        raise ValueError(f"Invalid token: {exc}") from exc


def authenticate_user(db: Session, email: str, password: str) -> Optional[User]:
    """Look up user by email (case-insensitive) and verify password."""
    user = db.query(User).filter(User.email == email.strip().lower()).first()
    if not user or not verify_password(password, user.hashed_password):
        return None
    if not user.is_active:
        return None
    return user


def get_user_by_id(db: Session, user_id: UUID) -> Optional[User]:
    return db.query(User).filter(User.id == user_id).first()


def create_user(db: Session, email: str, full_name: str, password: str,
                department: str, role: UserRole = UserRole.OFFICER) -> User:
    user = User(
        email=email.strip().lower(),   # always store lowercase
        full_name=full_name,
        hashed_password=hash_password(password),
        department=department,
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
