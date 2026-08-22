"""AdverseMediaPort: severity-ordered adverse-media findings, each carrying a MEDIA citation.

Advisory to the disposition MEMO, never to the band. The match band and the recommendation are
the deterministic engine's alone; adverse media enriches the narrative a reviewer reads, and the
eval pins that the bands are unchanged when this port is stubbed empty. Families: managed
(Grounding / Deep Research, lazy SDK), local fixture, onprem fail-fast.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.models import AdverseMediaFinding, PartyKind


@runtime_checkable
class AdverseMediaPort(Protocol):
    def search(
        self, name: str, *, kind: PartyKind = PartyKind.UNKNOWN
    ) -> tuple[AdverseMediaFinding, ...]:
        """Return adverse-media findings for a name, most severe first (possibly empty).

        Empty is a valid answer (no adverse media found) and must not be confused with an error:
        an adapter that cannot reach its source RAISES. Each finding carries a MEDIA-typed
        citation so a reviewer can trace it.
        """
        ...
