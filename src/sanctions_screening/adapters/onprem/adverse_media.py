"""On-prem AdverseMediaPort: fail-fast portability placeholder.

Adverse media is advisory, but the seam is still named and refused rather than silently returning
nothing: a client binds its own media source here, and a placeholder that returned an empty tuple
would look identical to a clean search.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import AdverseMediaFinding, PartyKind


class OnPremAdverseMediaAdapter:
    """Satisfies AdverseMediaPort but refuses: bind the client's own media source."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def search(
        self, name: str, *, kind: PartyKind = PartyKind.UNKNOWN
    ) -> tuple[AdverseMediaFinding, ...]:
        raise NotImplementedError(
            "on-prem adverse-media search is a portability placeholder: bind the client's own "
            "media source (see docs/onprem-migration.md)."
        )
