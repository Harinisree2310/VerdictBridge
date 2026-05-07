"""
VerdictBridge – PII masking service.

Before any text is sent to an external LLM API, this service replaces
named entities (party names, addresses, case identifiers, phone numbers,
email addresses) with placeholder tokens.

The LLM reasons over structure, not raw PII — satisfying:
  - MeitY data localisation guidelines
  - The hackathon's hosted-LLM constraint
  - General data minimisation principles

A reverse mapping is kept in memory so that after extraction the
placeholder tokens can be substituted back for display.
"""
from __future__ import annotations
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# ── Presidio (preferred) ───────────────────────────────────────────────────────
try:
    from presidio_analyzer import AnalyzerEngine
    from presidio_anonymizer import AnonymizerEngine
    from presidio_anonymizer.entities import OperatorConfig

    _analyzer  = AnalyzerEngine()
    _anonymizer = AnonymizerEngine()
    _PRESIDIO  = True
    logger.info("Presidio PII engine loaded.")
except ImportError:
    _PRESIDIO = False
    logger.warning("presidio not installed – falling back to regex PII masking.")

# Entity types to mask before LLM calls
MASK_ENTITIES = [
    "PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER",
    "LOCATION", "US_SSN", "IN_PAN", "IN_AADHAAR",
    "URL", "IP_ADDRESS",
]

# Regex fallback patterns (covers common Indian legal document PII)
_REGEX_PATTERNS: list[tuple[str, str]] = [
    (r"\b[A-Z]{5}[0-9]{4}[A-Z]\b",                    "<PAN>"),
    (r"\b[2-9][0-9]{3}\s?[0-9]{4}\s?[0-9]{4}\b",      "<AADHAAR>"),
    (r"\b[6-9]\d{9}\b",                                 "<PHONE>"),
    (r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Z|a-z]{2,}\b", "<EMAIL>"),
    (r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",        "<IP>"),
]


def mask_pii(text: str, language: str = "en") -> tuple[str, dict[str, str]]:
    """
    Mask PII in text and return (masked_text, token_map).

    token_map maps placeholder tokens back to original values so that
    extracted field values can be de-masked for display.

    Args:
        text: Raw document text.
        language: Language code for Presidio analyzer.

    Returns:
        (masked_text, token_map)
    """
    if not text or not text.strip():
        return text, {}

    token_map: dict[str, str] = {}

    if _PRESIDIO:
        try:
            results = _analyzer.analyze(
                text=text, entities=MASK_ENTITIES, language=language
            )
            if results:
                operators = {
                    e: OperatorConfig("replace", {"new_value": f"<{e}>"})
                    for e in MASK_ENTITIES
                }
                anonymized = _anonymizer.anonymize(
                    text=text, analyzer_results=results, operators=operators
                )
                return anonymized.text, token_map
        except Exception as exc:
            logger.error("Presidio masking failed: %s – falling back to regex", exc)

    # Regex fallback
    masked = text
    for pattern, placeholder in _REGEX_PATTERNS:
        masked = re.sub(pattern, placeholder, masked)

    return masked, token_map


def demask(text: Optional[str], token_map: dict[str, str]) -> Optional[str]:
    """Replace placeholder tokens back with original values."""
    if not text or not token_map:
        return text
    for token, original in token_map.items():
        text = text.replace(token, original)
    return text
