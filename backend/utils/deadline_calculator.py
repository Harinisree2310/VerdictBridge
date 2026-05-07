"""
VerdictBridge – Legal deadline calculator.

Handles:
  - Karnataka High Court appeal windows (90 days default)
  - Relative date language: "8 weeks from date of order", "90 days from..."
  - Court day arithmetic (excludes weekends + Indian public holidays)
  - Red/warning alert level computation
"""
from __future__ import annotations
import re
from datetime import date, datetime, timedelta
from typing import Optional

from backend.config import get_settings
from backend.models import AlertLevel

settings = get_settings()


# ── Indian public holidays (national + Karnataka state) ───────────────────────
# Extend this set annually or load from a database table in production.
INDIAN_HOLIDAYS: set[date] = {
    # 2024
    date(2024, 1, 26),  # Republic Day
    date(2024, 3, 25),  # Holi
    date(2024, 4, 14),  # Dr. Ambedkar Jayanti / Tamil New Year
    date(2024, 4, 17),  # Ram Navami
    date(2024, 5, 23),  # Buddha Purnima
    date(2024, 8, 15),  # Independence Day
    date(2024, 10, 2),  # Gandhi Jayanti
    date(2024, 10, 12), # Dussehra
    date(2024, 11, 1),  # Karnataka Rajyotsava
    date(2024, 11, 15), # Diwali
    date(2024, 12, 25), # Christmas
    # 2025
    date(2025, 1, 26),
    date(2025, 3, 14),  # Holi
    date(2025, 4, 14),
    date(2025, 8, 15),
    date(2025, 10, 2),
    date(2025, 10, 2),  # Gandhi Jayanti
    date(2025, 11, 1),  # Karnataka Rajyotsava
    date(2025, 12, 25),
    # 2026
    date(2026, 1, 26),
    date(2026, 8, 15),
    date(2026, 11, 1),
    date(2026, 12, 25),
}


def is_court_day(d: date) -> bool:
    """Return True if the date is a weekday and not an Indian public holiday."""
    return d.weekday() < 5 and d not in INDIAN_HOLIDAYS


def add_court_days(start: date, days: int) -> date:
    """Add N court days (business days excluding Indian holidays) to start date."""
    current = start
    remaining = days
    while remaining > 0:
        current += timedelta(days=1)
        if is_court_day(current):
            remaining -= 1
    return current


def add_calendar_days(start: date, days: int) -> date:
    """Add N calendar days, rolling forward to next court day if needed."""
    result = start + timedelta(days=days)
    while not is_court_day(result):
        result += timedelta(days=1)
    return result


def add_weeks(start: date, weeks: int) -> date:
    """Add N calendar weeks, rolling forward to next court day if needed."""
    return add_calendar_days(start, weeks * 7)


# ── Relative date parser ───────────────────────────────────────────────────────

_RELATIVE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"(\d+)\s+days?\s+from", re.I),   "days"),
    (re.compile(r"(\d+)\s+weeks?\s+from", re.I),  "weeks"),
    (re.compile(r"(\d+)\s+months?\s+from", re.I), "months"),
    (re.compile(r"within\s+(\d+)\s+days?", re.I), "days"),
    (re.compile(r"within\s+(\d+)\s+weeks?", re.I),"weeks"),
]


def parse_relative_deadline(
    deadline_text: str,
    order_date: date,
) -> Optional[date]:
    """
    Parse relative deadline language and compute an absolute date.

    Examples:
      "90 days from date of order"  → order_date + 90 court days
      "8 weeks from date of order"  → order_date + 8 weeks
      "within 30 days"              → order_date + 30 court days

    Returns None if the text cannot be parsed.
    """
    if not deadline_text:
        return None

    for pattern, unit in _RELATIVE_PATTERNS:
        m = pattern.search(deadline_text)
        if m:
            n = int(m.group(1))
            if unit == "days":
                return add_court_days(order_date, n)
            elif unit == "weeks":
                return add_weeks(order_date, n)
            elif unit == "months":
                # Approximate: 1 month ≈ 30 calendar days
                return add_calendar_days(order_date, n * 30)

    return None


def compute_deadline(
    order_date: Optional[datetime],
    explicit_deadline_text: Optional[str],
    compliance_required: bool = True,
    default_days: int = 90,
) -> tuple[Optional[datetime], str]:
    """
    Compute the limitation deadline for a judgment.

    Priority:
      1. Parse explicit_deadline_text if present
      2. Use default_days from order_date
      3. Return None if order_date is unknown

    Returns:
        (deadline_datetime, basis_explanation)
    """
    if order_date is None:
        return None, "Order date unknown — deadline cannot be computed."

    order_d = order_date.date() if isinstance(order_date, datetime) else order_date

    if explicit_deadline_text:
        parsed = parse_relative_deadline(explicit_deadline_text, order_d)
        if parsed:
            basis = (
                f"Parsed from judgment text: '{explicit_deadline_text}' "
                f"starting from order date {order_d.isoformat()}"
            )
            return datetime.combine(parsed, datetime.min.time()), basis

    # Default window
    deadline_d = add_court_days(order_d, default_days)
    basis = (
        f"{default_days} court days from order date {order_d.isoformat()} "
        f"(Karnataka HC default limitation period)"
    )
    return datetime.combine(deadline_d, datetime.min.time()), basis


def compute_alert_level(deadline: Optional[datetime]) -> AlertLevel:
    """
    Compute alert level based on how close the deadline is to today.

    RED     → ≤ settings.deadline_red_alert_days
    WARNING → ≤ 30 days
    NORMAL  → > 30 days or no deadline
    """
    if deadline is None:
        return AlertLevel.NORMAL

    today = datetime.utcnow()
    days_remaining = (deadline - today).days

    if days_remaining <= settings.deadline_red_alert_days:
        return AlertLevel.RED
    if days_remaining <= 30:
        return AlertLevel.WARNING
    return AlertLevel.NORMAL
