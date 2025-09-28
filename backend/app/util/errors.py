{
  "file_path": "rag-app/backend/app/util/errors.py",
  "language": "python",
  "imported_types": [],
  "imports": [],
  "declared_types": [
    {
      "name": "AppError",
      "type": "class",
      "line": 1,
      "docstring": "Base application error.",
      "modifiers": [],
      "decorators": [],
      "extends": [
        "Exception"
      ],
      "args": [],
      "returns": null,
      "members": []
    },
    {
      "name": "ValidationError",
      "type": "class",
      "line": 1,
      "docstring": "Input validation error.",
      "modifiers": [],
      "decorators": [],
      "extends": [
        "AppError"
      ],
      "args": [],
      "returns": null,
      "members": []
    },
    {
      "name": "NotFoundError",
      "type": "class",
      "line": 1,
      "docstring": "Resource not found.",
      "modifiers": [],
      "decorators": [],
      "extends": [
        "AppError"
      ],
      "args": [],
      "returns": null,
      "members": []
    },
    {
      "name": "ExternalServiceError",
      "type": "class",
      "line": 1,
      "docstring": "Downstream service failure.",
      "modifiers": [],
      "decorators": [],
      "extends": [
        "AppError"
      ],
      "args": [],
      "returns": null,
      "members": []
    },
    {
      "name": "RetryExhaustedError",
      "type": "class",
      "line": 1,
      "docstring": "Retries exhausted.",
      "modifiers": [],
      "decorators": [],
      "extends": [
        "AppError"
      ],
      "args": [],
      "returns": null,
      "members": []
    }
  ]
}