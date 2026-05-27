"""Conftest: ensure the repository root is on sys.path so ``simulator`` and
``tests`` import cleanly when pytest is invoked from the repo root.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
