{
  "file_path": "rag-app/backend/app/services/parser_service/main.py",
  "language": "python",
  "imported_types": [],
  "imports": [],
  "declared_types": [
    {
      "name": "ParseResult",
      "type": "class",
      "line": 1,
      "docstring": "Parser enriched artifact.",
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
      "name": "parse_and_enrich",
      "type": "function",
      "line": 1,
      "docstring": "Fan-out/fan-in parser; returns enriched parse path.",
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
        "type": "ParseResult",
        "description": ""
      },
      "members": []
    }
  ]
}