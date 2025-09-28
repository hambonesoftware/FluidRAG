# Phase 8 — Frontend MVVM & Streaming Results (Light)

## Goals
- Minimal UI to upload, run pipeline, stream updates, and download artifacts.

## Scope
- Models/ViewModels (UploadVM, PipelineVM) + Views (Upload, Pipeline, Results).
- API client for `/pipeline/run`, `/status`, `/results`, `/artifact`.
- Progress polling; optional SSE/WebSocket later.

## Deliverables
- Usable dev UI for local workflows.
- Styling can be minimal; the focus is backend completeness.
