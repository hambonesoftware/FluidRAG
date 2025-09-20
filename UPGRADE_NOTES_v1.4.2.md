# FluidRAG v1.4.2 – Font-size Retention & Style-aware Sectioning

Date: 2025-09-20

- PyMuPDF `get_text('dict')` used to capture **per-line font size/bold/bbox**.
- `page_line_styles[*][*]['font_sigma_rank']` computed per-page (z-score) and passed to `is_header_line(...)`.
- `sections_from_lines(...)` consumes lines + styles to improve header reliability.
