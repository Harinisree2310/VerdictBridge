"""
VerdictBridge – LLM extraction service.

Architecture:
  Primary   → Claude 3.5 Sonnet  (best long-document legal reasoning)
  Fallback  → Gemini 1.5 Pro     (PDF-native, cost-efficient, large context)
  Tertiary  → GPT-4o             (broad availability fallback)
  Mock      → deterministic stub  (for testing without API keys)

Each provider implements the same interface:
  extract_judgment_fields(text) → JudgmentExtractionResult
  generate_action_plan(fields, text) → ActionPlanResult

The service auto-selects the best available provider based on configured
API keys and falls through the chain on failure.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from backend.config import get_settings
from backend.models import ActionType, LLMProvider

logger = logging.getLogger(__name__)
settings = get_settings()

# ── Runtime AI/Mock toggle ─────────────────────────────────────────────────────
# Can be flipped at runtime via POST /api/v1/ai/mode without server restart.
# Default: False → real LLMs are tried first; falls back to mock if all fail.
_FORCE_MOCK: bool = False


def set_force_mock(enabled: bool) -> None:
    """Enable or disable forced mock mode at runtime."""
    global _FORCE_MOCK
    _FORCE_MOCK = enabled
    logger.info("AI mode set to: %s", "MOCK" if enabled else "AI")


def get_ai_mode() -> dict:
    """Return current AI mode status and which providers are configured."""
    s = get_settings()  # always fresh — reflects latest .env / reload
    return {
        "mode": "mock" if _FORCE_MOCK else "ai",
        "force_mock": _FORCE_MOCK,
        "providers_configured": {
            "claude":  bool(s.anthropic_api_key),
            "gemini":  bool(s.google_api_key),
            "openai":  bool(s.openai_api_key),
        },
    }


# ── Output data classes ────────────────────────────────────────────────────────

@dataclass
class FieldResult:
    value: Optional[str]
    confidence: float          # 0.0 – 1.0
    source_passage: Optional[str] = None   # verbatim text from judgment
    is_flagged: bool = False   # auto-set when confidence < threshold


@dataclass
class JudgmentExtractionResult:
    fields: dict[str, FieldResult]
    provider: LLMProvider
    raw_response: str = ""


@dataclass
class ActionPlanResult:
    recommended_action: ActionType
    action_description: str
    responsible_dept: str
    limitation_deadline: Optional[datetime]
    deadline_basis: str
    llm_reasoning: str
    provider: LLMProvider


# ── Prompt templates ───────────────────────────────────────────────────────────

EXTRACTION_SYSTEM = """You are a senior legal analyst specialising in Indian court and tribunal judgments,
including the High Courts, Central Administrative Tribunal (CAT), State Administrative Tribunals,
and other quasi-judicial bodies.
Your task is to extract structured information from court/tribunal judgment text with high precision.
Return ONLY valid JSON. Never hallucinate values — if a field is absent, use null.
For each field, provide a confidence score (0.0–1.0) and quote the exact source passage from the text."""

EXTRACTION_USER = """Extract the following fields from this court or tribunal judgment.

FIELDS TO EXTRACT:
- case_number        : Case / O.A. / W.P. / Appeal number as stated in the document
- court_name         : Full name of the court or tribunal (e.g. Central Administrative Tribunal, Kolkata Bench)
- bench              : Judge/member name(s) on the bench
- date_of_order      : Date the judgment/order was pronounced (ISO format YYYY-MM-DD)
- petitioner         : Petitioner / applicant / appellant name(s)
- respondent         : Respondent name(s) — often a government department or ministry
- subject_matter     : Brief subject of the case (1-2 sentences)
- key_directions     : Specific directions/orders issued by the court/tribunal (list each separately)
- compliance_required: Whether the government / respondent must take a compliance action (true/false)
- appeal_mentioned   : Whether the judgment mentions appeal rights or limitation period
- explicit_deadline  : Any explicit deadline stated in the judgment (ISO date or relative like "90 days")
- department_named   : Government department(s) explicitly named in directions
- penalty_mentioned  : Any penalty, contempt, or cost mentioned
- summary            : 3-sentence plain-language summary of the outcome

Return JSON in EXACTLY this schema:
{{
  "fields": {{
    "<field_name>": {{
      "value": "<extracted value or null>",
      "confidence": <0.0-1.0>,
      "source_passage": "<verbatim quote from text, max 200 chars, or null>"
    }}
  }}
}}

JUDGMENT TEXT:
{text}"""

ACTION_PLAN_SYSTEM = """You are a government legal compliance officer for Karnataka.
Given extracted fields from a court judgment, generate a precise action plan.
Be conservative: when in doubt, recommend compliance or seeking clarification over inaction.
Return ONLY valid JSON."""

ACTION_PLAN_USER = """Based on these extracted judgment fields, generate an action plan for the government department.

EXTRACTED FIELDS:
{fields_json}

CURRENT DATE: {today}

Determine:
1. recommended_action: one of [comply, consider_appeal, file_appeal, seek_clarification, no_action]
2. action_description: specific steps the department must take (be precise)
3. responsible_dept: which department should act (use extracted department_named if available)
4. limitation_deadline: calculate the exact deadline date (ISO format)
   - For appeals: typically 90 days from date_of_order under Karnataka HC rules
   - For compliance: use explicit_deadline if present, else 30 days from date_of_order
   - If date_of_order is null, return null
5. deadline_basis: explain how you calculated the deadline (e.g. "90 days from order date 2024-03-15 per Limitation Act")
6. reasoning: step-by-step reasoning for your recommendation (2-3 sentences)

Return JSON:
{{
  "recommended_action": "<action>",
  "action_description": "<description>",
  "responsible_dept": "<department>",
  "limitation_deadline": "<ISO date or null>",
  "deadline_basis": "<explanation>",
  "reasoning": "<chain of thought>"
}}"""


# ── Provider implementations ───────────────────────────────────────────────────

def _call_claude(system: str, user: str) -> str:
    """Call Anthropic Claude API and return raw text response."""
    import anthropic
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    message = client.messages.create(
        model=settings.claude_model,
        max_tokens=settings.claude_max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return message.content[0].text


def _call_gemini(system: str, user: str) -> str:
    """Call Google Gemini API and return raw text response."""
    import google.generativeai as genai
    genai.configure(api_key=settings.google_api_key)
    model = genai.GenerativeModel(
        model_name=settings.gemini_model,
        system_instruction=system,
        generation_config={"response_mime_type": "application/json"},
    )
    response = model.generate_content(user)
    return response.text


def _call_openai(system: str, user: str) -> str:
    """Call OpenAI API and return raw text response."""
    from openai import OpenAI
    client = OpenAI(api_key=settings.openai_api_key)
    response = client.chat.completions.create(
        model=settings.openai_model,
        temperature=0.0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return response.choices[0].message.content


# ── Case-specific mock data: Santi Charan Banerjee vs India Post ───────────────
# CAT Kolkata Bench, O.A., Order dated 19 February 2026
# Coram: Hon'ble Mr. Anindo Majumdar (Administrative Member) &
#        Hon'ble Mr. Diwaka Nath Prasad (Judicial Member)

_MOCK_EXTRACTION = json.dumps({
    "fields": {
        "case_number": {
            "value": "O.A. No. 441/00714/2025",
            "confidence": 0.94,
            "source_passage": "CENTRAL ADMINISTRATIVE TRIBUNAL, KOLKATA BENCH — O.A. No. 441/00714/2025"
        },
        "court_name": {
            "value": "Central Administrative Tribunal, Kolkata Bench",
            "confidence": 0.99,
            "source_passage": "CENTRAL ADMI... KOLKATA BE"
        },
        "bench": {
            "value": "Hon'ble Mr. Anindo Majumdar (Administrative Member) & Hon'ble Mr. Diwaka Nath Prasad (Judicial Member)",
            "confidence": 0.97,
            "source_passage": "Hon'ble Mr. Anindo Majumdar, Administrative Member\nHon'ble Mr. Diwaka"
        },
        "date_of_order": {
            "value": "2026-02-19",
            "confidence": 0.99,
            "source_passage": "Date of Order: 19 February, 2026"
        },
        "petitioner": {
            "value": "Santi Charan Banerjee",
            "confidence": 0.99,
            "source_passage": "Santi Charan Banerjee vs D/O India Post on 19 February, 2026"
        },
        "respondent": {
            "value": "Department of Posts (India Post), Ministry of Communications, Union of India",
            "confidence": 0.98,
            "source_passage": "vs D/O India Post"
        },
        "subject_matter": {
            "value": "Service matter concerning alleged denial of rightful benefits, promotion, or pay fixation by the applicant, a government servant in the Department of Posts (India Post), aggrieved by an administrative decision of the respondent department.",
            "confidence": 0.88,
            "source_passage": None
        },
        "key_directions": {
            "value": (
                "1. The Tribunal directs the respondents (Department of Posts) to take necessary action "
                "in accordance with the applicable service rules within the stipulated period.\n"
                "2. The respondents are directed to file a compliance report before the Tribunal within 90 days.\n"
                "3. Liberty is reserved to the applicant to approach the Tribunal in case of non-compliance."
            ),
            "confidence": 0.86,
            "source_passage": "Respondents are directed to take action as per the applicable service rules and file a compliance report"
        },
        "compliance_required": {
            "value": "true",
            "confidence": 0.97,
            "source_passage": None
        },
        "appeal_mentioned": {
            "value": "true",
            "confidence": 0.82,
            "source_passage": "Liberty is reserved to the applicant to approach this Tribunal in case of non-compliance"
        },
        "explicit_deadline": {
            "value": "90 days from date of order",
            "confidence": 0.91,
            "source_passage": "file a compliance report before the Tribunal within 90 days"
        },
        "department_named": {
            "value": "Department of Posts (India Post), Ministry of Communications",
            "confidence": 0.96,
            "source_passage": "D/O India Post"
        },
        "penalty_mentioned": {
            "value": "Contempt proceedings may be initiated for non-compliance",
            "confidence": 0.79,
            "source_passage": "Liberty is reserved to the applicant to approach this Tribunal in case of non-compliance"
        },
        "summary": {
            "value": (
                "The Central Administrative Tribunal, Kolkata Bench, allowed the Original Application filed by "
                "Santi Charan Banerjee, a government servant aggrieved by the Department of Posts (India Post). "
                "The Tribunal directed the respondent department to take corrective action per applicable service rules "
                "and file a compliance report within 90 days of the order dated 19 February 2026. "
                "Non-compliance may attract contempt proceedings before the Tribunal."
            ),
            "confidence": 0.90,
            "source_passage": None
        },
    }
})

_MOCK_ACTION_PLAN = json.dumps({
    "recommended_action": "comply",
    "action_description": (
        "The Department of Posts (India Post) must:\n"
        "1. Review the specific service matter of Santi Charan Banerjee (promotion/pay fixation/benefit denial) "
        "as per the applicable Central Civil Services rules and DoP service regulations.\n"
        "2. Issue a speaking order addressing the applicant's grievance within 90 days of 19-Feb-2026 "
        "(deadline: 20-May-2026).\n"
        "3. File a compliance report before the CAT Kolkata Bench on or before 20-May-2026.\n"
        "4. Communicate the compliance action taken to the applicant in writing.\n"
        "5. Retain copies of all compliance documents for audit and potential contempt review."
    ),
    "responsible_dept": "Department of Posts (India Post), Ministry of Communications, Government of India",
    "limitation_deadline": "2026-05-20",
    "deadline_basis": "90 days from date of order 19-Feb-2026 per CAT direction (compliance report deadline)",
    "reasoning": (
        "The Tribunal has explicitly directed the respondent (India Post) to take action per service rules "
        "and file a compliance report within 90 days — making 'comply' the only valid action. "
        "The applicant retains liberty to initiate contempt proceedings for non-compliance, "
        "elevating the risk level to WARNING. No grounds for appeal are apparent as the Tribunal "
        "has given a direction, not a final judgment on merits."
    )
})


def _call_mock(system: str, user: str) -> str:  # noqa: ARG001
    """
    Case-specific deterministic mock for Santi Charan Banerjee vs India Post
    (CAT Kolkata, 19 Feb 2026). Routes to extraction or action-plan stub
    based on which system prompt is active.
    Real LLMs are tried first when API keys are present — this is the final fallback.
    """
    # Detect which pipeline stage is running by inspecting the system prompt
    is_action_plan = "action plan" in system.lower() or "compliance officer" in system.lower()
    return _MOCK_ACTION_PLAN if is_action_plan else _MOCK_EXTRACTION


# ── Provider selection ─────────────────────────────────────────────────────────

def _get_provider_chain() -> list[tuple[LLMProvider, callable]]:
    """
    Build the ordered list of (provider, call_fn) based on available API keys
    and the current _FORCE_MOCK flag.

    IMPORTANT: calls get_settings() fresh on every invocation so that API keys
    added to .env after startup (and picked up via reload_settings()) are
    honoured immediately without a full server restart.
    """
    if _FORCE_MOCK:
        logger.info("Force-mock mode active — skipping real LLMs.")
        return [(LLMProvider.MOCK, _call_mock)]

    s = get_settings()  # live settings — reflects any cache reload
    chain: list[tuple[LLMProvider, callable]] = []

    if s.anthropic_api_key:
        chain.append((LLMProvider.CLAUDE, _call_claude))
    if s.google_api_key:
        chain.append((LLMProvider.GEMINI, _call_gemini))
    if s.openai_api_key:
        chain.append((LLMProvider.OPENAI, _call_openai))
    chain.append((LLMProvider.MOCK, _call_mock))   # always available as final fallback

    configured = [p.value for p, _ in chain]
    logger.info("LLM provider chain: %s", " → ".join(configured))
    return chain


def _call_with_fallback(system: str, user: str) -> tuple[str, LLMProvider]:
    """Try each provider in order, return (response_text, provider_used)."""
    chain = _get_provider_chain()
    last_error: Exception | None = None

    for provider, call_fn in chain:
        try:
            logger.info("Trying LLM provider: %s", provider.value)
            response = call_fn(system, user)
            logger.info("LLM provider %s succeeded.", provider.value)
            return response, provider
        except Exception as exc:
            logger.warning("Provider %s failed: %s – trying next.", provider.value, exc)
            last_error = exc

    raise RuntimeError(f"All LLM providers failed. Last error: {last_error}")


def _parse_json_response(raw: str) -> dict:
    """Extract JSON from LLM response, handling markdown code fences."""
    # Strip markdown fences if present
    cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`").strip()
    return json.loads(cleaned)


# ── Public API ─────────────────────────────────────────────────────────────────

CONFIDENCE_FLAG_THRESHOLD = 0.70   # fields below this are auto-flagged


def extract_judgment_fields(text: str) -> JudgmentExtractionResult:
    """
    Extract structured fields from judgment text using the best available LLM.

    Args:
        text: Pre-processed (PII-masked) judgment text.

    Returns:
        JudgmentExtractionResult with per-field confidence scores and source passages.
    """
    # Truncate to ~12k chars to stay within context limits for all providers
    truncated = text[:12000]
    user_prompt = EXTRACTION_USER.format(text=truncated)

    raw, provider = _call_with_fallback(EXTRACTION_SYSTEM, user_prompt)

    try:
        data = _parse_json_response(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM returned invalid JSON: {exc}\nRaw: {raw[:500]}") from exc

    fields: dict[str, FieldResult] = {}
    for fname, fdata in data.get("fields", {}).items():
        confidence = float(fdata.get("confidence", 0.5))
        fr = FieldResult(
            value=fdata.get("value"),
            confidence=confidence,
            source_passage=fdata.get("source_passage"),
            is_flagged=confidence < CONFIDENCE_FLAG_THRESHOLD,
        )
        fields[fname] = fr

    return JudgmentExtractionResult(fields=fields, provider=provider, raw_response=raw)


def generate_action_plan(
    fields: dict[str, FieldResult],
    text: str,
) -> ActionPlanResult:
    """
    Generate a recommended action plan from extracted judgment fields.

    Args:
        fields: Output of extract_judgment_fields.
        text: Original (PII-masked) judgment text for additional context.

    Returns:
        ActionPlanResult with deadline, responsible department, and reasoning.
    """
    fields_summary = {
        k: v.value for k, v in fields.items() if v.value is not None
    }
    today = datetime.utcnow().strftime("%Y-%m-%d")
    user_prompt = ACTION_PLAN_USER.format(
        fields_json=json.dumps(fields_summary, indent=2),
        today=today,
    )

    raw, provider = _call_with_fallback(ACTION_PLAN_SYSTEM, user_prompt)

    try:
        data = _parse_json_response(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Action plan LLM returned invalid JSON: {exc}") from exc

    # Parse action type
    action_str = data.get("recommended_action", "comply").lower().replace("-", "_")
    try:
        action = ActionType(action_str)
    except ValueError:
        action = ActionType.COMPLY

    # Parse deadline
    deadline: Optional[datetime] = None
    raw_deadline = data.get("limitation_deadline")
    if raw_deadline:
        try:
            deadline = datetime.fromisoformat(raw_deadline)
        except (ValueError, TypeError):
            # Try to infer from relative language as fallback
            order_date_str = fields_summary.get("date_of_order")
            if order_date_str:
                try:
                    order_date = datetime.fromisoformat(order_date_str)
                    deadline = order_date + timedelta(days=settings.default_appeal_days)
                except (ValueError, TypeError):
                    pass

    return ActionPlanResult(
        recommended_action=action,
        action_description=data.get("action_description", "Review judgment and take appropriate action."),
        responsible_dept=data.get("responsible_dept", "Concerned Department"),
        limitation_deadline=deadline,
        deadline_basis=data.get("deadline_basis", ""),
        llm_reasoning=data.get("reasoning", ""),
        provider=provider,
    )
