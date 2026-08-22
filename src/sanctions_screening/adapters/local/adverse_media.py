"""Local AdverseMediaPort: a small deterministic fixture corpus, SDK-free.

Advisory to the memo, never to the band. The offline family answers from a fixed, obviously
fictional corpus so the memo path is exercised in the gate; a name with no fixture entry returns
an empty tuple, which is a valid answer (no adverse media), not an error.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.kernel import Citation, Severity
from ...domain.match_engine import normalize
from ...domain.models import AdverseMediaFinding, PartyKind

#: normalised-name substring -> (headline, severity, snippet). Fictional sources only.
_CORPUS: tuple[tuple[str, str, Severity, str], ...] = (
    (
        "dmitri volkov",
        "Regulator names metals financier in fictional evasion probe",
        Severity.HIGH,
        "A fictional financial-press report links the named individual to sanctions evasion.",
    ),
    (
        "redsea shipping",
        "Shipping line flagged in fictional dual-use cargo inquiry",
        Severity.MEDIUM,
        "A fictional trade-press item reports an inquiry into the carrier's cargo manifests.",
    ),
)


class LocalAdverseMediaAdapter:
    """Return severity-ordered adverse-media findings from a fictional fixture corpus."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def search(
        self, name: str, *, kind: PartyKind = PartyKind.UNKNOWN
    ) -> tuple[AdverseMediaFinding, ...]:
        normalized = normalize(name)
        findings: list[AdverseMediaFinding] = []
        for needle, headline, severity, snippet in _CORPUS:
            if needle in normalized:
                findings.append(
                    AdverseMediaFinding(
                        party_name=name,
                        headline=headline,
                        severity=severity,
                        snippet=snippet,
                        citation=Citation(
                            source_id=f"media:{needle.replace(' ', '-')}",
                            title=headline,
                            snippet=snippet,
                        ),
                    )
                )
        findings.sort(key=lambda f: f.severity.value, reverse=True)
        return tuple(findings)
