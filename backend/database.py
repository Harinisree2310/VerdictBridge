"""
VerdictBridge – Database engine, session factory, and base model.

Defaults to SQLite for zero-install local development.
Switch DATABASE_URL to postgresql://... for production.

The engine is created lazily so test modules can set DATABASE_URL before
any model or service is imported.
"""
from __future__ import annotations
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase, Session


class Base(DeclarativeBase):
    pass


# ── Lazy engine / session factory ─────────────────────────────────────────────

_engine = None
_SessionLocal = None


def _get_engine():
    global _engine
    if _engine is None:
        from backend.config import get_settings
        settings = get_settings()
        url = settings.database_url

        kwargs: dict = {"echo": settings.debug}

        if url.startswith("sqlite"):
            # SQLite needs check_same_thread=False for FastAPI's thread model
            kwargs["connect_args"] = {"check_same_thread": False}
            # Enable WAL mode for better concurrent read performance
            def _set_wal(dbapi_conn, _):
                dbapi_conn.execute("PRAGMA journal_mode=WAL")
                dbapi_conn.execute("PRAGMA foreign_keys=ON")
        else:
            kwargs["pool_pre_ping"] = True
            kwargs["pool_size"] = 10
            kwargs["max_overflow"] = 20

        _engine = create_engine(url, **kwargs)

        if url.startswith("sqlite"):
            event.listen(_engine, "connect", _set_wal)

    return _engine


def _get_session_local():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=_get_engine()
        )
    return _SessionLocal


def get_engine():
    return _get_engine()


def SessionLocal() -> Session:  # type: ignore[return-value]
    """Create and return a new DB session."""
    return _get_session_local()()


def _reset_engine(new_engine=None):
    """Allow tests to swap in a different engine."""
    global _engine, _SessionLocal
    _engine = new_engine
    _SessionLocal = None


def get_db():
    """FastAPI dependency — yields a DB session and closes it after the request."""
    db = _get_session_local()()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables. Called once at application startup."""
    from backend import models  # noqa: F401 — registers all ORM classes
    Base.metadata.create_all(bind=_get_engine())
