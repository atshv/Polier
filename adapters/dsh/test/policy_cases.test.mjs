// The JS policy mirror against the shared decision table of the Python core
// (core/tests/policy_cases.json) plus the policy.json loader and the approval
// lookup. Needs no harness. Run: npm test
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'

import {
  ACTIONS, DEFAULTS, actionRequired, approver, commandDenial, commandSegments, enabled, globMatch,
  hasGrant, limits, loadPolicy, manifestMatch, pathMatches, pendingApprovals, policyErrors,
  protectedMatch,
} from '../lib/policy.mjs'

const table = JSON.parse(readFileSync(path.resolve(import.meta.dirname, '../../../core/tests/policy_cases.json'), 'utf8'))

// The table's policy as a loaded one: every section comes from the table, the
// loader adds `enabled` and the validation result.
const policy = { enabled: true, version: 1, ...table.policy }

for (const c of table.path_cases) {
  test(`policy path case: ${c.name}`, () => {
    assert.equal(pathMatches(c.pattern, c.rel), c.ok, `${c.pattern} vs ${c.rel}`)
  })
}

for (const c of table.manifest_cases) {
  test(`policy manifest case: ${c.name}`, () => {
    const scoped = { dependencies: { approval: true, manifests: [c.pattern] } }
    assert.equal(manifestMatch(scoped, c.rel), c.ok ? c.pattern : null, `${c.pattern} vs ${c.rel}`)
  })
}

for (const c of table.command_cases) {
  test(`policy command case: ${c.name}`, () => {
    const scoped = { commands: { deny: [], lead_only: [], warn: [], [c.list]: [c.pattern] } }
    const denial = commandDenial(scoped, c.command, c.role)
    assert.equal(denial ? denial.rule : null, c.denial, `${JSON.stringify(c.command)} as ${c.role}`)
    if (denial) assert.equal(denial.pattern, c.pattern)
  })
}

test('the table policy loads through the defaults', () => {
  const root = mkdtempSync(path.join(tmpdir(), 'pl-policy-'))
  writeFileSync(path.join(root, 'policy.json'), JSON.stringify(table.policy, null, 2))
  const loaded = loadPolicy(root)
  assert.equal(enabled(loaded), true)
  assert.deepEqual(loaded.errors, [])
  assert.deepEqual(limits(loaded), table.policy.limits)
  assert.equal(approver(loaded), 'owner')
  assert.equal(actionRequired(loaded, 'new_dependency'), true)
  assert.equal(actionRequired(loaded, 'state_override'), false)
  assert.equal(protectedMatch(loaded, 'apps/web/.env'), '.env')
  assert.equal(protectedMatch(loaded, 'src/app.py'), null)
  assert.equal(manifestMatch(loaded, 'apps/web/package.json'), 'package.json')
  assert.equal(manifestMatch(loaded, 'package-lock.json'), null)
})

test('an absent policy.json means disabled, a broken one fails open', () => {
  const root = mkdtempSync(path.join(tmpdir(), 'pl-policy-'))
  assert.deepEqual(loadPolicy(root), { enabled: false })
  assert.equal(enabled(loadPolicy(root)), false)

  writeFileSync(path.join(root, 'policy.json'), '{nope')
  const broken = loadPolicy(root)
  assert.equal(enabled(broken), false)
  assert.match(broken.errors[0], /not valid JSON/)

  writeFileSync(path.join(root, 'policy.json'), '[]')
  assert.equal(enabled(loadPolicy(root)), false)
})

test('a partial policy.json takes the defaults for the missing keys', () => {
  const root = mkdtempSync(path.join(tmpdir(), 'pl-policy-'))
  writeFileSync(path.join(root, 'policy.json'), JSON.stringify({
    version: 1,
    scope: { protected_paths: ['secrets/**'] },
  }))
  const loaded = loadPolicy(root)
  assert.equal(enabled(loaded), true)
  assert.deepEqual(loaded.scope.protected_paths, ['secrets/**'])
  assert.deepEqual(loaded.dependencies.manifests, DEFAULTS.dependencies.manifests)
  assert.deepEqual(limits(loaded), DEFAULTS.limits)
  assert.deepEqual(loaded.errors, [])
})

test('policy errors name the unknown key and the bad value', () => {
  const unknown = policyErrors({ ...policy, extra: true })
  assert.equal(unknown.some((error) => /unknown key "extra"/.test(error)), true)
  const nested = policyErrors({ ...policy, limits: { ...policy.limits, max_attempts_per_task: 0 } })
  assert.equal(nested.some((error) => /max_attempts_per_task/.test(error)), true)
  const version = policyErrors({ ...policy, version: 2 })
  assert.equal(version.some((error) => /version must be 1/.test(error)), true)
  assert.deepEqual(policyErrors({ ...policy, version: 1 }), [])
  // Invalid limits fall back to the defaults instead of raising.
  assert.deepEqual(limits({ limits: { max_attempts_per_task: 'many' } }), DEFAULTS.limits)
})

test('ACTIONS covers the approval actions of the design', () => {
  for (const action of ['new_dependency', 'scope_change', 'merge_to_base', 'release', 'reopen_done',
    'protected_path', 'state_override']) {
    assert.ok(ACTIONS.includes(action), action)
  }
})

test('globMatch is fnmatch-style and ignores case, commandSegments strips text and wrappers', () => {
  assert.equal(globMatch('git push*', 'git push origin main'), true)
  assert.equal(globMatch('git push*', 'GIT PUSH origin main'), true)
  assert.equal(globMatch('git push*', 'git status'), false)
  assert.equal(globMatch('*tools/state.py set*', 'python3 tools/state.py set M03 in_progress'), true)

  assert.deepEqual(commandSegments('cd /tmp && npm publish'), ['cd /tmp', 'npm publish'])
  assert.deepEqual(commandSegments('sudo env FOO=1 git push origin main'), ['git push origin main'])
  assert.deepEqual(commandSegments("bash -c 'git push origin main'"), ['git push origin main'])
  assert.deepEqual(commandSegments('cat <<EOF\ngit push origin main\nEOF'), ['cat << EOF'])
  assert.equal(commandDenial({ commands: { deny: ['git push*'], lead_only: [] } },
    'cat <<EOF\ngit push origin main\nEOF', 'worker'), null)
  assert.deepEqual(commandSegments("echo 'npm publish'"), ["echo npm publish"])
  assert.deepEqual(commandSegments(''), [])
})

// ---------------------------------------------------------------------------
// approvals: reviews/approvals/AP-NNN.json
// ---------------------------------------------------------------------------

function approval(root, { id = 'AP-001', action = 'new_dependency', task = 'M01', status = 'granted',
  at = '2026-10-28T12:00:00+00:00' } = {}) {
  const folder = path.join(root, 'reviews', 'approvals')
  mkdirSync(folder, { recursive: true })
  writeFileSync(path.join(folder, `${id}.json`), JSON.stringify({
    id, action, task, status, requested_by: 'worker', requested_at: '2026-10-28T11:00:00+00:00',
    approved_by: status === 'granted' ? 'owner' : null, approved_at: status === 'granted' ? at : null, note: null,
  }))
}

test('hasGrant reads the approval records', () => {
  const root = mkdtempSync(path.join(tmpdir(), 'pl-policy-'))
  assert.equal(hasGrant(root, 'new_dependency', 'M01'), null)

  approval(root, { id: 'AP-001', status: 'pending' })
  assert.equal(hasGrant(root, 'new_dependency', 'M01'), null)
  assert.equal(pendingApprovals(root).length, 1)

  approval(root, { id: 'AP-002', status: 'granted', at: '2026-10-28T12:00:00+00:00' })
  assert.equal(hasGrant(root, 'new_dependency', 'M01').id, 'AP-002')
  assert.equal(hasGrant(root, 'new_dependency', 'M02'), null)
  assert.equal(hasGrant(root, 'new_dependency', null).id, 'AP-002')
  assert.equal(hasGrant(root, 'release', 'M01'), null)

  // A record without a task matches any task; a newer granted record wins.
  approval(root, { id: 'AP-003', task: null, at: '2026-10-28T12:30:00+00:00' })
  assert.equal(hasGrant(root, 'new_dependency', 'M09').id, 'AP-003')
  approval(root, { id: 'AP-010', at: '2026-10-28T13:00:00+00:00' })
  assert.equal(hasGrant(root, 'new_dependency', 'M01').id, 'AP-010')
  assert.equal(pendingApprovals(root)[0].id, 'AP-001')
})

test('a broken approval file is ignored', () => {
  const root = mkdtempSync(path.join(tmpdir(), 'pl-policy-'))
  const folder = path.join(root, 'reviews', 'approvals')
  mkdirSync(folder, { recursive: true })
  writeFileSync(path.join(folder, 'AP-001.json'), '{broken')
  writeFileSync(path.join(folder, 'notes.txt'), 'not an approval')
  assert.equal(hasGrant(root, 'new_dependency', 'M01'), null)
  assert.deepEqual(pendingApprovals(root), [])
})
