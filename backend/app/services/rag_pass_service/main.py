{
  "file_path": "rag-app/backend/app/services/rag_pass_service/main.py",
  "language": "python",
  "imported_types": [],
  "imports": [],
  "declared_types": [
    {
      "name": "PassJobs",
      "type": "class",
      "line": 1,
      "docstring": "Pass job identifiers or artifact paths.",
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
      "docstring": "Execute five domain passes asynchronously.",
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
        "type": "PassJobs",
        "description": ""
      },
      "members": []
    }
  ]
}