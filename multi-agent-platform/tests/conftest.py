"""Pytest configuration: make the gateway app package importable in tests."""

from __future__ import annotations

import sys
from pathlib import Path

_GATEWAY_SRC = Path(__file__).resolve().parent.parent / "apps" / "gateway"
if str(_GATEWAY_SRC) not in sys.path:
    sys.path.insert(0, str(_GATEWAY_SRC))
