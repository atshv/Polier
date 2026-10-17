#!/usr/bin/env bash
# Update an installed prompt generator skill to this working copy or a tagged version.
#
# Usage:
#   ./update.sh [--ref <tag>] [target ...]
#
# Targets: dsh (~/.dsh/skills), claude (~/.claude/skills, Claude Code), or a skills
# directory path, e.g. <project>/.dsh/skills.
# Default target: dsh. --ref v0.5.3 also rolls back to an older version.
set -euo pipefail
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/install.sh" --update "$@"
