"""
Tests for the deadline calculator.
"""
import os
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_deadline.db")

import pytest
from datetime import date, datetime
from backend.utils.deadline_calculator import (
    add_court_days,
    add_calendar_days,
    compute_deadline,
    compute_alert_level,
    parse_relative_deadline,
    is_court_day,
    INDIAN_HOLIDAYS,
)
from backend.models import AlertLevel


def test_is_court_day_weekday():
    assert is_court_day(date(2024, 3, 18)) is True   # Monday


def test_is_court_day_weekend():
    assert is_court_day(date(2024, 3, 16)) is False  # Saturday
    assert is_court_day(date(2024, 3, 17)) is False  # Sunday


def test_is_court_day_holiday():
    assert is_court_day(date(2024, 8, 15)) is False  # Independence Day


def test_add_court_days_skips_weekend():
    # Friday + 1 court day = Monday
    result = add_court_days(date(2024, 3, 15), 1)  # Friday
    assert result.weekday() < 5  # must be a weekday


def test_add_court_days_90():
    start = date(2024, 1, 2)
    result = add_court_days(start, 90)
    # Result must be a court day
    assert is_court_day(result)
    # Must be at least 90 calendar days later
    assert (result - start).days >= 90


def test_parse_relative_deadline_days():
    order_date = date(2024, 3, 15)
    result = parse_relative_deadline("90 days from date of order", order_date)
    assert result is not None
    assert (result - order_date).days >= 90


def test_parse_relative_deadline_weeks():
    order_date = date(2024, 3, 15)
    result = parse_relative_deadline("within 8 weeks from date of receipt", order_date)
    assert result is not None
    assert (result - order_date).days >= 56  # 8 * 7


def test_parse_relative_deadline_no_match():
    result = parse_relative_deadline("no deadline mentioned", date(2024, 3, 15))
    assert result is None


def test_compute_deadline_with_explicit():
    order_date = datetime(2024, 3, 15)
    deadline, basis = compute_deadline(
        order_date=order_date,
        explicit_deadline_text="90 days from date of order",
    )
    assert deadline is not None
    assert "90 days" in basis.lower() or "parsed" in basis.lower()


def test_compute_deadline_default():
    order_date = datetime(2024, 3, 15)
    deadline, basis = compute_deadline(
        order_date=order_date,
        explicit_deadline_text=None,
        default_days=90,
    )
    assert deadline is not None
    assert "90" in basis


def test_compute_deadline_no_order_date():
    deadline, basis = compute_deadline(order_date=None, explicit_deadline_text=None)
    assert deadline is None
    assert "unknown" in basis.lower()


def test_alert_level_red():
    from datetime import timedelta
    deadline = datetime.utcnow() + timedelta(days=5)
    assert compute_alert_level(deadline) == AlertLevel.RED


def test_alert_level_warning():
    from datetime import timedelta
    deadline = datetime.utcnow() + timedelta(days=20)
    assert compute_alert_level(deadline) == AlertLevel.WARNING


def test_alert_level_normal():
    from datetime import timedelta
    deadline = datetime.utcnow() + timedelta(days=60)
    assert compute_alert_level(deadline) == AlertLevel.NORMAL


def test_alert_level_none():
    assert compute_alert_level(None) == AlertLevel.NORMAL
