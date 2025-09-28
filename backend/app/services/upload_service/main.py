{
  "file_path": "rag-app/backend/app/services/upload_service/main.py",
  "language": "python",
  "imported_types": [],
  "imports": [],
  "declared_types": [
    {
      "name": "NormalizedDoc",
      "type": "class",
      "line": 1,
      "docstring": "Normalized document artifact.",
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
      "name": "ensure_normalized",
      "type": "function",
      "line": 1,
      "docstring": "Validate/normalize upload and emit normalize.json",
      "modifiers": [],
      "decorators": [],
      "extends": [],
      "args": [
        {
          "name": "file_id",
          "type": "Optional[str]",
          "default": null
        },
        {
          "name": "file_name",
          "type": "Optional[str]",
          "default": null
        }
      ],
      "returns": {
        "type": "NormalizedDoc",
        "description": ""
      },
      "members": []
    }
  ]
}