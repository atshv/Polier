#!/usr/bin/env bash
# Update an installed Polier skill to this working copy or a tagged version.
#
# Usage:
#   ./update.sh [--ref <tag>] [target ...]
#
# Targets: dsh (~/.dsh/skills), claude (~/.claude/skills, Claude Code), or a skills
# directory path, e.g. <project>/.dsh/skills.
# Default target: dsh. --ref v0.5.3 also rolls back to an older version.
# Before updating, the drift report of the installed copy is printed, so local
# edits are visible before they are overwritten.
set -euo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARGS=("$@")
REF=""
TARGETS=()

while [ $# -gt 0 ]; do
  case "$1" in
    --ref) REF="${2:?--ref needs a tag, e.g. v0.5.3}"; shift 2 ;;
    --update) shift ;;  # implied by update.sh; accepted for compatibility
    -h|--help) exec "$SRC/install.sh" --update ${ARGS[@]+"${ARGS[@]}"} ;;
    *) TARGETS+=("$1"); shift ;;
  esac
done
[ ${#TARGETS[@]} -eq 0 ] && TARGETS=(dsh)

for target in "${TARGETS[@]}"; do
  case "$target" in
    dsh) dir="$HOME/.dsh/skills" ;;
    claude) dir="$HOME/.claude/skills" ;;
    */*) dir="$target" ;;
    *) echo "error: unknown target '$target'; use dsh, claude or a path such as ./my-project/.dsh/skills" >&2; exit 1 ;;
  esac
  dest="$dir/polier"
  if [ -f "$dest/tools/drift.py" ] && command -v python3 >/dev/null 2>&1; then
    echo "drift check: $dest"
    python3 "$dest/tools/drift.py" --package "$dest" || true
  fi
done

exec "$SRC/install.sh" --update ${ARGS[@]+"${ARGS[@]}"}
