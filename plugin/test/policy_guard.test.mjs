// The policy guard of the DSH plugin, on a throwaway git project with a real
// policy.json: protected paths, dependency manifests with approvals, denied
// commands, lead-only commands, and the pl_status, pl_next and pl_state
// surfaces. Boots the real tool registry. Run: npm test
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'

import { checkPath } from '../lib/project.mjs'
import { agent, approvals, boot as bootWith, call, mode } from './harness.mjs'

const PY = process.platform === 'win32' ? 'python' : 'python3'
const PACKAGE = path.resolve(import.meta.dirname, '../..')
const TABLE = JSON.parse(readFileSync(path.resolve(import.meta.dirname, '../../core/tests/policy_cases.json'), 'utf8'))
// tools/state.py and tools/dispatch.py are written by another track; the tests
// that need them skip while they are absent instead of failing the suite.
const HAS_STATE = existsSync(path.join(PACKAGE, 'tools', 'state.py'))
const HAS_DISPATCH = existsSync(path.join(PACKAGE, 'tools', 'dispatch.py'))

function project(tasks, { policy = false } = {}) {
  const root = mkdtempSync(path.join(tmpdir(), 'pl-policy-'))
  writeFileSync(path.join(root, 'board.json'), JSON.stringify({ project: 't', profile: 'S', base_branch: 'main', tasks }, null, 2))
  mkdirSync(path.join(root, 'src'))
  writeFileSync(path.join(root, 'src', 'app.py'), 'x = 1\n')
  writeFileSync(path.join(root, 'README.md'), 'readme\n')
  writeFileSync(path.join(root, '.env'), 'SECRET=1\n')
  writeFileSync(path.join(root, 'package.json'), '{"name": "t"}\n')
  mkdirSync(path.join(root, 'secrets'))
  writeFileSync(path.join(root, 'secrets', 'key.json'), '{"k": "v"}\n')
  mkdirSync(path.join(root, 'tasks'))
  for (const entry of tasks) writeFileSync(path.join(root, 'tasks', `${entry.id}.md`), `# ${entry.id}\n`)
  if (policy) writeFileSync(path.join(root, 'policy.json'), JSON.stringify(TABLE.policy, null, 2))
  const git = (...a) => execFileSync('git', ['-C', root, ...a], { stdio: 'pipe' })
  git('init', '-q', '-b', 'main')
  git('config', 'user.email', 't@example.com')
  git('config', 'user.name', 't')
  git('add', '-A')
  git('commit', '-q', '-m', 'chore: scaffold')
  return root
}

function task(id = 'M01', status = 'in_progress', extra = {}) {
  return {
    id, title: `Task ${id}`, goal: 'Do it.', status, depends_on: [], complexity: 2, stage: 1,
    scope_write: ['src/app.py', '.env', 'package.json', 'secrets/'], acceptance: ['A1'], gates: ['tests'], ...extra,
  }
}

/** Every session here may become lead: the owner allows each prompt. */
function boot(config = {}) {
  return bootWith(config, { approval: approvals(...Array(20).fill('allowed-once')) })
}

function approval(root, { id = 'AP-001', action = 'new_dependency', task: bound = 'M01', status = 'granted',
  at = '2026-10-28T12:00:00+00:00' } = {}) {
  const folder = path.join(root, 'reviews', 'approvals')
  mkdirSync(folder, { recursive: true })
  writeFileSync(path.join(folder, `${id}.json`), JSON.stringify({
    id, action, task: bound, status, requested_by: 'worker', requested_at: '2026-10-28T11:00:00+00:00',
    approved_by: status === 'granted' ? 'owner' : null, approved_at: status === 'granted' ? at : null, note: null,
  }))
}

test('the guard denies a protected path and a manifest without an approval', async () => {
  const root = project([task()], { policy: true })
  const { tools } = await boot()
  const a = agent(root)

  const env = await call(tools, a, 'write', { file_path: '.env', content: 'SECRET=2\n' })
  assert.equal(env.error, true)
  assert.match(env.text, /protected path in policy\.json/)
  assert.match(env.text, /Only a lead session may write it/)

  const secrets = await call(tools, a, 'write', { file_path: 'secrets/key.json', content: '{}\n' })
  assert.equal(secrets.error, true)
  assert.match(secrets.text, /protected path/)

  const manifest = await call(tools, a, 'write', { file_path: 'package.json', content: '{"name": "x"}\n' })
  assert.equal(manifest.error, true)
  assert.match(manifest.text, /dependency manifest/)
  assert.match(manifest.text, /pl_approval with action new_dependency and task M01/)
  assert.equal(readFileSync(path.join(root, 'package.json'), 'utf8'), '{"name": "t"}\n')

  // An ordinary in-scope file is untouched by the policy.
  assert.equal((await call(tools, a, 'write', { file_path: 'src/app.py', content: 'x = 2\n' })).error, false)

  // A granted new_dependency approval lets the manifest through.
  approval(root, { id: 'AP-001', action: 'new_dependency' })
  assert.equal((await call(tools, a, 'write', { file_path: 'package.json', content: '{"name": "x"}\n' })).error, false)

  // The protected path stays blocked for a worker even with a grant: only a
  // lead session writes it, so the approval is not a way around it.
  assert.equal((await call(tools, a, 'write', { file_path: '.env', content: 'SECRET=3\n' })).error, true)
  approval(root, { id: 'AP-002', action: 'protected_path', at: '2026-10-28T12:30:00+00:00' })
  assert.equal((await call(tools, a, 'write', { file_path: '.env', content: 'SECRET=3\n' })).error, true)
})

test('without policy.json the 1.0 guard stays exactly as it was', async () => {
  const root = project([task()])
  const { tools } = await boot()
  const a = agent(root)
  assert.equal((await call(tools, a, 'write', { file_path: '.env', content: 'SECRET=2\n' })).error, false)
  assert.equal((await call(tools, a, 'write', { file_path: 'package.json', content: '{"name": "x"}\n' })).error, false)
  const push = await call(tools, a, 'bash', { command: 'git push origin main' })
  assert.equal(push.error, false)
  assert.equal(push.value, 'ran')
})

test('the policy command guard denies deny-list commands for every role', async () => {
  const root = project([task()], { policy: true })
  const { tools } = await boot()

  const worker = agent(root)
  const push = await call(tools, worker, 'bash', { command: 'git push origin main' })
  assert.equal(push.error, true)
  assert.match(push.text, /command blocked/)
  assert.match(push.text, /deny rule "git push\*"/)

  const publish = await call(tools, worker, 'bash', { command: 'cd /tmp && npm publish --access public' })
  assert.equal(publish.error, true)

  // Text in quotes is data, not a command.
  assert.equal((await call(tools, worker, 'bash', { command: 'echo "git push origin main"' })).error, false)
  // A normal command passes.
  assert.equal((await call(tools, worker, 'bash', { command: 'git status' })).error, false)

  const lead = agent(root)
  await mode(tools, lead, 'lead')
  const leadPush = await call(tools, lead, 'bash', { command: 'git push origin main' })
  assert.equal(leadPush.error, true, 'nobody bypasses a deny command')
})

test('lead-only commands are refused to workers and reviewers, allowed to the lead', async () => {
  const root = project([task()], { policy: true })
  const { tools } = await boot()
  const command = 'python3 tools/state.py set M03 in_progress'

  const worker = agent(root)
  const refused = await call(tools, worker, 'bash', { command })
  assert.equal(refused.error, true)
  assert.match(refused.text, /lead-only rule/)
  assert.match(refused.text, /only the lead session may run it/)

  const reviewer = agent(root)
  await mode(tools, reviewer, 'reviewer')
  assert.equal((await call(tools, reviewer, 'bash', { command })).error, true)
  // A reviewer may still read the state.
  assert.equal((await call(tools, reviewer, 'bash', { command: 'python3 tools/state.py show' })).error, false)

  const lead = agent(root)
  await mode(tools, lead, 'lead')
  const allowed = await call(tools, lead, 'bash', { command })
  assert.equal(allowed.error, false)
  assert.equal(allowed.value, 'ran')
})

test('a lead session bypasses the path and dependency rules only', async () => {
  const root = project([task()], { policy: true })
  const { tools } = await boot()
  const lead = agent(root)
  await mode(tools, lead, 'lead')
  assert.equal((await call(tools, lead, 'write', { file_path: '.env', content: 'SECRET=2\n' })).error, false)
  assert.equal((await call(tools, lead, 'write', { file_path: 'package.json', content: '{"name": "x"}\n' })).error, false)
  assert.equal((await call(tools, lead, 'bash', { command: 'git status' })).error, false)
})

test('pl_status reports the policy and the disabled default', async () => {
  const enabledRoot = project([task()], { policy: true })
  const { tools } = await boot()
  const report = await call(tools, agent(enabledRoot), 'pl_status', {})
  assert.equal(report.error, false, report.text)
  assert.deepEqual(report.value.policy.protected_paths.slice(0, 1), ['.env'])
  assert.deepEqual(report.value.policy.limits, { max_attempts_per_task: 3, max_in_progress: 2, max_review_rounds: 3 })

  const plainRoot = project([task()])
  const plain = await call(tools, agent(plainRoot), 'pl_status', {})
  assert.deepEqual(plain.value.policy, { enabled: false })
})

test('pl_next returns the dispatch plan', { skip: HAS_DISPATCH ? false : 'tools/dispatch.py not present yet' }, async () => {
  const root = project([task('M01', 'pending'), task('M02', 'pending', { depends_on: ['M01'] })])
  const { tools } = await boot({ python: PY })
  const a = agent(root)
  const plan = await call(tools, a, 'pl_next', {})
  assert.equal(plan.error, false, plan.text)
  assert.equal(plan.value.project, 't')
  assert.ok(Array.isArray(plan.value.next))
  assert.ok(Array.isArray(plan.value.waves))
  assert.ok(plan.value.waves.flat().some((item) => item.id === 'M01'))
})

test('pl_state shows state and only a lead session may set it', { skip: HAS_STATE ? false : 'tools/state.py not present yet' }, async () => {
  const root = project([task()], { policy: true })
  const { tools } = await boot({ python: PY })
  const worker = agent(root)

  const refused = await call(tools, worker, 'pl_state', { action: 'set', task: 'M01', status: 'blocked', note: 'waiting' })
  assert.equal(refused.error, true)
  assert.match(refused.text, /lead session changes task state/)

  const lead = agent(root)
  await mode(tools, lead, 'lead')
  const shown = await call(tools, lead, 'pl_state', { task: 'M01' })
  assert.equal(shown.error, false, shown.text)
  assert.ok(shown.value && typeof shown.value === 'object')

  const moved = await call(tools, lead, 'pl_state', { action: 'set', task: 'M01', status: 'blocked', note: 'waiting for the owner' })
  assert.equal(moved.error, false, moved.text)
  assert.equal(moved.value.ok, true, moved.text)
  const board = JSON.parse(readFileSync(path.join(root, 'board.json'), 'utf8'))
  assert.equal(board.tasks[0].status, 'blocked')
})

test('the JS guard mirror marks run records lead-owned and approvals reviewer-blocked', () => {
  const tasks = [task()]
  const runs = checkPath('runs/M01.json', tasks, 'worker')
  assert.equal(runs.ok, false)
  assert.equal(runs.code, 'lead-owned')
  assert.equal(checkPath('reviews/M01.md', tasks, 'reviewer').ok, true)
  const approvals = checkPath('reviews/approvals/AP-001.json', tasks, 'reviewer')
  assert.equal(approvals.ok, false)
  assert.equal(approvals.code, 'approvals')
})

test('a denied command is a denial in ask mode as well, never a question', async () => {
  const root = project([task()], { policy: true })
  const { tools } = await boot({ enforce: 'ask', python: PY })
  const push = await call(tools, agent(root), 'bash', { command: 'git push origin main' })
  assert.equal(push.error, true)
  assert.match(push.text, /command blocked/)
  assert.match(push.text, /applies to every role/)
})
