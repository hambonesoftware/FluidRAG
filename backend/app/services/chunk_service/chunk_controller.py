{
  "file_path": "rag-app/backend/app/services/chunk_service/chunk_controller.py",
  "language": "python",
  "imported_types": [],
  "imports": [],
  "declared_types": [
    {
      "name": "ChunkInternal",
      "type": "class",
      "line": 1,
      "docstring": "Internal chunk descriptor.",
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
      "name": "run_uf_chunking",
      "type": "function",
      "line": 1,
      "docstring": "Controller for chunking & local index building.",
      "modifiers": [],
      "decorators": [],
      "extends": [],
      "args": [
        {
          "name": "doc_id",
          "type": "str",
          "default": null
        },
        {
          "name": "normalize_artifact",
          "type": "str",
          "default": null
        }
      ],
      "returns": {
        "type": "ChunkInternal",
        "description": ""
      },
      "members": []
    },
    {
      "name": "handle_chunk_errors",
      "type": "function",
      "line": 1,
      "docstring": "Normalize and raise chunk errors.",
      "modifiers": [],
      "decorators": [],
      "extends": [],
      "args": [
        {
          "name": "e",
          "type": "Exception"
        }
      ],
      "returns": {
        "type": "None",
        "description": ""
      },
      "members": []
    }
  ]
}