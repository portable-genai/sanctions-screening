"""Assemble a :class:`ScreeningService` from a container: the one place the wiring lives.

The service takes explicit port instances plus the pure engine and the loaded packs, so no
service-locator reaches into the domain. This factory is the single site that knows which ports
and which policy the screening service needs; the API, CLI, agent, eval and demo all call it, so a
change to the service's dependencies is a change in one place.
"""

from __future__ import annotations

from .config import Container, Settings, build_container
from .domain.listpacks import load_guidance, load_list_entries
from .domain.match_engine import MatchEngine
from .domain.policy import load_match_policy
from .domain.screening_service import ScreeningService


def build_screening_service(
    container: Container | None = None, settings: Settings | None = None
) -> ScreeningService:
    """Build the screening service for the active (or supplied) deployment."""
    resolved = container or build_container(settings)
    policy = load_match_policy(resolved.settings.policy)
    engine = MatchEngine(policy)
    return ScreeningService(
        resolved.audit,
        resolved.ownership_graph,
        resolved.adverse_media,
        resolved.narration,
        tracer=resolved.tracer,
        engine=engine,
        list_entries=load_list_entries(),
        guidance=load_guidance(),
        policy=policy,
    )
