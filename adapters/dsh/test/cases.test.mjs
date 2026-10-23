// The JS guard mirror against the decision table of the Python core
// (core/tests/write_cases.json). Needs no harness. Run: npm test
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import path from 'node:path'

import { checkPath, normalized } from '../lib/project.mjs'

const table = JSON.parse(readFileSync(path.resolve(import.meta.dirname, '../../../core/tests/write_cases.json'), 'utf8'))

for (const c of table.cases) {
  test(`write case: ${c.name}`, () => {
    const tasks = c.tasks.map((k) => table.tasks[k])
    const verdict = checkPath(normalized(c.path), tasks, c.role ?? 'worker')
    assert.equal(verdict.ok, c.ok, JSON.stringify(verdict))
    if (!c.ok) assert.equal(verdict.code, c.code)
  })
}
