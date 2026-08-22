"""Managed AdverseMediaPort: grounded adverse-media search over a managed backend (lazy SDK).

Advisory to the memo, never to the band. The SDK import is inside the method so this module
imports with no cloud SDK present; offline, that lazy import is what refuses, which is the honest
managed-family behaviour (a silent empty answer would be indistinguishable from "no findings").
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import AdverseMediaFinding, PartyKind


class GroundedAdverseMediaAdapter:
    """Query a managed grounded-search backend for adverse media on a name."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def search(
        self, name: str, *, kind: PartyKind = PartyKind.UNKNOWN
    ) -> tuple[AdverseMediaFinding, ...]:
        # Lazy: the managed grounded-search client is absent on the offline profiles, so the
        # import itself is the refusal there. A real deployment configures the backend region.
        from google.cloud import discoveryengine  # noqa: PLC0415

        _ = discoveryengine  # the wiring to the managed index is a deployment concern
        raise NotImplementedError(
            "the managed adverse-media backend is a deployment concern; configure the grounded "
            "search index and region for the gcp profile"
        )
