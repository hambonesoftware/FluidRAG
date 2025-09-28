{
  "file_path": "rag-app/backend/app/routes/orchestrator.py",
  "language": "python",
  "imported_types": [],
  "imports": [],
  "declared_types": [
    {
      "name": "PipelineRunRequest",
      "type": "class",
      "line": 1,
      "docstring": "Orchestrator pipeline input contract.",
      "modifiers": [],
      "decorators": [],
      "extends": [
        "BaseModel"
      ],
      "args": [],
      "returns": null,
      "members": []
    },
    {
      "name": "run_pipeline",
      "type": "function",
      "line": 1,
      "docstring": "Execute full pipeline: upload→parse→chunk→headers→passes.",
      "modifiers": [],
      "decorators": [],
      "extends": [],
      "args": [
        {
          "name": "req",
          "type": "PipelineRunRequest",
          "default": null
        }
      ],
      "returns": {
        "type": "dict",
        "description": ""
      },
      "members": []
    },
    {
      "name": "status",
      "type": "function",
      "line": 1,
      "docstring": "Aggregate status for given document.",
      "modifiers": [],
      "decorators": [],
      "extends": [],
      "args": [
        {
          "name": "doc_id",
          "type": "str",
          "default": null
        }
      ],
      "returns": {
        "type": "dict",
        "description": ""
      },
      "members": []
    },
    {
      "name": "results",
      "type": "function",
      "line": 1,
      "docstring": "Return artifact manifest for given document.",
      "modifiers": [],
      "decorators": [],
      "extends": [],
      "args": [
        {
          "name": "doc_id",
          "type": "str",
          "default": null
        }
      ],
      "returns": {
        "type": "dict",
        "description": ""
      },
      "members": []
    },
    {
      "name": "stream_artifact",
      "type": "function",
      "line": 1,
      "docstring": "Stream artifact bytes to client using chunked transfer.",
      "modifiers": [],
      "decorators": [],
      "extends": [],
      "args": [
        {
          "name": "path",
          "type": "str"
        }
      ],
      "returns": {
        "type": "StreamingResponse",
        "description": ""
      },
      "members": []
    }
  ]
}