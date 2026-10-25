#!/usr/bin/env python3
"""Task claims any harness can read: take, release, beat (heartbeat), list.

Usage:
    python3 tools/claim.py take M03 --harness dsh --session S [--worktree P] [--slot N]
                                  [--ttl 600] [--root .] [--json]
    python3 tools/claim.py release M03 [--session S] [--root .]
    python3 tools/claim.py beat M03 [--session S] [--root .]
    python3 tools/claim.py list [--root .] [--json]

Claims live in <git-common-dir>/polier/claims/<task>.json, shared by every
worktree of the repository. A claim is live while its heartbeat is younger than
the TTL (default 600 s); a stale claim can be taken over. board.json is never
written.

Exit codes: 0 ok, 1 conflict / no claim / stale claim, 2 usage or environment
error (not a git repository, bad board). The logic lives in core/claims.py.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.claims import (HARNESSES, TTL, ClaimConflict, NoClaim, beat,  # noqa: E402
                         claim_age, claim_dir, live_claims, release, take)
from core.errors import PolierError  # noqa: E402

__all__ = ["main"]


def _json(value) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def _summary(claim: dict) -> str:
    age = claim_age(claim)
    return (f"{claim.get('task')}: harness={claim.get('harness')} session={claim.get('session')} "
            f"worktree={claim.get('worktree') or '-'} slot={claim.get('slot') if claim.get('slot') is not None else '-'} "
            f"started={claim.get('started')} heartbeat={claim.get('heartbeat')}"
            + (f" age={int(age)}s" if age is not None else ""))


def _with_age(claim: dict) -> dict:
    age = claim_age(claim)
    return {**claim, "age_s": None if age is None else int(age)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawTextHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    def root_arg(p) -> None:
        p.add_argument("--root", default=".", help="project folder inside a git repository (default: .)")

    take_p = sub.add_parser("take", help="take a task or refresh the claim of this session")
    take_p.add_argument("task", help="task ID, e.g. M03")
    take_p.add_argument("--harness", required=True, choices=HARNESSES, help="who works: dsh, claude-code or cli")
    take_p.add_argument("--session", required=True, help="session id of that harness")
    take_p.add_argument("--worktree", help="worktree the session works in")
    take_p.add_argument("--slot", type=int, help="runtime slot from .polier-slot")
    take_p.add_argument("--ttl", type=float, default=TTL, help="seconds before a claim is stale (default: 600)")
    take_p.add_argument("--json", action="store_true", help="print the claim as JSON")
    root_arg(take_p)

    release_p = sub.add_parser("release", help="release a claim")
    release_p.add_argument("task", help="task ID")
    release_p.add_argument("--session", help="only release when this session holds the claim")
    release_p.add_argument("--json", action="store_true", help="print the result as JSON")
    root_arg(release_p)

    beat_p = sub.add_parser("beat", help="refresh the heartbeat of a claim")
    beat_p.add_argument("task", help="task ID")
    beat_p.add_argument("--session", help="only beat a claim held by this session")
    beat_p.add_argument("--json", action="store_true", help="print the claim as JSON")
    root_arg(beat_p)

    list_p = sub.add_parser("list", help="list the live claims of the repository")
    list_p.add_argument("--json", action="store_true", help="print the claims as JSON")
    root_arg(list_p)

    args = parser.parse_args(argv)

    try:
        if args.command == "take":
            claim = take(args.root, args.task, harness=args.harness, session=args.session,
                         worktree=args.worktree, slot=args.slot, ttl=args.ttl)
            if args.json:
                _json(claim)
            else:
                print(f"CLAIM TAKEN {_summary(claim)}")
            return 0

        if args.command == "release":
            removed = release(args.root, args.task, session=args.session)
            if args.json:
                _json({"task": args.task, "released": removed})
            elif removed:
                print(f"CLAIM RELEASED {args.task}")
            else:
                holder = "no claim" if args.session is None else f"no claim of session {args.session}"
                print(f"CLAIM NOT RELEASED {args.task}: {holder}", file=sys.stderr)
            return 0 if removed else 1

        if args.command == "beat":
            claim = beat(args.root, args.task, session=args.session)
            if args.json:
                _json(claim)
            else:
                print(f"CLAIM REFRESHED {_summary(claim)}")
            return 0

        claim_dir(args.root)  # a folder outside git is an environment error, not "no claims"
        claims = live_claims(args.root)
        if args.json:
            _json([_with_age(claim) for claim in claims])
        elif not claims:
            print("NO LIVE CLAIMS")
        else:
            for claim in claims:
                print(_summary(claim))
        return 0
    except ClaimConflict as exc:
        print(f"CLAIM CONFLICT: {exc}", file=sys.stderr)
        return 1
    except NoClaim as exc:
        print(f"NO CLAIM: {exc}", file=sys.stderr)
        return 1
    except PolierError as exc:
        print(f"CLAIM ERROR: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"CLAIM ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
