{
  "file_path": "rag-app/backend/app/services/header_service/main.py",
  "language": "python",
  "imported_types": [],
  "imports": [],
  "declared_types": [
    {
      "name": "HeaderJoinResult",
      "type": "class",
      "line": 1,
      "docstring": "Header and rechunking outputs.",
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
      "name": "join_and_rechunk",
      "type": "function",
      "line": 1,
      "docstring": "Heuristics+LLM headers, sequence repair, section rechunk.",
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
          "name": "chunks_artifact",
          "type": "str",
          "default": null
        }
      ],
      "returns": {
        "type": "HeaderJoinResult",
        "description": ""
      },
      "members": []
    }
  ]
}