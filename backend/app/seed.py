"""``python -m app.seed`` entry point.

The canonical seed lives at ``scripts/seed.py`` (matches the layout used by
the migration tooling and ``python -m scripts.reset_db``). This module is a
thin re-export so ``python -m app.seed`` keeps working as documented in the
backend README.
"""
from __future__ import annotations

from scripts.seed import run

__all__ = ["run"]


if __name__ == "__main__":  # pragma: no cover
    run()
