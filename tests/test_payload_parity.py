from backend.compat.payload_adapter import to_legacy_llm_message


def test_payload_structure_parity():
    ctx = {
        "Standards": [
            {
                "chunk_id": "s1",
                "doc_id": "docA",
                "section": "1",
                "section_title": "Scope",
                "pages": (1, 2),
                "text": "Clause text",
            }
        ],
        "ProjectSpec": [
            {
                "chunk_id": "p1",
                "doc_id": "docB",
                "section": "2",
                "section_title": "Requirements",
                "pages": (3, 3),
                "text": "Project requirement",
            }
        ],
        "Risk": [],
    }
    question = "What are the requirements?"
    payload = to_legacy_llm_message(ctx, question)
    assert list(payload.keys()) == ["messages"]
    assert payload["messages"][0]["role"] == "system"
    assert "[Standards]" in payload["messages"][1]["content"]
    assert "[ProjectSpec]" in payload["messages"][1]["content"]
    assert "Project requirement" in payload["messages"][1]["content"]
