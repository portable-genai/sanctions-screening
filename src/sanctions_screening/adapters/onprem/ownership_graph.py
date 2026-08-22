"""On-prem OwnershipGraphPort: fail-fast portability placeholder (the sovereign-exit proof).

A client running on its own infrastructure binds its own beneficial-ownership source here. The
placeholder refuses rather than returning an empty graph: an empty graph reads as "no owners",
and screening would then miss an owner on a list because a seam was left unimplemented.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import OwnershipGraph


class OnPremOwnershipGraphAdapter:
    """Satisfies OwnershipGraphPort but refuses: bind the client's own ownership source."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def resolve(
        self, subject_id: str, subject_name: str, *, tenant: str, as_of: str = ""
    ) -> OwnershipGraph:
        raise NotImplementedError(
            "on-prem ownership resolution is a portability placeholder: bind the client's own "
            "beneficial-ownership source (see docs/onprem-migration.md). Returning an empty "
            "graph would hide an owner on a list, so this seam refuses instead."
        )
