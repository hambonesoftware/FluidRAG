{
  "file_path": "rag-app/backend/app/services/parser_service/parser_controller.py",
  "language": "python",
  "imported_types": [],
  "imports": [],
  "declared_types": [
    {
      "name": "ParseInternal",
      "type": "class",
      "line": 1,
      "docstring": "Internal parsed artifact descriptor.",
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
      "docstring": "Controller: async fan-out of parse subtasks; fan-in, merge, write JSON.",
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
        "type": "ParseInternal",
        "description": ""
      },
      "members": []
    },
    {
      "name": "handle_parser_errors",
      "type": "function",
      "line": 1,
      "docstring": "Normalize and raise parser errors.",
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