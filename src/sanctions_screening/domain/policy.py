"""Bank-owned policy for the match engine: thresholds and weights, lifted out of the code.

The numbers are the adopter's, not the engine's, so they live in a frozen dataclass populated
from the settings ``policy:`` block (practices check B4) rather than as magic constants inside
``match_engine.py``. The engine reads a :class:`MatchPolicy` and branches on no jurisdiction; a
market that wants different bands edits configuration, not the engine.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MatchPolicy:
    """Confidence-band thresholds and blend weights for the deterministic match engine.

    The four thresholds partition a 0..100 confidence into the five bands. A confidence at or
    above ``confirmed_at`` is a CONFIRMED band; below ``weak_at`` is CLEAR. The weights blend the
    token, name-part, date-of-birth and identifier sub-scores into the final confidence; they are
    normalised at use so a mis-summed set of weights cannot silently change the scale.
    """

    weak_at: float = 40.0
    possible_at: float = 60.0
    strong_at: float = 78.0
    confirmed_at: float = 90.0
    token_weight: float = 0.55
    name_part_weight: float = 0.25
    dob_weight: float = 0.12
    id_weight: float = 0.08
    #: The ownership stake at or above which a natural person is a beneficial owner. Doc1 owns the
    #: resolution; this is the threshold THIS screening applies when reading the graph.
    ownership_threshold_pct: float = 25.0

    def __post_init__(self) -> None:
        thresholds = (self.weak_at, self.possible_at, self.strong_at, self.confirmed_at)
        if list(thresholds) != sorted(thresholds):
            raise ValueError(
                "match policy thresholds must be non-decreasing "
                f"(weak <= possible <= strong <= confirmed), got {thresholds}"
            )
        if not all(0.0 <= t <= 100.0 for t in thresholds):
            raise ValueError(f"match policy thresholds must lie in 0..100, got {thresholds}")


def load_match_policy(block: Mapping[str, object] | None) -> MatchPolicy:
    """Build a :class:`MatchPolicy` from a settings ``policy:`` mapping, or the shipped default.

    An absent block yields the default policy; a present one overrides only the keys it names, so
    a deployment can retune one threshold without restating the rest.
    """
    if not block:
        return MatchPolicy()
    fields = {
        "weak_at",
        "possible_at",
        "strong_at",
        "confirmed_at",
        "token_weight",
        "name_part_weight",
        "dob_weight",
        "id_weight",
        "ownership_threshold_pct",
    }
    overrides = {key: float(value) for key, value in block.items() if key in fields}  # type: ignore[arg-type]
    return MatchPolicy(**overrides)
