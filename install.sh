#!/usr/bin/env bash
# Install Polier as an agent skill.
#
# Usage:
#   ./install.sh [--ref <tag>] [--update] [target ...]
#
# Targets: dsh (~/.dsh/skills), claude (~/.claude/skills, Claude Code), or a skills
# directory path, e.g. <project>/.dsh/skills.
# Default target: dsh. --ref installs a tagged version (e.g. v0.5.3) instead of the
# working copy. --update replaces an existing installation (see update.sh).
set -euo pipefail

NAME="polier"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REF=""
UPDATE=0
TARGETS=()

while [ $# -gt 0 ]; do
  case "$1" in
    --ref) REF="${2:?--ref needs a tag, e.g. v0.5.3}"; shift 2 ;;
    --update) UPDATE=1; shift ;;
    -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
    *) TARGETS+=("$1"); shift ;;
  esac
done
[ ${#TARGETS[@]} -eq 0 ] && TARGETS=(dsh)

# Source: the working copy, or an exported tag
if [ -n "$REF" ]; then
  git -C "$SRC" rev-parse -q --verify "refs/tags/$REF" >/dev/null \
    || { echo "error: tag $REF not found; available: $(git -C "$SRC" tag | tr '\n' ' ')" >&2; exit 1; }
  TMP="$(mktemp -d)"
  trap 'rm -rf "$TMP"' EXIT
  git -C "$SRC" archive "$REF" | tar -x -C "$TMP"
  SRC="$TMP"
fi
NEW_VERSION="$(cat "$SRC/VERSION" 2>/dev/null || echo "${REF:-unknown}")"

for target in "${TARGETS[@]}"; do
  case "$target" in
    dsh) dir="$HOME/.dsh/skills" ;;
    claude) dir="$HOME/.claude/skills" ;;
    */*) dir="$target" ;;
    *) echo "error: unknown target '$target'; use dsh, claude or a path such as ./my-project/.dsh/skills" >&2; exit 1 ;;
  esac
  dest="$dir/$NAME"

  if [ -e "$dest" ] && [ "$UPDATE" -eq 0 ]; then
    echo "skip: $dest exists (version $(cat "$dest/VERSION" 2>/dev/null || echo unknown)); use ./update.sh $target" >&2
    continue
  fi
  if [ ! -e "$dest" ] && [ "$UPDATE" -eq 1 ]; then
    echo "skip: $dest is not installed; use ./install.sh $target" >&2
    continue
  fi

  old_version="$(cat "$dest/VERSION" 2>/dev/null || echo unknown)"
  mkdir -p "$dir"
  rm -rf "$dest.new"
  mkdir -p "$dest.new"
  (cd "$SRC" && tar -cf - --exclude .git --exclude .DS_Store --exclude node_modules --exclude __pycache__ --exclude ./tests --exclude ./core/tests --exclude ./adapters/dsh/test .) | (cd "$dest.new" && tar -xf -)
  rm -rf "$dest"
  mv "$dest.new" "$dest"

  if [ "$UPDATE" -eq 1 ]; then
    echo "updated: $dest ($old_version -> $NEW_VERSION)"
  else
    echo "installed: $dest ($NEW_VERSION)"
  fi
done

if [ "$UPDATE" -eq 1 ]; then
  echo "Projects keep their generator_version; read CHANGELOG.md before migrating one."
fi
