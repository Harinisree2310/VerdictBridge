"""
Tests for the tamper-evident audit log service.
Uses an in-memory SQLite database.
"""
import os
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.models import AuditLog
from backend.services.audit_service import log_event, verify_chain, GENESIS_HASH


@pytest.fixture
def db():
    """In-memory SQLite session for testing."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_first_entry_uses_genesis_hash(db):
    entry = log_event(db, event_type="test_event", description="first entry")
    assert entry.prev_hash == GENESIS_HASH
    assert entry.entry_hash is not None
    assert len(entry.entry_hash) == 64  # SHA-256 hex


def test_chain_links_entries(db):
    e1 = log_event(db, event_type="event_1", description="first")
    e2 = log_event(db, event_type="event_2", description="second")
    assert e2.prev_hash == e1.entry_hash


def test_chain_verification_passes(db):
    log_event(db, event_type="event_1", description="a")
    log_event(db, event_type="event_2", description="b")
    log_event(db, event_type="event_3", description="c")

    is_valid, errors = verify_chain(db)
    assert is_valid is True
    assert errors == []


def test_chain_verification_detects_tampering(db):
    log_event(db, event_type="event_1", description="a")
    e2 = log_event(db, event_type="event_2", description="b")

    # Tamper with the second entry's hash
    e2.entry_hash = "0" * 64
    db.commit()

    is_valid, errors = verify_chain(db)
    assert is_valid is False
    assert len(errors) > 0


def test_empty_chain_is_valid(db):
    is_valid, errors = verify_chain(db)
    assert is_valid is True
    assert errors == []


def test_log_event_with_metadata(db):
    entry = log_event(
        db,
        event_type="document_uploaded",
        description="Test upload",
        actor_label="officer_1",
        metadata={"file_size": "1024 KB", "pages": 5},
    )
    assert entry.metadata_json["file_size"] == "1024 KB"
    assert entry.actor_label == "officer_1"
