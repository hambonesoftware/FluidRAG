"""Lightweight LLM client wrapper used by the section refinement pipeline."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class LLMResponse:
    """Container for structured LLM responses."""

    content: Any


class LLMClient:
    """Simple placeholder client for invoking an LLM.

    The implementation here is intentionally minimal so that unit tests can
    inject deterministic behaviour.  Production integrations should replace
    the :meth:`refine` method with a real model call and handle authentication
    and retries appropriately.
    """

    def refine(
        self,
        *,
        system_prompt: str,
        user_payload: Dict[str, Any],
        schema: Dict[str, Any],
        granularity_guide: Optional[str] = None,
    ) -> LLMResponse:
        """Call the backing LLM to refine a suspect specification.

        Parameters
        ----------
        system_prompt:
            The shared system instructions provided to the model.
        user_payload:
            The structured user message including context and the suspect row.
        schema:
            The JSON schema responses must follow.
        granularity_guide:
            Optional swimlane-specific instructions.

        Returns
        -------
        LLMResponse
            Wrapper containing the parsed model output.

        Notes
        -----
        The default implementation is a stub and raises ``NotImplementedError``
        so that tests can patch it.  Replace this with a real client when
        wiring the pipeline to an inference endpoint.
        """

        raise NotImplementedError(
            "LLMClient.refine must be implemented with an actual LLM backend."
        )


__all__ = ["LLMClient", "LLMResponse"]

