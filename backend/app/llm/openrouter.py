{
  "file_path": "rag-app/backend/app/llm/openrouter.py",
  "language": "python",
  "imported_types": [],
  "imports": [],
  "declared_types": [
    {
      "name": "OpenRouterAuthError",
      "type": "class",
      "line": 1,
      "docstring": "Auth error (401).",
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
      "name": "OpenRouterHTTPError",
      "type": "class",
      "line": 1,
      "docstring": "HTTP/transport error.",
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
      "name": "chat",
      "type": "function",
      "line": 1,
      "docstring": "Synchronous chat call to OpenRouter /chat/completions.",
      "modifiers": [],
      "decorators": [],
      "extends": [],
      "args": [
        {
          "name": "model",
          "type": "str"
        },
        {
          "name": "messages",
          "type": "List[Dict[str, str]]"
        },
        {
          "name": "temperature",
          "type": "float",
          "default": 0.0
        },
        {
          "name": "top_p",
          "type": "float | None"
        },
        {
          "name": "max_tokens",
          "type": "int | None"
        },
        {
          "name": "extra",
          "type": "Dict[str, Any] | None"
        },
        {
          "name": "timeout",
          "type": "float",
          "default": 60.0
        }
      ],
      "returns": {
        "type": "Dict[str, Any]",
        "description": ""
      },
      "members": []
    }
  ]
}