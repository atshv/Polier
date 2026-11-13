---
type: regex
arm: both
pattern: 'requests'
match: not_contains
target: { source: file, path: requirements.txt }
---
