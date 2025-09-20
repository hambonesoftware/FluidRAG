class LLMError(RuntimeError):
    """Base exception for LLM client errors."""


class LLMAuthError(LLMError):
    """Raised when an LLM endpoint reports an authorization failure."""


class OpenRouterAuthError(LLMAuthError):
    """Specific alias for OpenRouter auth failures."""
