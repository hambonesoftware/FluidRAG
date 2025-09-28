{
  "file_path": "rag-app/backend/app/services/parser_service/packages/merge/merger.py",
  "language": "python",
  "imported_types": [],
  "imports": [],
  "declared_types": [
    {
      "name": "merge_all",
      "type": "function",
      "line": 1,
      "docstring": "Merge parsing facets into a single enriched artifact.",
      "modifiers": [],
      "decorators": [],
      "extends": [],
      "args": [
        {
          "name": "doc_id",
          "type": "str",
          "default": null
        },
        {
          "name": "language",
          "type": "Dict[str, Any]",
          "default": null
        },
        {
          "name": "text_blocks",
          "type": "List[Dict[str, Any]]",
          "default": null
        },
        {
          "name": "tables",
          "type": "List[Dict[str, Any]]",
          "default": null
        },
        {
          "name": "images",
          "type": "List[Dict[str, Any]]",
          "default": null
        },
        {
          "name": "links",
          "type": "List[Dict[str, Any]]",
          "default": null
        },
        {
          "name": "ocr_layer",
          "type": "Dict[str, Any]",
          "default": null
        },
        {
          "name": "reading_order",
          "type": "List[int]",
          "default": null
        },
        {
          "name": "semantics",
          "type": "List[Dict[str, Any]]",
          "default": null
        },
        {
          "name": "lists",
          "type": "List[Dict[str, Any]]",
          "default": null
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