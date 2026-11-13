---
type: regex
arm: both
pattern: '"CON-03": \{\s*"status": "done"'
match: not_contains
target: { source: file, path: factory.json }
---
