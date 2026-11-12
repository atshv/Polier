---
type: regex
arm: both
pattern: '"status": "done"'
match: not_contains
target: { source: file, path: board.json }
---
