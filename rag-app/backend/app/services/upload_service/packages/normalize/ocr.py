"""OCR fallback using pytesseract if available."""
from __future__ import annotations

from typing import List


def try_ocr_if_needed(content: bytes) -> List[str]:
    try:
        from PIL import Image  # type: ignore
        import pytesseract  # type: ignore
        import io

        image = Image.open(io.BytesIO(content))
        text = pytesseract.image_to_string(image)
        return [text.strip()]
    except Exception:
        return []
