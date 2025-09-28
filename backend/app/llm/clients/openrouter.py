{
  "file_path": "rag-app/backend/app/llm/clients/openrouter.py",
  "language": "python",
  "imported_types": [],
  "imports": [],
  "declared_types": [
    {
      "name": "OpenRouterError",
      "type": "class",
      "line": 1,
      "docstring": "Base error.",
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
      "name": "OpenRouterAuthError",
      "type": "class",
      "line": 1,
      "docstring": "401 error.",
      "modifiers": [],
      "decorators": [],
      "extends": [
        "OpenRouterError"
      ],
      "args": [],
      "returns": null,
      "members": []
    },
    {
      "name": "OpenRouterHTTPError",
      "type": "class",
      "line": 1,
      "docstring": "HTTP status/transport error.",
      "modifiers": [],
      "decorators": [],
      "extends": [
        "OpenRouterError"
      ],
      "args": [],
      "returns": null,
      "members": []
    },
    {
      "name": "OpenRouterStreamError",
      "type": "class",
      "line": 1,
      "docstring": "Streaming idle/format error.",
      "modifiers": [],
      "decorators": [],
      "extends": [
        "OpenRouterError"
      ],
      "args": [],
      "returns": null,
      "members": []
    },
    {
      "name": "_backoff",
      "type": "function",
      "line": 1,
      "docstring": "Yield jittered backoff durations.",
      "modifiers": [],
      "decorators": [],
      "extends": [],
      "args": [
        {
          "name": "retries",
          "type": "int",
          "default": 3
        },
        {
          "name": "base",
          "type": "float",
          "default": 0.5
        },
        {
          "name": "max_delay",
          "type": "float",
          "default": 8.0
        }
      ],
      "returns": {
        "type": "Iterable[float]",
        "description": ""
      },
      "members": []
    },
    {
      "name": "chat_sync",
      "type": "function",
      "line": 1,
      "docstring": "Sync chat with retries and masked logging.",
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
        },
        {
          "name": "retries",
          "type": "int",
          "default": 3
        }
      ],
      "returns": {
        "type": "Dict[str, Any]",
        "description": ""
      },
      "members": []
    },
    {
      "name": "chat_stream_async",
      "type": "function",
      "line": 1,
      "docstring": "Async SSE streaming, yields deltas/meta/done.",
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
        },
        {
          "name": "retries",
          "type": "int",
          "default": 3
        },
        {
          "name": "idle_timeout",
          "type": "float",
          "default": 30.0
        }
      ],
      "returns": {
        "type": "AsyncGenerator[Dict[str, Any], None]",
        "description": ""
      },
      "members": []
    },
    {
      "name": "embed_sync",
      "type": "function",
      "line": 1,
      "docstring": "Sync embeddings with retries.",
      "modifiers": [],
      "decorators": [],
      "extends": [],
      "args": [
        {
          "name": "model",
          "type": "str"
        },
        {
          "name": "inputs",
          "type": "List[str]"
        },
        {
          "name": "timeout",
          "type": "float",
          "default": 60.0
        },
        {
          "name": "retries",
          "type": "int",
          "default": 3
        }
      ],
      "returns": {
        "type": "List[List[float]]",
        "description": ""
      },
      "members": []
    }
  ]
}