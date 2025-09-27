from backend.headers import llm_header_pass


def test_run_llm_header_pass_invalid_json(monkeypatch):
    def fake_call(_text: str) -> str:
        return "not json"

    monkeypatch.setattr(llm_header_pass, "call_llm", fake_call)

    result = llm_header_pass.run_llm_header_pass("sample text")
    assert result["parse_error"] is not None
    assert "EXPECTING" in result["parse_error"].upper()
    assert result["candidates"] == []
    assert isinstance(result["raw_response"], str)
