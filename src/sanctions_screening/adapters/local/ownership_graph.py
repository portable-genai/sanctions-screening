"""Local OwnershipGraphPort: replay a captured Doc1 UBO fixture through the shared reader.

The fixture is a body captured from Doc1's FROZEN contract and shipped in-package. It is read by
the SAME ``parse_ubo_graph`` the managed adapter uses over the wire, so the offline family and the
managed family cannot read the contract two different ways: a drift that would break Doc1 in
production breaks the consumer contract test here first.
"""

from __future__ import annotations

import json
from importlib import resources

from ...config import Settings
from ...domain.models import OwnershipGraph
from .._ubo_contract import parse_ubo_graph

_FIXTURE_ANCHOR = "sanctions_screening._fixtures"
_FIXTURE_NAME = "doc1_ubo_graph.json"

#: The tenant the captured Doc1 graph belongs to, as the contract publishes it. Named here so the
#: eval, the demo and the tests scope their reads to the graph they are entitled to rather than
#: to whatever the port happens to return.
FIXTURE_TENANT = "demo-bank"


def load_fixture_graph() -> OwnershipGraph:
    """Read and parse the shipped Doc1 UBO fixture (also used by the contract test)."""
    raw = resources.files(_FIXTURE_ANCHOR).joinpath(_FIXTURE_NAME).read_text(encoding="utf-8")
    return parse_ubo_graph(json.loads(raw))


class LocalOwnershipGraphAdapter:
    """Return the captured Doc1 graph for any subject, so screening exercises the owner path."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def resolve(
        self, subject_id: str, subject_name: str, *, tenant: str, as_of: str = ""
    ) -> OwnershipGraph:
        graph = load_fixture_graph()
        # The graph's own data tag decides, not the id the caller named. Doc1 publishes the
        # owning tenant on the contract and this consumer used to drop it, so a UBO key from any
        # authenticated caller resolved and screened another bank's beneficial owners, who are
        # natural persons. An untagged graph matches nobody: the fail-closed reading of "the
        # source did not say who owns this" is "not you".
        if not tenant or graph.tenant != tenant:
            raise PermissionError(
                f"ownership graph {subject_id!r} does not belong to tenant {tenant!r}"
            )
        # Carry the caller's subject identity onto the fixture, so a screen of any subject_id
        # reads back as a graph for THAT subject rather than for the fixture's Acme.
        return OwnershipGraph(
            subject_id=subject_id or graph.subject_id,
            subject_name=subject_name or graph.subject_name,
            root_id=graph.root_id,
            tenant=graph.tenant,
            nodes=graph.nodes,
            edges=graph.edges,
            beneficial_owners=graph.beneficial_owners,
            truncated=graph.truncated,
            unresolved_ids=graph.unresolved_ids,
            opacity_score=graph.opacity_score,
            ownership_threshold_pct=graph.ownership_threshold_pct,
            as_of=as_of or graph.as_of,
        )
