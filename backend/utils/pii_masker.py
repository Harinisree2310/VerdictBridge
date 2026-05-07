"""PII detection and masking using Microsoft Presidio."""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from presidio_analyzer import AnalyzerEngine
    from presidio_anonymizer import AnonymizerEngine
    from presidio_anonymizer.entities import OperatorConfig

    _analyzer = AnalyzerEngine()
    _anonymizer = AnonymizerEngine()
    _presidio_available = True
except ImportError:
    _presidio_available = False
    logger.warning(
        "presidio-analyzer / presidio-anonymizer not installed. "
        "PII masking will be skipped."
    )

# Entity types to detect and mask
DEFAULT_ENTITIES = [
    "PERSON",
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "US_SSN",
    "CREDIT_CARD",
    "US_BANK_NUMBER",
    "IP_ADDRESS",
    "LOCATION",
]


def mask_pii(text: str, entities: Optional[list[str]] = None, language: str = "en") -> str:
    """
    Detect and replace PII in text with placeholder tokens.

    Args:
        text: Input text that may contain PII.
        entities: List of entity types to mask. Defaults to DEFAULT_ENTITIES.
        language: Language code for the analyzer.

    Returns:
        Text with PII replaced by tokens like <PERSON>, <EMAIL_ADDRESS>, etc.
    """
    if not _presidio_available:
        return text

    if not text or not text.strip():
        return text

    entity_list = entities or DEFAULT_ENTITIES

    try:
        results = _analyzer.analyze(text=text, entities=entity_list, language=language)

        if not results:
            return text

        operators = {
            entity: OperatorConfig("replace", {"new_value": f"<{entity}>"})
            for entity in entity_list
        }

        anonymized = _anonymizer.anonymize(
            text=text,
            analyzer_results=results,
            operators=operators,
        )
        return anonymized.text
    except Exception as exc:
        logger.error("PII masking failed: %s", exc)
        return text  # fail open — return original text


def detect_pii(text: str, entities: Optional[list[str]] = None, language: str = "en") -> list[dict]:
    """
    Detect PII in text and return a list of findings without modifying the text.

    Returns:
        List of dicts: {"entity_type", "start", "end", "score"}
    """
    if not _presidio_available:
        return []

    entity_list = entities or DEFAULT_ENTITIES

    try:
        results = _analyzer.analyze(text=text, entities=entity_list, language=language)
        return [
            {
                "entity_type": r.entity_type,
                "start": r.start,
                "end": r.end,
                "score": round(r.score, 3),
            }
            for r in results
        ]
    except Exception as exc:
        logger.error("PII detection failed: %s", exc)
        return []
