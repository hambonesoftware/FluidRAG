from __future__ import annotations

from pathlib import Path

from ...services.upload_service import ensure_normalized


def test_test_upload(tmp_path: Path) -> None:
    sample_path = Path(__file__).resolve().parents[2] / "data" / "sample.pdf"
    content = sample_path.read_bytes()
    result = ensure_normalized(
        file_name="sample.pdf",
        content=content,
        content_type="application/pdf",
    )
    assert result.doc_id
    assert result.manifest_path
    manifest = Path(result.manifest_path)
    assert manifest.exists()
