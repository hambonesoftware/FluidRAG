{
  "file_path": "rag-app/backend/app/services/chunk_service/packages/segment/uf_chunker.py",
  "language": "python",
  "imported_types": [],
  "imports": [],
  "declared_types": [
    {
      "name": "uf_chunk",
      "type": "function",
      "line": 1,
      "docstring": "Produce UF micro-chunks with metadata.",
      "modifiers": [],
      "decorators": [],
      "extends": [],
      "args": [
        {
          "name": "sentences",
          "type": "List[str]",
          "default": null
        },
        {
          "name": "typography",
          "type": "Dict[str, Any]",
          "default": null
        },
        {
          "name": "target_tokens",
          "type": "int",
          "default": null
        },
        {
          "name": "overlap",
          "type": "int",
          "default": null
        }
      ],
      "returns": {
        "type": "List[Dict[str, Any]]",
        "description": ""
      },
      "members": []
    }
  ]
}