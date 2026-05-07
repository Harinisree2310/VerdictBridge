"""
Tests for the LLM extraction service.
Uses the mock provider so no API keys are required.
"""
import os
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_llm.db")

import pytest
from unittest.mock import patch
from backend.services.llm_service import (
    extract_judgment_fields,
    generate_action_plan,
    CONFIDENCE_FLAG_THRESHOLD,
)
from backend.models import ActionType, LLMProvider


SAMPLE_JUDGMENT_TEXT = """
IN THE HIGH COURT OF KARNATAKA AT BENGALURU
DATED THIS THE 15TH DAY OF MARCH 2024

W.P. No. 12345/2024

BEFORE THE HON'BLE MR. JUSTICE A. KUMAR

Sri Ramesh Kumar, S/o Late Suresh Kumar,
Aged about 45 years, Working as Assistant Engineer,
Public Works Department, Bengaluru.                    ... Petitioner

Vs.

1. State of Karnataka, represented by its
   Principal Secretary, Public Works Department,
   Vidhana Soudha, Bengaluru - 560 001.
2. The Chief Engineer, PWD, Bengaluru.              ... Respondents

ORDER

The petitioner has challenged the order dated 01.01.2024 by which his
representation for promotion to the post of Executive Engineer has been rejected.

Having heard the learned counsel for both parties, this Court is of the view
that the respondents have not considered the petitioner's case in accordance
with the applicable rules.

Accordingly, the writ petition is allowed. The respondents are directed to
consider the case of the petitioner for promotion to the post of Executive
Engineer within a period of 8 weeks from the date of receipt of this order.

No costs.

                                        Sd/-
                              (A. KUMAR, J.)
"""


def test_extract_fields_mock():
    """extract_judgment_fields returns expected fields using mock provider."""
    result = extract_judgment_fields(SAMPLE_JUDGMENT_TEXT)

    assert result.provider == LLMProvider.MOCK
    assert "case_number" in result.fields
    assert "court_name" in result.fields
    assert "date_of_order" in result.fields
    assert "petitioner" in result.fields
    assert "respondent" in result.fields
    assert "key_directions" in result.fields

    # All confidence scores should be between 0 and 1
    for name, field in result.fields.items():
        assert 0.0 <= field.confidence <= 1.0, f"Field {name} has invalid confidence {field.confidence}"


def test_flagging_logic():
    """Fields with confidence below threshold should be auto-flagged."""
    result = extract_judgment_fields(SAMPLE_JUDGMENT_TEXT)
    for name, field in result.fields.items():
        expected_flagged = field.confidence < CONFIDENCE_FLAG_THRESHOLD
        assert field.is_flagged == expected_flagged, (
            f"Field '{name}' flagged={field.is_flagged} but confidence={field.confidence}"
        )


def test_generate_action_plan_mock():
    """generate_action_plan returns a valid ActionPlanResult using mock provider."""
    extraction = extract_judgment_fields(SAMPLE_JUDGMENT_TEXT)
    plan = generate_action_plan(extraction.fields, SAMPLE_JUDGMENT_TEXT)

    assert plan.recommended_action in list(ActionType)
    assert plan.action_description
    assert plan.responsible_dept
    assert plan.provider == LLMProvider.MOCK


def test_extract_fields_empty_text():
    """Empty text should still return a result (mock handles it gracefully)."""
    result = extract_judgment_fields("")
    assert isinstance(result.fields, dict)


def test_provider_chain_falls_to_mock():
    """When no API keys are configured, the mock provider should be used."""
    with patch("backend.services.llm_service.settings") as mock_settings:
        mock_settings.anthropic_api_key = ""
        mock_settings.google_api_key = ""
        mock_settings.openai_api_key = ""
        mock_settings.claude_model = "claude-3-5-sonnet-20241022"
        mock_settings.claude_max_tokens = 4096
        mock_settings.gemini_model = "gemini-1.5-pro"
        mock_settings.openai_model = "gpt-4o"

        result = extract_judgment_fields(SAMPLE_JUDGMENT_TEXT)
        assert result.provider == LLMProvider.MOCK
