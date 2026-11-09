#!/usr/bin/env python3
"""The guard decision for one write or shell command, as JSON.

Usage:
    python3 tools/guard.py '<request JSON>'
    echo '<request JSON>' | python3 tools/guard.py

The request names ``root``, ``cwd``, ``role`` (worker, reviewer, lead, off),
``tasks`` (ids bound to the session), an optional ``specialist`` with
``title`` and ``writes``, and either ``path`` or ``command``. The answer is
``{"deny": reason or null, "kills": true|false}``. The DSH plugin calls this
before every guarded tool call; the rules live in core/guard.py.

Exit 0 = answered (allowed or denied), 2 = the request is not valid JSON.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.guard import decide  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args and args[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    raw = args[0] if args else sys.stdin.read()
    try:
        request = json.loads(raw)
    except ValueError as exc:
        print(json.dumps({"error": f"request is not JSON: {exc}"}))
        return 2
    if not isinstance(request, dict):
        print(json.dumps({"error": "request must be a JSON object"}))
        return 2
    print(json.dumps(decide(request)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
