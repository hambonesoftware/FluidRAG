"""Image extraction helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .....util.logging import get_logger

logger = get_logger(__name__)


def extract_images(normalized: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract images & captions."""

    source_path = normalized.get("source", {}).get("path")
    extracted: list[dict[str, Any]] = []

    if source_path and Path(source_path).exists():
        try:
            import fitz  # type: ignore

            with fitz.open(source_path) as document:
                for page_index, page in enumerate(document, start=1):
                    for image_index, info in enumerate(page.get_images(full=True), start=1):
                        xref = info[0]
                        try:
                            base = document.extract_image(xref)
                        except Exception:  # pragma: no cover - corrupt image entry
                            base = {"image": b"", "width": info[2], "height": info[3], "ext": None}
                        extracted.append(
                            {
                                "id": f"{normalized['doc_id']}:p{page_index}:img{image_index}",
                                "page": page_index,
                                "width": base.get("width", info[2]),
                                "height": base.get("height", info[3]),
                                "ext": base.get("ext"),
                                "size_bytes": len(base.get("image", b"")),
                            }
                        )
        except Exception as exc:  # pragma: no cover - dependency failure
            logger.warning(
                "parser.extract_images.failed",
                extra={"path": source_path, "error": str(exc)},
            )

    for page in normalized.get("pages", []):
        for image in page.get("images", []):
            image_id = image.get("id")
            entry = next((item for item in extracted if item["id"] == image_id), None)
            if entry is None:
                entry = {
                    "id": image_id,
                    "page": page.get("page_number", 0),
                    "size_bytes": 0,
                }
                extracted.append(entry)
            entry["description"] = image.get("description", "")
    return extracted
