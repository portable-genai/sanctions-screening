"""Parse Doc1's FROZEN UBO-graph JSON body into this vertical's ``OwnershipGraph``.

Doc1 froze the shape of ``resolve_ubo_graph`` / ``GET /v1/ubo-graph`` in
``cdd-sow-research/docs/ubo-graph-contract.md`` and versions it by the agent card. This is the
CONSUMER side of that agreement: one strict reader, used by BOTH the managed adapter (over the
wire) and the local adapter (over a captured fixture), so the two families cannot read the same
contract two different ways. A field Doc1 renames, retypes or removes breaks this reader loudly,
which is exactly the drift a consumer contract-fixture test is meant to catch here rather than in
production. Unknown ADDED fields are ignored, matching Doc1's additive-change rule.

The single most likely silent break Doc1 called out is a percentage arriving as a 0..1 fraction
or a string; :func:`_pct` refuses anything that is not a real number in 0..100.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..domain.models import (
    BeneficialOwner,
    OwnershipEdge,
    OwnershipGraph,
    OwnershipNode,
)


class UboContractError(ValueError):
    """Doc1's UBO body did not match the frozen contract this consumer pins."""


def _require(body: Mapping[str, Any], key: str) -> Any:
    if key not in body:
        raise UboContractError(f"missing required field {key!r}")
    return body[key]


def _pct(value: Any, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise UboContractError(f"{where}: percentage must be a number, got {value!r}")
    number = float(value)
    if not 0.0 <= number <= 100.0:
        raise UboContractError(
            f"{where}: percentage must be 0..100 (never a 0..1 fraction), got {number}"
        )
    return number


def _node(raw: Mapping[str, Any]) -> OwnershipNode:
    return OwnershipNode(
        node_id=str(_require(raw, "id")),
        name=str(_require(raw, "name")),
        kind=str(_require(raw, "kind")),
        jurisdiction=str(raw.get("jurisdiction", "")),
        is_pep=bool(raw.get("is_pep", False)),
        depth=int(raw.get("depth", 0)),
    )


def _edge(raw: Mapping[str, Any]) -> OwnershipEdge:
    return OwnershipEdge(
        source_id=str(_require(raw, "source_id")),
        target_id=str(_require(raw, "target_id")),
        kind=str(_require(raw, "kind")),
        pct=_pct(raw.get("pct", 0.0), "edge"),
    )


def _owner(raw: Mapping[str, Any]) -> BeneficialOwner:
    return BeneficialOwner(
        node_id=str(_require(raw, "node_id")),
        name=str(_require(raw, "name")),
        kind=str(raw.get("kind", "natural_person")),
        jurisdiction=str(raw.get("jurisdiction", "")),
        is_pep=bool(raw.get("is_pep", False)),
        effective_pct=_pct(_require(raw, "effective_pct"), "beneficial_owner"),
        meets_threshold=bool(raw.get("meets_threshold", False)),
    )


def parse_ubo_graph(body: Mapping[str, Any]) -> OwnershipGraph:
    """Parse a Doc1 UBO body into an :class:`OwnershipGraph`, raising on any contract drift."""
    if not isinstance(body, Mapping):
        raise UboContractError("UBO body must be a JSON object")
    graph = _require(body, "graph")
    if not isinstance(graph, Mapping):
        raise UboContractError("'graph' must be an object")
    owners_raw = _require(body, "beneficial_owners")
    if not isinstance(owners_raw, list):
        raise UboContractError("'beneficial_owners' must be a list")
    nodes = tuple(_node(n) for n in graph.get("nodes", []))
    edges = tuple(_edge(e) for e in graph.get("edges", []))
    owners = tuple(_owner(o) for o in owners_raw)
    return OwnershipGraph(
        subject_id=str(body.get("subject_id", "")),
        subject_name=str(body.get("subject_name", "")),
        root_id=str(graph.get("root_id", "")),
        # Doc1 has always published the owning tenant on this contract and this consumer was
        # dropping it, which is how a UBO graph key from any caller resolved any subject's
        # beneficial owners. Read it, so the adapter has something to authorize against.
        tenant=str(body.get("tenant", "")),
        nodes=nodes,
        edges=edges,
        beneficial_owners=owners,
        truncated=bool(graph.get("truncated", False)),
        unresolved_ids=tuple(str(u) for u in graph.get("unresolved_ids", []) or ()),
        opacity_score=float(body.get("opacity_score", 0.0)),
        ownership_threshold_pct=_pct(
            body.get("ownership_threshold_pct", 25.0), "ownership_threshold_pct"
        ),
        as_of=str(body.get("as_of", "")),
    )
