{
  "file_path": "rag-app/backend/app/util/retry.py",
  "language": "python",
  "imported_types": [],
  "imports": [],
  "declared_types": [
    {
      "name": "RetryPolicy",
      "type": "class",
      "line": 1,
      "docstring": "Configurable retry policy with backoff.",
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
          "docstring": "Initialize policy",
          "modifiers": [],
          "decorators": [],
          "extends": [],
          "args": [
            {
              "name": "self",
              "type": "RetryPolicy"
            },
            {
              "name": "retries",
              "type": "int",
              "default": 3
            },
            {
              "name": "base_delay",
              "type": "float",
              "default": 0.5
            },
            {
              "name": "max_delay",
              "type": "float",
              "default": 8.0
            },
            {
              "name": "jitter",
              "type": "bool",
              "default": true
            }
          ],
          "returns": {
            "type": "None",
            "description": ""
          },
          "members": []
        },
        {
          "name": "sleep_durations",
          "type": "function",
          "line": 1,
          "docstring": "Yield backoff durations",
          "modifiers": [],
          "decorators": [],
          "extends": [],
          "args": [
            {
              "name": "self",
              "type": "RetryPolicy"
            }
          ],
          "returns": {
            "type": "Iterable[float]",
            "description": ""
          },
          "members": []
        }
      ]
    },
    {
      "name": "CircuitBreaker",
      "type": "class",
      "line": 1,
      "docstring": "Simple circuit breaker.",
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
          "docstring": "Init",
          "modifiers": [],
          "decorators": [],
          "extends": [],
          "args": [
            {
              "name": "self",
              "type": "CircuitBreaker"
            },
            {
              "name": "fail_threshold",
              "type": "int",
              "default": 5
            },
            {
              "name": "reset_timeout",
              "type": "float",
              "default": 30.0
            }
          ],
          "returns": {
            "type": "None",
            "description": ""
          },
          "members": []
        },
        {
          "name": "call",
          "type": "function",
          "line": 1,
          "docstring": "Protect call with breaker",
          "modifiers": [],
          "decorators": [],
          "extends": [],
          "args": [
            {
              "name": "self",
              "type": "CircuitBreaker"
            },
            {
              "name": "fn",
              "type": "Callable"
            },
            {
              "name": "*args",
              "type": "Any"
            },
            {
              "name": "**kwargs",
              "type": "Any"
            }
          ],
          "returns": {
            "type": "Any",
            "description": ""
          },
          "members": []
        }
      ]
    },
    {
      "name": "with_retries",
      "type": "function",
      "line": 1,
      "docstring": "Execute with retries/backoff and optional circuit breaker",
      "modifiers": [],
      "decorators": [],
      "extends": [],
      "args": [
        {
          "name": "fn",
          "type": "Callable"
        },
        {
          "name": "exceptions",
          "type": "tuple"
        },
        {
          "name": "policy",
          "type": "RetryPolicy|None"
        },
        {
          "name": "breaker",
          "type": "CircuitBreaker|None"
        },
        {
          "name": "*args",
          "type": "Any"
        },
        {
          "name": "**kwargs",
          "type": "Any"
        }
      ],
      "returns": {
        "type": "Any",
        "description": ""
      },
      "members": []
    }
  ]
}