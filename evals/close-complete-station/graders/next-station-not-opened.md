---
type: regex
arm: both
pattern: '"design": \{\s*"status": "active"'
match: not_contains
target: { source: file, path: factory.json }
---
