{
  "file_path": "rag-app/backend/app/services/chunk_service/main.py",
  "language": "python",
  "imported_types": [],
  "imports": [],
  "declared_types": [
    {
      "name": "ChunkResult",
      "type": "class",
      "line": 1,
      "docstring": "UF chunking result.",
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
      "docstring": "Create UF chunks from enriched parse.",
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
        "type": "ChunkResult",
        "description": ""
      },
      "members": []
    }
  ]
}