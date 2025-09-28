{
  "file_path": "rag-app/backend/app/services/header_service/header_controller.py",
  "language": "python",
  "imported_types": [],
  "imports": [],
  "declared_types": [
    {
      "name": "HeaderJoinInternal",
      "type": "class",
      "line": 1,
      "docstring": "Internal header join result.",
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
      "docstring": "Controller: regex/typo scoring, stitching, repair, emit headers & rechunk.",
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
        "type": "HeaderJoinInternal",
        "description": ""
      },
      "members": []
    },
    {
      "name": "handle_header_errors",
      "type": "function",
      "line": 1,
      "docstring": "Normalize and raise header errors.",
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