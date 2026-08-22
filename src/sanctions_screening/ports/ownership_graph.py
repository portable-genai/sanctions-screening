"""OwnershipGraphPort: the boundary that consumes Doc1's resolved beneficial-ownership graph.

G2 does not resolve ownership itself. Doc1 (the CDD / Source-of-Wealth agent) owns that
resolution and publishes it over an A2A surface whose output shape is FROZEN
(``cdd-sow-research/docs/ubo-graph-contract.md``). This port names the hand-off; the adapters
call Doc1 (managed), replay a captured fixture (local), or refuse (onprem). The engine then
screens each resolved beneficial owner through the same match engine, so an owner on a list is
caught even when the payer name is clean.

The domain stays pure: this port speaks only in this vertical's :class:`OwnershipGraph`, and the
adapter is the only place that knows Doc1's JSON.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.models import OwnershipGraph


@runtime_checkable
class OwnershipGraphPort(Protocol):
    def resolve(
        self, subject_id: str, subject_name: str, *, tenant: str, as_of: str = ""
    ) -> OwnershipGraph:
        """Resolve ``tenant``'s ownership graph for a subject, or raise when it cannot be got.

        ``tenant`` is the VERIFIED principal's and is required, not defaulted. This port took a
        client-supplied ``subject_id`` and no principal, so any authenticated caller who named a
        key had that subject's beneficial owners, who are NATURAL PERSONS, resolved and screened
        on their behalf. An adapter raises when the graph it found belongs to somebody else, the
        same way it raises when it cannot reach its source.

        A returned graph may be ``truncated`` or carry ``unresolved_ids``: that is not an error,
        it means the percentages are a floor. An adapter that cannot reach its source RAISES
        rather than returning an empty graph, because an empty graph reads as "no owners" and a
        missing graph reads as "unknown", and screening must not confuse the two.
        """
        ...
