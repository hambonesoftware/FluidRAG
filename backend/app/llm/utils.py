{
  "file_path": "rag-app/backend/app/llm/utils.py",
  "language": "python",
  "imported_types": [],
  "imports": [],
  "declared_types": [
    {
      "name": "windows_curl",
      "type": "function",
      "line": 1,
      "docstring": "Build Windows-friendly curl command.",
      "modifiers": [],
      "decorators": [],
      "extends": [],
      "args": [
        {
          "name": "url",
          "type": "str"
        },
        {
          "name": "headers",
          "type": "Dict[str, str]"
        },
        {
          "name": "payload",
          "type": "Dict[str, Any]"
        }
      ],
      "returns": {
        "type": "str",
        "description": ""
      },
      "members": []
    },
    {
      "name": "log_prompt",
      "type": "function",
      "line": 1,
      "docstring": "Build compact request meta for logging.",
      "modifiers": [],
      "decorators": [],
      "extends": [],
      "args": [
        {
          "name": "prefix",
          "type": "str"
        },
        {
          "name": "payload",
          "type": "Dict[str, Any]"
        },
        {
          "name": "hdrs",
          "type": "Dict[str, str]"
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