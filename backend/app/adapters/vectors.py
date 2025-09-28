{
  "file_path": "rag-app/backend/app/adapters/vectors.py",
  "language": "python",
  "imported_types": [],
  "imports": [],
  "declared_types": [
    {
      "name": "EmbeddingModel",
      "type": "class",
      "line": 1,
      "docstring": "Abstraction for embedding backends.",
      "modifiers": [],
      "decorators": [],
      "extends": [],
      "args": [],
      "returns": null,
      "members": [
        {
          "name": "embed_texts",
          "type": "function",
          "line": 1,
          "docstring": "Batch embed texts",
          "modifiers": [],
          "decorators": [],
          "extends": [],
          "args": [
            {
              "name": "self",
              "type": "EmbeddingModel"
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
    },
    {
      "name": "BM25Index",
      "type": "class",
      "line": 1,
      "docstring": "Sparse BM25 index over chunks.",
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
          "docstring": "Init BM25 index",
          "modifiers": [],
          "decorators": [],
          "extends": [],
          "args": [
            {
              "name": "self",
              "type": "BM25Index"
            }
          ],
          "returns": {
            "type": "None",
            "description": ""
          },
          "members": []
        },
        {
          "name": "add",
          "type": "function",
          "line": 1,
          "docstring": "Add docs",
          "modifiers": [],
          "decorators": [],
          "extends": [],
          "args": [
            {
              "name": "self",
              "type": "BM25Index"
            },
            {
              "name": "docs",
              "type": "list[str]"
            }
          ],
          "returns": {
            "type": "None",
            "description": ""
          },
          "members": []
        },
        {
          "name": "search",
          "type": "function",
          "line": 1,
          "docstring": "Search top-k",
          "modifiers": [],
          "decorators": [],
          "extends": [],
          "args": [
            {
              "name": "self",
              "type": "BM25Index"
            },
            {
              "name": "query",
              "type": "str"
            },
            {
              "name": "k",
              "type": "int",
              "default": 20
            }
          ],
          "returns": {
            "type": "list[tuple[int,float]]",
            "description": ""
          },
          "members": []
        }
      ]
    },
    {
      "name": "FaissIndex",
      "type": "class",
      "line": 1,
      "docstring": "Local FAISS dense vector index.",
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
          "docstring": "Create or load index",
          "modifiers": [],
          "decorators": [],
          "extends": [],
          "args": [
            {
              "name": "self",
              "type": "FaissIndex"
            },
            {
              "name": "dim",
              "type": "int"
            },
            {
              "name": "index_path",
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
          "name": "add",
          "type": "function",
          "line": 1,
          "docstring": "Add vectors",
          "modifiers": [],
          "decorators": [],
          "extends": [],
          "args": [
            {
              "name": "self",
              "type": "FaissIndex"
            },
            {
              "name": "vectors",
              "type": "list[list[float]]"
            }
          ],
          "returns": {
            "type": "None",
            "description": ""
          },
          "members": []
        },
        {
          "name": "search",
          "type": "function",
          "line": 1,
          "docstring": "Search top-k",
          "modifiers": [],
          "decorators": [],
          "extends": [],
          "args": [
            {
              "name": "self",
              "type": "FaissIndex"
            },
            {
              "name": "query_vec",
              "type": "list[float]"
            },
            {
              "name": "k",
              "type": "int",
              "default": 20
            }
          ],
          "returns": {
            "type": "list[tuple[int,float]]",
            "description": ""
          },
          "members": []
        },
        {
          "name": "save",
          "type": "function",
          "line": 1,
          "docstring": "Persist index",
          "modifiers": [],
          "decorators": [],
          "extends": [],
          "args": [
            {
              "name": "self",
              "type": "FaissIndex"
            }
          ],
          "returns": {
            "type": "None",
            "description": ""
          },
          "members": []
        }
      ]
    },
    {
      "name": "QdrantIndex",
      "type": "class",
      "line": 1,
      "docstring": "Qdrant remote dense vector index.",
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
          "docstring": "Init client/collection",
          "modifiers": [],
          "decorators": [],
          "extends": [],
          "args": [
            {
              "name": "self",
              "type": "QdrantIndex"
            },
            {
              "name": "collection",
              "type": "str"
            }
          ],
          "returns": {
            "type": "None",
            "description": ""
          },
          "members": []
        },
        {
          "name": "add",
          "type": "function",
          "line": 1,
          "docstring": "Add vectors",
          "modifiers": [],
          "decorators": [],
          "extends": [],
          "args": [
            {
              "name": "self",
              "type": "QdrantIndex"
            },
            {
              "name": "vectors",
              "type": "list[list[float]]"
            },
            {
              "name": "payloads",
              "type": "list[dict]|None"
            }
          ],
          "returns": {
            "type": "None",
            "description": ""
          },
          "members": []
        },
        {
          "name": "search",
          "type": "function",
          "line": 1,
          "docstring": "Search",
          "modifiers": [],
          "decorators": [],
          "extends": [],
          "args": [
            {
              "name": "self",
              "type": "QdrantIndex"
            },
            {
              "name": "query_vec",
              "type": "list[float]"
            },
            {
              "name": "k",
              "type": "int",
              "default": 20
            }
          ],
          "returns": {
            "type": "list[dict]",
            "description": ""
          },
          "members": []
        }
      ]
    },
    {
      "name": "hybrid_search",
      "type": "function",
      "line": 1,
      "docstring": "Fuse sparse+dense scores",
      "modifiers": [],
      "decorators": [],
      "extends": [],
      "args": [
        {
          "name": "bm25",
          "type": "BM25Index|None"
        },
        {
          "name": "dense",
          "type": "FaissIndex|QdrantIndex|None"
        },
        {
          "name": "query",
          "type": "str"
        },
        {
          "name": "query_vec",
          "type": "list[float]|None"
        },
        {
          "name": "alpha",
          "type": "float",
          "default": 0.5
        },
        {
          "name": "k",
          "type": "int",
          "default": 20
        }
      ],
      "returns": {
        "type": "list[dict]",
        "description": ""
      },
      "members": []
    }
  ]
}