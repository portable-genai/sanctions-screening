"""NarrationPort: the boundary the disposition-memo drafter sits behind.

The memo is the ONE place a model speaks in this service, and it speaks under supervision: it
restates the engine's bands and arithmetic in prose and adds nothing consequential. The service
validates every returned draft against the figures the engine computed and DISCARDS a draft that
introduces a number the engine did not (see ``screening_service.py``); a discarded draft falls
back to a deterministic skeleton, so a disposition never waits on generation and never inherits an
ungrounded number.

Families: managed (a pinned Gemini model, lazy SDK), local (a deterministic grounded skeleton, so
the offline gate exercises the memo path), onprem fail-fast. The local adapter is not a stub: it
produces a real, grounded memo from the supplied facts.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable


@runtime_checkable
class NarrationPort(Protocol):
    def draft_memo(self, facts: Mapping[str, object]) -> str:
        """Draft the disposition memo prose from the engine facts, or raise when it cannot.

        The return is untrusted text: the caller validates it against the engine's own figures
        and discards it on any figure the engine did not compute. An adapter that cannot produce
        a draft RAISES rather than returning an empty string, so the caller's fallback is entered
        deliberately rather than on a silent empty answer.
        """
        ...
