"""Apply feedback_events schema to Postgres.

Usage:
    python -m agrimind_kernel.feedback.migrate
    python -m agrimind_kernel.feedback.migrate --dsn postgresql://user:pass@localhost:5432/agrimind

Env (checked in order):
    POSTGRES_DSN, then Settings.postgres_dsn
"""

from __future__ import annotations

import argparse
import os
import sys


def resolve_dsn(cli_dsn: str | None = None) -> str:
    if cli_dsn:
        return cli_dsn
    env = os.getenv("POSTGRES_DSN")
    if env:
        return env
    try:
        from agrimind_kernel.config.settings import get_settings

        return get_settings().postgres_dsn
    except Exception:  # noqa: BLE001
        return "postgresql://agrimind:agrimind_secret_123@localhost:5432/agrimind"


def ensure_schema(dsn: str | None = None) -> None:
    """Public helper: create feedback_events table if missing."""
    from agrimind_kernel.feedback.postgres_store import PostgresFeedbackStore

    resolved = resolve_dsn(dsn)
    store = PostgresFeedbackStore(resolved, ensure_schema_on_init=True)
    # ensure_schema already ran on init; call again is a no-op once ready
    store.ensure_schema()
    print(f"feedback_events schema OK (dsn host from: {resolved.split('@')[-1]})")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Migrate / ensure AGRIMIND feedback_events Postgres schema"
    )
    parser.add_argument(
        "--dsn",
        default=None,
        help="Postgres DSN (default: POSTGRES_DSN or settings.postgres_dsn)",
    )
    args = parser.parse_args(argv)
    try:
        ensure_schema(args.dsn)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: schema migration failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
