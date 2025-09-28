{
  "file_path": "rag-app/backend/app/adapters/storage.py",
  "language": "python",
  "imported_types": [],
  "imports": [],
  "declared_types": [
    {
      "name": "write_json",
      "type": "function",
      "line": 1,
      "docstring": "Write a JSON file with directories ensured.",
      "modifiers": [],
      "decorators": [],
      "extends": [],
      "args": [
        {
          "name": "path",
          "type": "str",
          "default": null
        },
        {
          "name": "payload",
          "type": "Dict[str, Any]",
          "default": null
        }
      ],
      "returns": {
        "type": "None",
        "description": ""
      },
      "members": []
    },
    {
      "name": "write_jsonl",
      "type": "function",
      "line": 1,
      "docstring": "Write JSONL lines safely.",
      "modifiers": [],
      "decorators": [],
      "extends": [],
      "args": [
        {
          "name": "path",
          "type": "str",
          "default": null
        },
        {
          "name": "rows",
          "type": "Iterable[Dict[str, Any]]",
          "default": null
        }
      ],
      "returns": {
        "type": "None",
        "description": ""
      },
      "members": []
    },
    {
      "name": "read_jsonl",
      "type": "function",
      "line": 1,
      "docstring": "Read JSONL into list of dicts.",
      "modifiers": [],
      "decorators": [],
      "extends": [],
      "args": [
        {
          "name": "path",
          "type": "str",
          "default": null
        }
      ],
      "returns": {
        "type": "list[dict]",
        "description": ""
      },
      "members": []
    },
    {
      "name": "ensure_parent_dirs",
      "type": "function",
      "line": 1,
      "docstring": "Create parent directories if missing.",
      "modifiers": [],
      "decorators": [],
      "extends": [],
      "args": [
        {
          "name": "path",
          "type": "str",
          "default": null
        }
      ],
      "returns": {
        "type": "None",
        "description": ""
      },
      "members": []
    },
    {
      "name": "stream_read",
      "type": "function",
      "line": 1,
      "docstring": "Async stream file bytes in chunks.",
      "modifiers": [],
      "decorators": [],
      "extends": [],
      "args": [
        {
          "name": "path",
          "type": "str"
        },
        {
          "name": "chunk_size",
          "type": "int",
          "default": 65536
        }
      ],
      "returns": {
        "type": "AsyncIterator[bytes]",
        "description": ""
      },
      "members": []
    },
    {
      "name": "stream_write",
      "type": "function",
      "line": 1,
      "docstring": "Async write bytes from stream to file.",
      "modifiers": [],
      "decorators": [],
      "extends": [],
      "args": [
        {
          "name": "path",
          "type": "str"
        },
        {
          "name": "aiter",
          "type": "AsyncIterator[bytes]"
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