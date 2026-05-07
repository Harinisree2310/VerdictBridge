"""
VerdictBridge – PDF ingestion service.

Uses PyMuPDF (fitz) for:
  - Native text extraction with bounding-box coordinates per word/block
  - Page rendering to images (for OCR fallback)
  - Passage search (for source highlighting after LLM extraction)
"""
from __future__ import annotations
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


@dataclass
class PageBlock:
    """A block of text on a single PDF page with its bounding box."""
    page: int           # 1-indexed
    text: str
    bbox: tuple[float, float, float, float]  # (x0, y0, x1, y1)
    block_no: int


@dataclass
class PDFContent:
    page_count: int
    full_text: str
    blocks: list[PageBlock] = field(default_factory=list)


def extract_content(file_path: str) -> PDFContent:
    """
    Extract text and bounding-box blocks from a PDF.

    Returns a PDFContent with:
      - full_text: concatenated text across all pages
      - blocks: list of PageBlock objects (for source highlighting)
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {file_path}")

    blocks: list[PageBlock] = []
    page_texts: list[str] = []

    with fitz.open(str(path)) as doc:
        page_count = len(doc)
        for page_idx, page in enumerate(doc):
            page_num = page_idx + 1
            raw_blocks = page.get_text("blocks")  # list of (x0,y0,x1,y1,text,block_no,block_type)
            page_text_parts = []
            for b in raw_blocks:
                x0, y0, x1, y1, text, block_no, block_type = b
                if block_type == 0 and text.strip():  # type 0 = text block
                    blocks.append(PageBlock(
                        page=page_num,
                        text=text.strip(),
                        bbox=(x0, y0, x1, y1),
                        block_no=block_no,
                    ))
                    page_text_parts.append(text.strip())
            page_texts.append("\n".join(page_text_parts))

    full_text = "\n\n".join(t for t in page_texts if t)
    return PDFContent(page_count=page_count, full_text=full_text, blocks=blocks)


def find_passage_bbox(
    file_path: str,
    passage: str,
    max_pages: int = 50,
) -> Optional[dict]:
    """
    Search for a text passage in the PDF and return its location.

    Returns:
        {"page": int, "bbox": (x0, y0, x1, y1), "source_text": str}
        or None if not found.
    """
    if not passage or len(passage.strip()) < 10:
        return None

    # Use first 60 chars of passage as search needle (robust to minor OCR diffs)
    needle = passage.strip()[:60]

    try:
        with fitz.open(file_path) as doc:
            for page_idx, page in enumerate(doc):
                if page_idx >= max_pages:
                    break
                hits = page.search_for(needle)
                if hits:
                    rect = hits[0]
                    return {
                        "page": page_idx + 1,
                        "bbox": (rect.x0, rect.y0, rect.x1, rect.y1),
                        "source_text": passage.strip()[:500],
                    }
    except Exception as exc:
        logger.warning("Passage search failed: %s", exc)

    return None


def render_pages_to_images(file_path: str, dpi: int = 150) -> list[bytes]:
    """
    Render each page to a PNG image (bytes).
    Used as input to the OCR fallback pipeline.
    """
    images: list[bytes] = []
    with fitz.open(file_path) as doc:
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        for page in doc:
            pix = page.get_pixmap(matrix=mat, colorspace=fitz.csGRAY)
            images.append(pix.tobytes("png"))
    return images


def get_page_count(file_path: str) -> int:
    with fitz.open(file_path) as doc:
        return len(doc)
