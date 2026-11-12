---
type: regex
arm: both
pattern: '"concept": \{\s*"status": "done"'
match: not_contains
target: { source: file, path: factory.json }
---
