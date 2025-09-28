{
  "file_path": "rag-app/backend/app/services/upload_service/upload_controller.py",
  "language": "python",
  "imported_types": [],
  "imports": [],
  "declared_types": [
    {
      "name": "NormalizedDocInternal",
      "type": "class",
      "line": 1,
      "docstring": "Internal normalized result.",
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
      "docstring": "Controller: orchestrates validators, pdf normalize, OCR, manifest & DB.",
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
        "type": "NormalizedDocInternal",
        "description": ""
      },
      "members": []
    },
    {
      "name": "make_doc_id",
      "type": "function",
      "line": 1,
      "docstring": "Generate stable doc_id from inputs/time.",
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
        "type": "str",
        "description": ""
      },
      "members": []
    },
    {
      "name": "handle_upload_errors",
      "type": "function",
      "line": 1,
      "docstring": "Normalize and raise application errors for upload stage.",
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