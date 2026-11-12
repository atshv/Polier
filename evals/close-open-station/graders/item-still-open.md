---
type: regex
arm: with-only
pattern: '"CON-03":\s*\{[^{}]*"status":\s*"open"'
match: contains
target: { source: file, path: factory.json }
---
