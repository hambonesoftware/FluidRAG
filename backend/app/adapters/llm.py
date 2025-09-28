{
  "file_path": "rag-app/backend/app/adapters/llm.py",
  "language": "python",
  "imported_types": [],
  "imports": [],
  "declared_types": [
    {
      "name": "call_llm",
      "type": "function",
      "line": 1,
      "docstring": "Call configured LLM provider and return parsed result.",
      "modifiers": [],
      "decorators": [],
      "extends": [],
      "args": [
        {
          "name": "system",
          "type": "str",
          "default": null
        },
        {
          "name": "user",
          "type": "str",
          "default": null
        },
        {
          "name": "context",
          "type": "str",
          "default": null
        }
      ],
      "returns": {
        "type": "Any",
        "description": ""
      },
      "members": []
    },
    {
      "name": "LLMClient",
      "type": "class",
      "line": 1,
      "docstring": "Provider-agnostic LLM client with retries.",
      "modifiers": [],
      "decorators": [],
      "extends": [],
      "args": [],
      "returns": null,
      "members": [
        {
          "name": "__init__",
          "type": "function",
          "line": 1,
          "docstring": "Init client",
          "modifiers": [],
          "decorators": [],
          "extends": [],
          "args": [
            {
              "name": "self",
              "type": "LLMClient"
            },
            {
              "name": "provider",
              "type": "str",
              "default": "openai"
            },
            {
              "name": "api_key",
              "type": "str|None"
            }
          ],
          "returns": {
            "type": "None",
            "description": ""
          },
          "members": []
        },
        {
          "name": "chat",
          "type": "function",
          "line": 1,
          "docstring": "Chat completion with retry policy",
          "modifiers": [],
          "decorators": [],
          "extends": [],
          "args": [
            {
              "name": "self",
              "type": "LLMClient"
            },
            {
              "name": "system",
              "type": "str"
            },
            {
              "name": "user",
              "type": "str"
            },
            {
              "name": "context",
              "type": "str"
            },
            {
              "name": "temperature",
              "type": "float",
              "default": 0.0
            },
            {
              "name": "max_tokens",
              "type": "int",
              "default": 1024
            }
          ],
          "returns": {
            "type": "dict",
            "description": ""
          },
          "members": []
        },
        {
          "name": "embed",
          "type": "function",
          "line": 1,
          "docstring": "Batch embed via provider",
          "modifiers": [],
          "decorators": [],
          "extends": [],
          "args": [
            {
              "name": "self",
              "type": "LLMClient"
            },
            {
              "name": "texts",
              "type": "list[str]"
            }
          ],
          "returns": {
            "type": "list[list[float]]",
            "description": ""
          },
          "members": []
        }
      ]
    }
  ]
}