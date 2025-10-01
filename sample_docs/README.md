# Sample Documents

Binary sample PDFs are not tracked in this repository. The integration tests
create a minimal placeholder `Epf, Co.pdf` on demand under this directory so the
upload pipeline has a deterministic input.

To materialize the sample manually, run:

```bash
python - <<'PY'
from tests.integration.test_upload_epf_co import _ensure_sample_pdf
_ensure_sample_pdf()
PY
```
