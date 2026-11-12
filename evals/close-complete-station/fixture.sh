#!/usr/bin/env bash
# Concept station active, every concept item done with evidence. The script gets only PATH, HOME and
# TMPDIR, so git's identity is passed inline.
set -euo pipefail
mkdir -p docs src reviews

cat > policy.json <<'EOF_POLICY'
{
  "version": 1,
  "limits": {"max_attempts_per_task": 3, "max_in_progress": 1, "max_review_rounds": 3},
  "scope": {"protected_paths": [".env", ".env.*", "secrets/**", "policy.json"]},
  "dependencies": {"approval": true, "manifests": ["requirements.txt"]},
  "approvals": {"actions": ["new_dependency", "scope_change", "merge_to_base", "release", "reopen_done", "protected_path"], "approver": "owner"},
  "commands": {"deny": ["git push*", "git tag*"], "lead_only": [], "warn": []},
  "checks": {"review_before_done": true, "handoff_before_done": true, "run_record": true, "disjoint_scopes": true},
  "budget": {"max_tokens_per_task": null, "warn_at": 0.8}
}
EOF_POLICY

cat > board.json <<'EOF_BOARD'
{
  "project": "eval-fixture",
  "profile": "S",
  "base_branch": "main",
  "tasks": [
    {"id": "M01", "title": "Add numbers", "goal": "add() returns the sum of two numbers.", "status": "pending", "depends_on": [], "complexity": 2, "stage": 1, "scope_write": ["src/app.py"], "acceptance": ["A1"], "gates": ["tests"]}
  ]
}
EOF_BOARD

cat > factory.json <<'EOF_FACTORY'
{
  "factory_version": "3.0",
  "platforms": ["cli"],
  "traits": [],
  "resolved_traits": [],
  "stations": {
    "idea": {"status": "done", "closed": "2026-01-01T00:00:00Z", "approved_by": "owner"},
    "concept": {"status": "active", "started": "2026-01-01T00:00:00Z"},
    "design": {"status": "pending"},
    "architecture": {"status": "pending"},
    "plan": {"status": "pending"},
    "build": {"status": "pending"},
    "verify": {"status": "pending"},
    "release": {"status": "pending"},
    "operate": {"status": "pending"}
  },
  "items": {
    "CON-02": {"status": "done", "evidence": ["docs/concept.md#features"], "at": "2026-01-01T00:00:00Z", "by": "lead"},
    "CON-03": {"status": "done", "evidence": ["docs/concept.md#user-stories"], "at": "2026-01-01T00:00:00Z", "by": "lead"},
    "CON-04": {"status": "done", "evidence": ["docs/quality.md"], "at": "2026-01-01T00:00:00Z", "by": "lead"}
  },
  "history": []
}
EOF_FACTORY

cat > docs/concept.md <<'EOF_CONCEPT'
# Concept

## Features

- add: MVP

## User stories

As a user I want to add numbers so that I can total them.
WHEN I add 1 and 2 THEN the result SHALL be 3.
EOF_CONCEPT

cat > docs/quality.md <<'EOF_QUALITY'
# Quality

D1: add(1, 2) returns 3.
EOF_QUALITY

printf 'def add(a, b):\n    return a + b\n' > src/app.py
printf 'Scaffold readme with a typo: teh quick start.\n' > README.md

git init -q -b main
git add -A
git -c user.name=eval -c user.email=eval@example.com commit -q -m 'chore: scaffold'
