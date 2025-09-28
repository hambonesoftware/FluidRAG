```mermaid
sequenceDiagram
    autonumber
    participant UI as Frontend (MVVM)
    participant ORCH as Orchestrator (routes/orchestrator)
    participant UP_MAIN as Upload Service (main.py)
    participant UP_CTRL as Upload Controller
    participant PAR_MAIN as Parser Service (main.py)
    participant PAR_CTRL as Parser Controller
    participant CH_MAIN as Chunk Service (main.py)
    participant CH_CTRL as Chunk Controller
    participant HD_MAIN as Header Service (main.py)
    participant HD_CTRL as Header Controller
    participant PASS_MAIN as RAG Pass Service (main.py)
    participant PASS_CTRL as Passes Controller
    participant VEC as Adapters: vectors
    participant STO as Adapters: storage
    participant LLM as OpenRouter Client

    UI->>ORCH: POST /pipeline/run {file_id|file_name}
    ORCH->>UP_MAIN: ensure_normalized()
    UP_MAIN->>UP_CTRL: ensure_normalized()
    UP_CTRL->>STO: write_json(normalize.json)
    UP_CTRL-->>UP_MAIN: NormalizedDoc
    UP_MAIN-->>ORCH: NormalizedDoc

    ORCH->>PAR_MAIN: parse_and_enrich(doc_id, normalize_artifact)
    PAR_MAIN->>PAR_CTRL: parse_and_enrich(...)
    par PAR fan-out
        PAR_CTRL->>+PAR_CTRL: detect_language()
        PAR_CTRL->>+PAR_CTRL: extract_text_blocks()
        PAR_CTRL->>+PAR_CTRL: extract_tables()
        PAR_CTRL->>+PAR_CTRL: extract_images()
        PAR_CTRL->>+PAR_CTRL: extract_links()
        PAR_CTRL->>+PAR_CTRL: maybe_ocr()
    and PAR fan-in
        PAR_CTRL->>+PAR_CTRL: build_reading_order()
        PAR_CTRL->>+PAR_CTRL: infer_semantics()
        PAR_CTRL->>+PAR_CTRL: detect_lists_bullets()
        PAR_CTRL->>STO: write_json(parse.enriched.json)
    end
    PAR_CTRL-->>PAR_MAIN: ParseResult
    PAR_MAIN-->>ORCH: ParseResult

    ORCH->>CH_MAIN: run_uf_chunking(doc_id, parse_artifact)
    CH_MAIN->>CH_CTRL: run_uf_chunking(...)
    CH_CTRL->>+CH_CTRL: split_sentences()
    CH_CTRL->>+CH_CTRL: extract_typography()
    CH_CTRL->>+CH_CTRL: uf_chunk()
    CH_CTRL->>STO: write_jsonl(uf_chunks.jsonl)
    CH_CTRL->>VEC: build_local_index()
    CH_CTRL-->>CH_MAIN: ChunkResult
    CH_MAIN-->>ORCH: ChunkResult

    ORCH->>HD_MAIN: join_and_rechunk(doc_id, chunks_artifact)
    HD_MAIN->>HD_CTRL: join_and_rechunk(...)
    HD_CTRL->>+HD_CTRL: find_header_candidates()
    HD_CTRL->>+HD_CTRL: score_typo()
    HD_CTRL->>+HD_CTRL: stitch_headers()
    HD_CTRL->>+HD_CTRL: repair_sequence()
    HD_CTRL->>+HD_CTRL: rechunk_by_headers()
    HD_CTRL->>STO: write_json(headers.json); write_jsonl(header_chunks.jsonl)
    HD_CTRL-->>HD_MAIN: HeaderJoinResult
    HD_MAIN-->>ORCH: HeaderJoinResult

    ORCH->>PASS_MAIN: run_all(doc_id, rechunk_artifact)
    PASS_MAIN->>PASS_CTRL: run_all(...)
    PASS_CTRL->>STO: read_jsonl(header_chunks.jsonl)
    PASS_CTRL->>VEC: retrieve_ranked()  Note right of VEC: BM25 + Dense + hybrid
    PASS_CTRL->>LLM: chat_sync() per prompt\n(5 structured passes)
    PASS_CTRL->>STO: write_pass_results(pass_i.json)
    PASS_CTRL-->>PASS_MAIN: PassJobs
    PASS_MAIN-->>ORCH: PassJobs

    ORCH-->>UI: 200 {artifacts, passes}
```
