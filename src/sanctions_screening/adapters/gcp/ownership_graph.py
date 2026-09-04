"""Managed OwnershipGraphPort: call cdd-sow-research's A2A ``resolve_ubo_graph`` skill and parse its
body.

cdd-sow-research publishes the resolution over its A2A surface (agent card at
``/.well-known/agent-card.json``). This adapter POSTs the subject to cdd-sow-research's resolve
endpoint and parses the response through the shared ``parse_ubo_graph``, so drift in
cdd-sow-research's frozen contract surfaces as a parse error rather than a silent misread of who
owns whom.

Fail closed offline: an unconfigured cdd-sow-research URL raises ``RuntimeError`` rather than
inventing an empty graph, exactly as the managed review router refuses an unconfigured console. The
HTTP client is imported lazily so this module imports with no client library present.
"""

from __future__ import annotations

from typing import Any

from ...config import Settings
from ...domain.models import OwnershipGraph
from .._ubo_contract import parse_ubo_graph


class Doc1OwnershipGraphAdapter:
    """Resolve a subject's ownership graph from cdd-sow-research over A2A (rule R8 stays
    cdd-sow-research's concern).
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def resolve(
        self, subject_id: str, subject_name: str, *, tenant: str, as_of: str = ""
    ) -> OwnershipGraph:
        base_url = self._settings.doc1_a2a_url.strip()
        if not base_url:
            raise RuntimeError(
                "doc1_a2a_url is not configured, so the UBO graph cannot be resolved. Set "
                "DOC1_A2A_URL (config/settings.yaml doc1_a2a_url) to cdd-sow-research's A2A "
                "endpoint."
            )
        import httpx  # noqa: PLC0415 - lazy so this module imports with no client installed

        payload: dict[str, Any] = {"subject_id": subject_id, "subject_name": subject_name}
        if as_of:
            payload["as_of"] = as_of
        response = httpx.post(f"{base_url}/a2a/resolve_ubo_graph", json=payload, timeout=30.0)
        response.raise_for_status()
        graph = parse_ubo_graph(response.json())
        # cdd-sow-research answers about whatever key it is asked for, so the entitlement check
        # belongs on
        # THIS side of the hop: the graph's published tenant must be the caller's verified one.
        if not tenant or graph.tenant != tenant:
            raise PermissionError(
                f"ownership graph {subject_id!r} does not belong to tenant {tenant!r}"
            )
        return graph
