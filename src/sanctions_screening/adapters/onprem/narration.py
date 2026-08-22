"""On-prem NarrationPort: fail-fast portability placeholder.

A client binds its own model here. The seam refuses rather than returning empty prose: the
service would then fall back to its deterministic memo, which is correct, but a placeholder that
silently returned nothing would hide that the client's model was never wired.
"""

from __future__ import annotations

from collections.abc import Mapping

from ...config import Settings


class OnPremNarrationAdapter:
    """Satisfies NarrationPort but refuses: bind the client's own model."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def draft_memo(self, facts: Mapping[str, object]) -> str:
        raise NotImplementedError(
            "on-prem narration is a portability placeholder: bind the client's own model "
            "(see docs/onprem-migration.md)."
        )
