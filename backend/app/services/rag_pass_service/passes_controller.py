{
  "file_path": "rag-app/backend/app/services/rag_pass_service/passes_controller.py",
  "language": "python",
  "imported_types": [],
  "imports": [],
  "declared_types": [
    {
      "name": "PassJobsInternal",
      "type": "class",
      "line": 1,
      "docstring": "Internal pass job bundle.",
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
      "name": "run_all",
      "type": "function",
      "line": 1,
      "docstring": "Retrieve, compose context, LLM calls, emit results.",
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
          "name": "rechunk_artifact",
          "type": "str",
          "default": null
        }
      ],
      "returns": {
        "type": "PassJobsInternal",
        "description": ""
      },
      "members": []
    },
    {
      "name": "handle_pass_errors",
      "type": "function",
      "line": 1,
      "docstring": "Normalize and raise rag pass errors.",
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