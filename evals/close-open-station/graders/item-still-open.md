---
type: regex
arm: both
pattern: '"CON-03":\s*\{[^{}]*"status":\s*"open"'
match: contains
target: { source: file, path: factory.json }
---
