"""
VerdictBridge – OCR service (Tesseract fallback for scanned judgments).

Handles:
  - Scanned Karnataka High Court PDFs (often physical-origin copies)
  - Bilingual documents (English + Kannada)
  - Image pre-processing for better OCR accuracy
"""
from __future__ import annotations
import io
import logging

import pytesseract
from PIL import Image, ImageFilter, ImageOps

from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

if settings.tesseract_cmd and settings.tesseract_cmd != "tesseract":
    pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd


def _preprocess_image(image: Image.Image) -> Image.Image:
    """
    Pre-process a scanned page image to improve OCR accuracy:
      1. Convert to grayscale
      2. Increase contrast
      3. Mild sharpening
      4. Binarise (threshold)
    """
    img = ImageOps.grayscale(image)
    img = ImageOps.autocontrast(img, cutoff=2)
    img = img.filter(ImageFilter.SHARPEN)
    # Binarise: pixels above 180 → white, below → black
    img = img.point(lambda p: 255 if p > 180 else 0, "1").convert("L")
    return img


def ocr_image_bytes(image_bytes: bytes, lang: str | None = None) -> str:
    """Run Tesseract OCR on raw PNG/JPEG bytes."""
    lang = lang or settings.ocr_language
    image = Image.open(io.BytesIO(image_bytes))
    processed = _preprocess_image(image)
    config = "--oem 3 --psm 6"   # LSTM engine, assume uniform block of text
    text = pytesseract.image_to_string(processed, lang=lang, config=config)
    return text.strip()


def ocr_pages(page_images: list[bytes], lang: str | None = None) -> str:
    """
    Run OCR on a list of page images and return concatenated text.
    Each page is labelled for downstream passage search.
    """
    lang = lang or settings.ocr_language
    results: list[str] = []
    for i, img_bytes in enumerate(page_images, start=1):
        try:
            page_text = ocr_image_bytes(img_bytes, lang=lang)
            if page_text:
                results.append(f"[Page {i}]\n{page_text}")
        except Exception as exc:
            logger.warning("OCR failed on page %d: %s", i, exc)
    return "\n\n".join(results)


def needs_ocr(text: str) -> bool:
    """
    Heuristic: if native PDF extraction returned very little text,
    the document is likely scanned and needs OCR.
    """
    return len(text.strip()) < settings.ocr_fallback_min_chars
