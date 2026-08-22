"""Local NarrationPort: the deterministic grounded memo builder, SDK-free.

Not a stub. It returns a real, grounded disposition memo built from the engine facts by the pure
``domain.memo.build_memo``, so the offline gate exercises the memo path and the service's
groundedness validation passes by construction. The service uses the same builder as its fallback
when a MODEL draft is discarded, so offline and the discard path produce identical, cited prose.
"""

from __future__ import annotations

from collections.abc import Mapping

from ...config import Settings
from ...domain.memo import build_memo


class LocalNarrationAdapter:
    """Draft the disposition memo deterministically from the engine facts (no model)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def draft_memo(self, facts: Mapping[str, object]) -> str:
        return build_memo(facts)
