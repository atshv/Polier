#!/usr/bin/env python3
"""Write docs/roles.md from roles/roles.json and the role instructions (npm run docs)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import roles  # noqa: E402

if __name__ == "__main__":
    (ROOT / "docs" / "roles.md").write_text(roles.markdown(), encoding="utf-8")
    print("written: docs/roles.md")
