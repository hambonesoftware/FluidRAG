{
  "file_path": "rag-app/backend/app/llm/utils/envsafe.py",
  "language": "python",
  "imported_types": [],
  "imports": [],
  "declared_types": [
    {
      "name": "mask_bearer",
      "type": "function",
      "line": 1,
      "docstring": "Mask bearer tokens for logs.",
      "modifiers": [],
      "decorators": [],
      "extends": [],
      "args": [
        {
          "name": "token",
          "type": "str | None"
        }
      ],
      "returns": {
        "type": "str",
        "description": ""
      },
      "members": []
    },
    {
      "name": "openrouter_headers",
      "type": "function",
      "line": 1,
      "docstring": "Build OpenRouter headers from env.",
      "modifiers": [],
      "decorators": [],
      "extends": [],
      "args": [],
      "returns": {
        "type": "Dict[str, str]",
        "description": ""
      },
      "members": []
    },
    {
      "name": "masked_headers",
      "type": "function",
      "line": 1,
      "docstring": "Return a copy with Authorization masked.",
      "modifiers": [],
      "decorators": [],
      "extends": [],
      "args": [
        {
          "name": "headers",
          "type": "Dict[str, str]"
        }
      ],
      "returns": {
        "type": "Dict[str, str]",
        "description": ""
      },
      "members": []
    }
  ]
}