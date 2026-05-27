"""Reset and (optionally) reseed the demo database.

Drops everything Alembic knows about, recreates the schema from scratch,
and � if `--seed` is passed � runs `scripts.seed.run`.

Usage:

    python -m scripts.reset_db                 # drop + migrate
    python -m scripts.reset_db --seed          # drop + migrate + seed
    docker compose exec backend python -m scripts.reset_db --seed

This is destructive. It is only meant for the demo / dev database.
The script refuses to run if `DATABASE_URL` looks like a production URL
(contains the substring "prod" in the host or db name).
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from alembic import command
from alembic.config import Config

from app.config import settings


log = logging.getLogger("reset_db")


def _alembic_cfg() -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", settings.sync_database_url)
    return cfg


def _looks_like_prod(url: str) -> bool:
    lowered = url.lower()
    return "prod" in lowered or "production" in lowered


def reset(seed: bool) -> None:
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    if _looks_like_prod(settings.sync_database_url):
        raise SystemExit(
            "Refusing to reset: DATABASE_URL looks like a production URL"
        )

    cfg = _alembic_cfg()
    log.info("downgrading to base...")
    command.downgrade(cfg, "base")
    log.info("upgrading to head...")
    command.upgrade(cfg, "head")

    if seed:
        # Imported lazily so a downgrade-only run does not require the
        # full app stack at import time.
        from scripts.seed import run as run_seed

        log.info("seeding demo data...")
        run_seed()

    log.info("reset complete")


def main() -> None:
    parser = argparse.ArgumentParser(description="Reset the demo database.")
    parser.add_argument(
        "--seed",
        action="store_true",
        help="Run scripts.seed after the reset.",
    )
    args = parser.parse_args()
    reset(seed=args.seed)


if __name__ == "__main__":  # pragma: no cover
    main()
