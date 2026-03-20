#!/usr/bin/env python3
"""Repo-root wrapper for the final Fresh Capital MVP shell command."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from fresh_capital.__main__ import main


if __name__ == "__main__":
    raise SystemExit(main())
