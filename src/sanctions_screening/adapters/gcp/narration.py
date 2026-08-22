"""Managed NarrationPort: draft the memo with a pinned Gemini model (lazy SDK).

The model restates the engine's bands and arithmetic; it produces no consequential number. The
caller validates the draft against the engine's figures and DISCARDS it on any invented number,
so this adapter is never trusted to be grounded on its own. The SDK import is lazy, so this module
imports on the offline profiles with no cloud SDK present, and that lazy import is the honest
refusal offline.
"""

from __future__ import annotations

from collections.abc import Mapping

from ...config import Settings

#: Pinned model id, region-qualified in the runbook. A floating default is never used.
_MODEL = "gemini-3.5-flash"


class GeminiNarrationAdapter:
    """Draft the disposition memo with a pinned managed model, for the caller to validate."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def draft_memo(self, facts: Mapping[str, object]) -> str:
        from google import genai  # noqa: PLC0415 - lazy so offline imports need no SDK

        _ = (genai, _MODEL, facts)
        raise NotImplementedError(
            "the managed narration model is a deployment concern; configure the Gemini client "
            "and region for the gcp profile. The draft is validated and discarded on any "
            "ungrounded number regardless of the backend."
        )
