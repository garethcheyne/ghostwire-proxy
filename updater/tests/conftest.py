"""Lets the tests import the `updater` package from updater/ (run with: cd updater && python -m pytest tests)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
