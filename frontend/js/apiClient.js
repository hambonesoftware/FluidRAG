{
  "file_path": "rag-app/frontend/js/apiClient.js",
  "language": "javascript",
  "imported_types": [],
  "imports": [],
  "declared_types": [
    {
      "name": "ApiClient",
      "type": "class",
      "line": 1,
      "docstring": "Fetch wrapper for orchestrator endpoints.",
      "modifiers": [],
      "decorators": [],
      "extends": [],
      "args": [],
      "returns": null,
      "members": [
        {
          "name": "constructor",
          "type": "function",
          "line": 1,
          "docstring": "Initialize with base URL.",
          "modifiers": [],
          "decorators": [],
          "extends": [],
          "args": [
            {
              "name": "self",
              "type": "ApiClient",
              "default": null
            },
            {
              "name": "{ baseUrl }",
              "type": "Object",
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
          "name": "runPipeline",
          "type": "function",
          "line": 1,
          "docstring": "POST pipeline run.",
          "modifiers": [],
          "decorators": [],
          "extends": [],
          "args": [
            {
              "name": "{ fileId, fileName }",
              "type": "Object",
              "default": null
            }
          ],
          "returns": {
            "type": "Promise<any>",
            "description": ""
          },
          "members": []
        },
        {
          "name": "status",
          "type": "function",
          "line": 1,
          "docstring": "GET status.",
          "modifiers": [],
          "decorators": [],
          "extends": [],
          "args": [
            {
              "name": "docId",
              "type": "string",
              "default": null
            }
          ],
          "returns": {
            "type": "Promise<any>",
            "description": ""
          },
          "members": []
        },
        {
          "name": "results",
          "type": "function",
          "line": 1,
          "docstring": "GET results.",
          "modifiers": [],
          "decorators": [],
          "extends": [],
          "args": [
            {
              "name": "docId",
              "type": "string",
              "default": null
            }
          ],
          "returns": {
            "type": "Promise<any>",
            "description": ""
          },
          "members": []
        }
      ]
    }
  ]
}