import json
import re

from backend.headers.pipeline import run_headers


def _page_with_lines(lines):
    text_parts = []
    tokens = []
    cursor = 0
    for idx, line in enumerate(lines):
        if idx:
            text_parts.append("\n")
            cursor += 1
        text_parts.append(line)
        for match in re.finditer(r"\S+", line):
            token_text = match.group(0)
            start = cursor + match.start()
            end = cursor + match.end()
            tokens.append(
                {
                    "text": token_text,
                    "start": start,
                    "end": end,
                    "font_size": 12.0,
                    "bold": True,
                    "indent": 0.0,
                    "line_idx": idx,
                }
            )
        cursor += len(line)
    text = "".join(text_parts)
    lines_meta = []
    for idx, line in enumerate(lines):
        lines_meta.append(
            {
                "index": idx,
                "text": line,
                "para_start": True,
                "virtual_blank_lines_before": 1,
                "list_context": "none",
                "bold": True,
                "style_jump": {"font_delta": 1.0, "bold_flip": True, "left_x_delta": 0.0},
            }
        )
    return {
        "text": text,
        "raw_text": text,
        "tokens": tokens,
        "lines": lines_meta,
    }


def test_appendix_headers_follow_preprocess_truth(tmp_path):
    page6_lines = [
        "A1. Robot & EOAT",
        "A2. Vision/Sensing",
    ]
    page7_lines = [
        "A3. Conveyors & Pallet Handling",
        "A4. Controls & Electrical",
        "A5. Utilities & Consumption",
        "A6. Performance",
        "A7. Layout",
        "A8. Options (pricing separate)",
    ]

    pages = [
        {"text": "", "raw_text": "", "tokens": [], "lines": []}
        for _ in range(5)
    ]
    pages.append(_page_with_lines(page6_lines))
    pages.append(_page_with_lines(page7_lines))

    preprocess_payload = [
        {
            "page": 6,
            "headers": [
                {"line_idx": idx, "text": text}
                for idx, text in enumerate(page6_lines)
            ],
        },
        {
            "page": 7,
            "headers": [
                {"line_idx": idx, "text": text}
                for idx, text in enumerate(page7_lines)
            ],
        },
    ]

    decomp = {
        "pages": pages,
        "preprocess": {"headers": preprocess_payload},
        "output_dir": str(tmp_path),
    }

    result = run_headers("doc", decomp)

    truth_file = tmp_path / "headers_final.json"
    assert truth_file.exists(), "headers_final.json was not written"

    payload = json.loads(truth_file.read_text(encoding="utf-8"))
    truth_rows = payload.get("headers_final") or []

    expected_sequence = page6_lines + page7_lines
    assert [row["text"] for row in truth_rows] == expected_sequence
    assert [row["page"] for row in truth_rows[:2]] == [6, 6]
    assert [row["page"] for row in truth_rows[2:]] == [7] * 6

    assert [row["text"] for row in result.truth] == expected_sequence
    assert len(result.headers) == len(expected_sequence)
