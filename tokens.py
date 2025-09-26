"""Tokenizer utilities with optional tiktoken support."""
from __future__ import annotations

from typing import List

try:
    import tiktoken  # type: ignore

    _enc = tiktoken.get_encoding("cl100k_base")

    def encode(text: str) -> List[int]:
        """Encode ``text`` into token IDs using ``tiktoken``.

        Falls back to a deterministic estimate if tiktoken is unavailable.
        """

        return _enc.encode(text, disallowed_special=())

except Exception:  # pragma: no cover - exercised when tiktoken missing

    def encode(text: str) -> List[int]:
        """Return a deterministic approximate tokenisation for ``text``.

        ``tiktoken`` is optional in the runtime environment. When it's not
        installed we approximate tokens assuming roughly four characters per
        token. The concrete values are irrelevant—callers only rely on the
        counts and ordering, which remain deterministic for a given input.
        """

        approx = max(1, len(text) // 4)
        return list(range(approx))


__all__ = ["encode"]
