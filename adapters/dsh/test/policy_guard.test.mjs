// The policy guard of the DSH plugin, on a throwaway git project with a real
// policy.json: protected paths, dependency manifests with approvals, denied
// commands, lead-only commands, and the /pl next, /pl policy, pl_next and
// pl_state surfaces. Boots the real tool registry. Run: npm test
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'

import { Context } from '@deepseek-ai/cordis'
import SystemPrompt from '@deepseek-ai/dsh-system-prompt'
import ToolRuntime from '@deepseek-ai/dsh-tools'

import * as plugin from '../index.mjs'
import { checkPath } from '../lib/project.mjs'

const PY = process.platform === 'win32' ? 'python' : 'python3'
const PACKAGE = path.resolve(import.meta.dirname, '../../..')
const TABLE = JSON.parse(readFileSync(path.resolve(import.meta.dirname, '../../../core/tests/policy_cases.json'), 'utf8'))
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

let seq = 0
function agent(cwd) {
  const steered = []
  return { id: `agent-${++seq}`, session: { header: { cwd } }, steer: (m) => steered.push(m), steered }
}

async function boot(config = {}) {
  const ctx = new Context()
  await ctx.plugin(SystemPrompt)
  await ctx.plugin(ToolRuntime)
  await new Promise((resolve) => ctx.inject(['tools'], (c) => {
    c.tools.register({
      name: 'write',
      description: 'write a file',
      parameters: { type: 'object', properties: { file_path: { type: 'string' }, content: { type: 'string' } }, required: ['file_path', 'content'] },
      output: { schema: { type: 'string' }, render: (_a, v) => [{ type: 'text', text: v }] },
      async execute(args, exec) {
        const abs = path.resolve(exec.agent.session.header.cwd, args.file_path)
        mkdirSync(path.dirname(abs), { recursive: true })
        writeFileSync(abs, args.content)
        return 'written'
      },
    })
    c.tools.register({
      name: 'bash',
      description: 'run a shell command',
      parameters: { type: 'object', properties: { command: { type: 'string' } }, required: ['command'] },
      output: { schema: { type: 'string' }, render: (_a, v) => [{ type: 'text', text: String(v) }] },
      async execute() { return 'ran' },
    })
    resolve()
  }))
  await ctx.plugin(plugin, config)
  const tools = await new Promise((resolve) => ctx.inject(['tools'], (c) => resolve(c.tools)))
  return { ctx, tools }
}

async function call(tools, a, name, args) {
  const r = await tools.execute({ callId: `c${++seq}`, name, arguments: args, agent: a, signal: new AbortController().signal })
  const text = r.content.map((b) => b.text).join('')
  let value
  try { value = JSON.parse(text) } catch { value = text }
  return { error: r.isError, text, value }
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

async function role(ctx, a, value) {
  const cmd = plugin.command(ctx, plugin.resolveConfig())
  return cmd.handler({ agent: a, rawInput: value, signal: new AbortController().signal })
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
  assert.match(manifest.text, /tools\/approve\.py request --action new_dependency --task M01/)
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
  const { ctx, tools } = await boot()

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
  await role(ctx, lead, 'lead')
  const leadPush = await call(tools, lead, 'bash', { command: 'git push origin main' })
  assert.equal(leadPush.error, true, 'nobody bypasses a deny command')
})

test('lead-only commands are refused to workers and reviewers, allowed to the lead', async () => {
  const root = project([task()], { policy: true })
  const { ctx, tools } = await boot()
  const command = 'python3 tools/state.py set M03 in_progress'

  const worker = agent(root)
  const refused = await call(tools, worker, 'bash', { command })
  assert.equal(refused.error, true)
  assert.match(refused.text, /lead-only rule/)
  assert.match(refused.text, /only the lead session may run it/)

  const reviewer = agent(root)
  await role(ctx, reviewer, 'reviewer')
  assert.equal((await call(tools, reviewer, 'bash', { command })).error, true)
  // A reviewer may still read the state.
  assert.equal((await call(tools, reviewer, 'bash', { command: 'python3 tools/state.py show' })).error, false)

  const lead = agent(root)
  await role(ctx, lead, 'lead')
  const allowed = await call(tools, lead, 'bash', { command })
  assert.equal(allowed.error, false)
  assert.equal(allowed.value, 'ran')
})

test('a lead session bypasses the path and dependency rules only', async () => {
  const root = project([task()], { policy: true })
  const { ctx, tools } = await boot()
  const lead = agent(root)
  await role(ctx, lead, 'lead')
  assert.equal((await call(tools, lead, 'write', { file_path: '.env', content: 'SECRET=2\n' })).error, false)
  assert.equal((await call(tools, lead, 'write', { file_path: 'package.json', content: '{"name": "x"}\n' })).error, false)
  assert.equal((await call(tools, lead, 'bash', { command: 'git status' })).error, false)
})

test('/pl policy reports the rules and the disabled default; the help lists the new verbs', async () => {
  const enabledRoot = project([task()], { policy: true })
  const enabledBoot = await boot()
  const enabledCmd = plugin.command(enabledBoot.ctx, plugin.resolveConfig())
  const report = await enabledCmd.handler({ agent: agent(enabledRoot), rawInput: 'policy' })
  assert.equal(report.kind, 'success')
  assert.match(report.text, /Policy: enabled/)
  assert.match(report.text, /Protected paths: \.env/)
  assert.match(report.text, /Denied commands: git push\*/)
  assert.match(report.text, /Limits: attempts 3, in progress 2, review rounds 3/)

  const plainRoot = project([task()])
  const plainBoot = await boot()
  const plainCmd = plugin.command(plainBoot.ctx, plugin.resolveConfig())
  const disabled = await plainCmd.handler({ agent: agent(plainRoot), rawInput: 'policy' })
  assert.equal(disabled.kind, 'success')
  assert.match(disabled.text, /Policy: disabled/)

  const help = await enabledCmd.handler({ agent: agent(enabledRoot), rawInput: 'nonsense' })
  assert.match(help.text, /\/pl next/)
  assert.match(help.text, /\/pl policy/)
})

test('pl_next returns the dispatch plan', { skip: HAS_DISPATCH ? false : 'tools/dispatch.py not present yet' }, async () => {
  const root = project([task('M01', 'pending'), task('M02', 'pending', { depends_on: ['M01'] })])
  const { ctx, tools } = await boot({ python: PY })
  const a = agent(root)
  const plan = await call(tools, a, 'pl_next', {})
  assert.equal(plan.error, false, plan.text)
  assert.equal(plan.value.project, 't')
  assert.ok(Array.isArray(plan.value.next))
  assert.ok(Array.isArray(plan.value.waves))
  assert.ok(plan.value.waves.flat().some((item) => item.id === 'M01'))

  const text = await plugin.command(ctx, plugin.resolveConfig({ python: PY }))
    .handler({ agent: a, rawInput: 'next' })
  assert.equal(text.kind, 'success', text.text)
  assert.match(text.text, /M01/)
})

test('pl_state shows state and only a lead session may set it', { skip: HAS_STATE ? false : 'tools/state.py not present yet' }, async () => {
  const root = project([task()], { policy: true })
  const { ctx, tools } = await boot({ python: PY })
  const worker = agent(root)

  const refused = await call(tools, worker, 'pl_state', { action: 'set', task: 'M01', status: 'blocked', note: 'waiting' })
  assert.equal(refused.error, true)
  assert.match(refused.text, /lead session changes task state/)

  const lead = agent(root)
  await role(ctx, lead, 'lead')
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
