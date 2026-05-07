"""
VerdictBridge – End-to-end demo script.

Demonstrates the full pipeline without requiring a running server:
  1. Simulates a Karnataka HC judgment text
  2. Runs PII masking
  3. Runs LLM extraction (mock provider — no API key needed)
  4. Runs action plan generation
  5. Computes deadline and alert level
  6. Prints a formatted report

Run with:
  python demo_pipeline.py
  python demo_pipeline.py --real   (uses real LLM if API keys are in .env)
"""
import sys
import json
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

from backend.services.pii_service import mask_pii
from backend.services.llm_service import extract_judgment_fields, generate_action_plan
from backend.utils.deadline_calculator import compute_deadline, compute_alert_level
from backend.models import AlertLevel

SAMPLE_JUDGMENT = """
IN THE HIGH COURT OF KARNATAKA AT BENGALURU

DATED THIS THE 15TH DAY OF MARCH 2024

W.P. No. 12345/2024

BEFORE THE HON'BLE MR. JUSTICE ARUN KUMAR

Sri Ramesh Kumar, S/o Late Suresh Kumar,
Aged about 45 years, Working as Assistant Engineer,
Public Works Department, Bengaluru - 560 001.
Mobile: 9876543210
Email: ramesh.kumar@pwd.kar.gov.in                    ... Petitioner

Vs.

1. State of Karnataka, represented by its
   Principal Secretary, Public Works Department,
   Vidhana Soudha, Bengaluru - 560 001.
2. The Chief Engineer, PWD (South), Bengaluru.        ... Respondents

ORDER

The petitioner has challenged the order dated 01.01.2024 passed by the
2nd respondent by which his representation for promotion to the post of
Executive Engineer has been rejected without assigning any reasons.

Having heard Sri B.V. Acharya, learned Senior Counsel for the petitioner
and Sri C.H. Hanumantharaya, learned AGA for the respondents, this Court
is of the view that the respondents have not considered the petitioner's
case in accordance with the Karnataka Civil Services (Probation) Rules, 1977.

The impugned order is hereby quashed. The respondents are directed to
consider the case of the petitioner for promotion to the post of Executive
Engineer within a period of 8 weeks from the date of receipt of this order,
strictly in accordance with the applicable rules and seniority list.

The petitioner shall be entitled to all consequential benefits if found
eligible for promotion.

No costs.

                                        Sd/-
                              (ARUN KUMAR, J.)
"""

SEPARATOR = "─" * 70


def print_section(title: str):
    print(f"\n{SEPARATOR}")
    print(f"  {title}")
    print(SEPARATOR)


def main():
    use_real = "--real" in sys.argv
    if use_real:
        print("🔑 Using real LLM providers (requires API keys in .env)")
    else:
        print("🤖 Using mock LLM provider (no API keys required)")

    print_section("STAGE 1 — Input Document")
    print(SAMPLE_JUDGMENT[:400] + "...")

    # ── PII Masking ────────────────────────────────────────────────────────────
    print_section("STAGE 2 — PII Masking")
    try:
        masked_text, token_map = mask_pii(SAMPLE_JUDGMENT)
    except Exception:
        # Presidio/spaCy not fully installed — use regex fallback
        import re
        masked_text = re.sub(r"\b[6-9]\d{9}\b", "<PHONE>", SAMPLE_JUDGMENT)
        masked_text = re.sub(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Z|a-z]{2,}\b", "<EMAIL>", masked_text)
        token_map = {}
    # Show a snippet of the masked text
    print("Original snippet: 'Mobile: 9876543210, Email: ramesh.kumar@pwd.kar.gov.in'")
    # Find the masked version
    for line in masked_text.split("\n"):
        if "PHONE" in line or "EMAIL" in line or "9876" in line or "ramesh" in line.lower():
            print(f"Masked:  '{line.strip()}'")
            break
    print(f"✓ PII masking complete. Text sent to LLM has PII replaced with tokens.")

    # ── LLM Extraction ─────────────────────────────────────────────────────────
    print_section("STAGE 3 — LLM Field Extraction")
    print(f"Provider chain: Claude → Gemini → GPT-4o → Mock")

    extraction = extract_judgment_fields(masked_text)
    print(f"✓ Provider used: {extraction.provider.value.upper()}")
    print(f"✓ Fields extracted: {len(extraction.fields)}")

    flagged = [(k, v) for k, v in extraction.fields.items() if v.is_flagged]
    print(f"⚠  Fields flagged for review (confidence < 70%): {len(flagged)}")

    print("\nExtracted fields:")
    for name, field in extraction.fields.items():
        flag_icon = "⚠ " if field.is_flagged else "✓ "
        conf_pct = f"{field.confidence * 100:.0f}%"
        value_display = (field.value[:60] + "…") if field.value and len(field.value) > 60 else field.value
        print(f"  {flag_icon} {name:<25} [{conf_pct:>4}]  {value_display}")

    # ── Action Plan ────────────────────────────────────────────────────────────
    print_section("STAGE 4 — Action Plan Generation")
    plan = generate_action_plan(extraction.fields, masked_text)
    print(f"✓ Provider used: {plan.provider.value.upper()}")
    print(f"  Recommended action : {plan.recommended_action.value.upper()}")
    print(f"  Responsible dept   : {plan.responsible_dept}")
    print(f"  Action description : {plan.action_description}")
    print(f"  LLM reasoning      : {plan.llm_reasoning}")

    # ── Deadline Calculation ───────────────────────────────────────────────────
    print_section("STAGE 5 — Deadline Calculation")
    order_date_field = extraction.fields.get("date_of_order")
    order_date = None
    if order_date_field and order_date_field.value:
        try:
            order_date = datetime.fromisoformat(order_date_field.value)
        except ValueError:
            pass

    explicit_field = extraction.fields.get("explicit_deadline")
    explicit_text = explicit_field.value if explicit_field else None

    deadline, basis = compute_deadline(
        order_date=order_date,
        explicit_deadline_text=explicit_text,
    )
    alert = compute_alert_level(deadline)

    alert_icons = {
        AlertLevel.RED: "🔴 RED ALERT",
        AlertLevel.WARNING: "🟡 WARNING",
        AlertLevel.NORMAL: "🟢 NORMAL",
    }

    print(f"  Order date         : {order_date.date() if order_date else 'unknown'}")
    print(f"  Explicit deadline  : {explicit_text or 'none stated'}")
    print(f"  Computed deadline  : {deadline.date() if deadline else 'unknown'}")
    print(f"  Deadline basis     : {basis}")
    print(f"  Alert level        : {alert_icons[alert]}")

    if deadline:
        days_left = (deadline - datetime.utcnow()).days
        print(f"  Days remaining     : {days_left}")

    # ── Summary ────────────────────────────────────────────────────────────────
    print_section("PIPELINE COMPLETE — Summary")
    print(f"  Document processed in 5 stages")
    print(f"  LLM provider       : {extraction.provider.value.upper()}")
    print(f"  Fields extracted   : {len(extraction.fields)}")
    print(f"  Fields flagged     : {len(flagged)}")
    print(f"  Action required    : {plan.recommended_action.value.upper()}")
    print(f"  Deadline           : {deadline.date() if deadline else 'TBD'}")
    print(f"  Alert level        : {alert.value.upper()}")
    print(f"\n  ✓ Ready for human review in VerdictBridge dashboard")
    print(SEPARATOR)


if __name__ == "__main__":
    main()
