"""Consumer contract test against cdd-sow-research's FROZEN UBO-graph shape.

G2 consumes cdd-sow-research's resolved ownership graph over A2A. cdd-sow-research froze that shape
in ``cdd-sow-research/docs/ubo-graph-contract.md`` and this repo pins a fixture captured from it.
The point of this suite is that drift in cdd-sow-research breaks G2's TEST rather than silently
misreading who owns whom: the same strict reader the managed adapter uses over the wire is driven
here over the captured fixture (green), then over deliberately drifted copies (red).
"""

from __future__ import annotations

import copy
import json
from importlib import resources
from typing import Any

import pytest

from sanctions_screening.adapters._ubo_contract import (
    UboContractError,
    parse_ubo_graph,
)
from sanctions_screening.adapters.local.ownership_graph import load_fixture_graph

_FIXTURE_ANCHOR = "sanctions_screening._fixtures"
_FIXTURE_NAME = "doc1_ubo_graph.json"


def _raw_fixture() -> dict[str, Any]:
    text = resources.files(_FIXTURE_ANCHOR).joinpath(_FIXTURE_NAME).read_text(encoding="utf-8")
    body: dict[str, Any] = json.loads(text)
    return body


def test_the_frozen_fixture_parses_and_carries_the_expected_owners() -> None:
    graph = load_fixture_graph()
    assert graph.subject_name == "Acme Holdings Pte Ltd (FICTIONAL)"
    names = {owner.name for owner in graph.beneficial_owners}
    assert "Ines Quiller (FICTIONAL)" in names
    # A percentage is a number in 0..100, never a fraction (cdd-sow-research's single most likely
    # silent break).
    for edge in graph.edges:
        assert 0.0 <= edge.pct <= 100.0


def test_a_renamed_owners_field_breaks_the_consumer_test() -> None:
    """If cdd-sow-research renamed ``beneficial_owners``, the reader must fail loudly, not read zero
    owners.
    """
    drifted = copy.deepcopy(_raw_fixture())
    drifted["owners"] = drifted.pop("beneficial_owners")
    with pytest.raises(UboContractError):
        parse_ubo_graph(drifted)


def test_a_percentage_out_of_range_is_rejected() -> None:
    """A value outside 0..100 (a mis-scaled percentage) is caught, not silently believed."""
    drifted = copy.deepcopy(_raw_fixture())
    drifted["beneficial_owners"][0]["effective_pct"] = 145.0
    with pytest.raises(UboContractError):
        parse_ubo_graph(drifted)


def test_a_percentage_as_a_string_is_rejected() -> None:
    drifted = copy.deepcopy(_raw_fixture())
    drifted["graph"]["edges"][0]["pct"] = "60"
    with pytest.raises(UboContractError):
        parse_ubo_graph(drifted)


def test_a_missing_required_field_is_rejected() -> None:
    drifted = copy.deepcopy(_raw_fixture())
    del drifted["graph"]["nodes"][1]["name"]
    with pytest.raises(UboContractError):
        parse_ubo_graph(drifted)
