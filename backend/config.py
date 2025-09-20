import os

# Flask / App
PORT = int(os.environ.get("PORT", 5142))
MAX_CONTENT_LENGTH = 50 * 1024 * 1024
STATIC_FOLDER = "../frontend"
STATIC_URL_PATH = ""

# OpenRouter attribution headers (recommended)
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()
OPENROUTER_HTTP_REFERER = (
    os.environ.get("OPENROUTER_HTTP_REFERER")
    or os.environ.get("OPENROUTER_SITE_URL")
    or "http://localhost:5142"
)
OPENROUTER_APP_TITLE = os.environ.get("OPENROUTER_APP_TITLE", "FluidRAG")

# Default provider / model
DEFAULT_PROVIDER = "openrouter"
OPENROUTER_DEFAULT_MODEL = os.environ.get("OPENROUTER_DEFAULT_MODEL", "").strip()

# llama.cpp
LLAMACPP_URL = os.environ.get("LLAMACPP_URL", "http://localhost:8080/v1/chat/completions")
LLAMACPP_DEFAULT_MODEL = os.environ.get("LLAMACPP_DEFAULT_MODEL", "llama.cpp/default")

# Uploads
ALLOWED_EXT = {".pdf", ".docx", ".txt"}
