"""Minimal stdlib CLI: screen a name, or verify the audit chain (argparse, no extra deps)."""

from __future__ import annotations

import argparse
import sys

from hex_service_kit.logging import configure_logging

from ..config import build_container
from ..domain.models import PartyKind, ScreeningRequest
from ..service_factory import build_screening_service


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sanctions_screening")
    sub = parser.add_subparsers(dest="command", required=True)

    screen_cmd = sub.add_parser("screen", help="Screen a single party name.")
    screen_cmd.add_argument("subject")
    screen_cmd.add_argument("--kind", default=PartyKind.ENTITY.value)
    screen_cmd.add_argument("--subject-id", default="", help="Doc1 UBO key; empty skips owners.")
    screen_cmd.add_argument("--actor", default="cli-user@bank.example")
    screen_cmd.add_argument("--tenant", default="", help="Tenant partition asserted to Hrz7.")

    args = parser.parse_args(argv)
    container = build_container()
    # Idempotent: a process that is both an API app and a CLI configures once.
    configure_logging(container.settings.profile, service="sanctions-screening")

    if args.command == "screen":
        service = build_screening_service(container)
        kind = PartyKind(args.kind) if args.kind in tuple(PartyKind) else PartyKind.UNKNOWN
        request = ScreeningRequest(subject=args.subject, kind=kind, subject_id=args.subject_id)
        tenant = args.tenant or container.settings.tenant
        result = service.screen(request, actor=args.actor, tenant=tenant)
        print(f"{result.subject}: band={result.band.value} recommend={result.recommendation.value}")
        print(f"  severity: {result.severity.value}   owners screened: {result.owners_screened}")
        print(f"  requires_human_review: {result.requires_human_review}")
        # Rule R8 on the CLI path too: every disposition is routed, never merely printed.
        ref = container.review_router.route(result, maker=args.actor, tenant=args.tenant)
        print(f"  routed to human review: {ref}")
        return 0

    return 2  # pragma: no cover - argparse requires a subcommand


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
