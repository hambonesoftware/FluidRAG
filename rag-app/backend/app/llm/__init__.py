"""OpenRouter client helpers."""

from .clients.openrouter import (
    OpenRouterAuthError as ClientAuthError,
)
from .clients.openrouter import (
    OpenRouterError,
    OpenRouterStreamError,
    chat_stream_async,
    chat_sync,
    embed_sync,
)
from .clients.openrouter import (
    OpenRouterHTTPError as ClientHTTPError,
)
from .openrouter import OpenRouterAuthError, OpenRouterHTTPError, chat
from .utils import log_prompt, windows_curl
from .utils.envsafe import mask_bearer, masked_headers, openrouter_headers

__all__ = [
    "chat",
    "chat_sync",
    "chat_stream_async",
    "embed_sync",
    "windows_curl",
    "log_prompt",
    "mask_bearer",
    "openrouter_headers",
    "masked_headers",
    "OpenRouterError",
    "OpenRouterAuthError",
    "OpenRouterHTTPError",
    "ClientAuthError",
    "ClientHTTPError",
    "OpenRouterStreamError",
]
