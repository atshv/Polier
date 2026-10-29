#!/usr/bin/env python3
"""Start the Polier dashboard: a local HTTP + SSE server with the web UI (2.0).

Usage:
    python3 tools/serve.py [project] [--host 127.0.0.1] [--port 8765] [--open]
    python3 tools/serve.py . --token "$POLIER_DASHBOARD_TOKEN"
    python3 tools/serve.py . --read-only

The dashboard is optional: every action it offers goes through the same
``core`` functions as the CLI tools, and the project files stay the source of
truth. It binds to loopback by default, needs no dependency beyond the Python
standard library and serves one self-contained page (``server/assets``).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.app import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
