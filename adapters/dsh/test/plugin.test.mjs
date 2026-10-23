// Boots the real DeepSeek Harness tool registry, mounts the plugin and drives it
// with a fake agent on a throwaway git project. Run: npm test
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { mkdtempSync, mkdirSync, readFileSync, writeFileSync, existsSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'

import { Context } from '@deepseek-ai/cordis'
import SystemPrompt from '@deepseek-ai/dsh-system-prompt'
import ToolRuntime from '@deepseek-ai/dsh-tools'

import * as plugin from '../index.mjs'

const PY = process.platform === 'win32' ? 'python' : 'python3'

function project(tasks) {
  const root = mkdtempSync(path.join(tmpdir(), 'pl-dsh-'))
  writeFileSync(path.join(root, 'board.json'), JSON.stringify({ project: 't', profile: 'S', base_branch: 'main', tasks }, null, 2))
  mkdirSync(path.join(root, 'src'))
  writeFileSync(path.join(root, 'src/app.py'), 'x = 1\n')
  writeFileSync(path.join(root, 'README.md'), 'readme\n')
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
    scope_write: ['src/app.py'], acceptance: ['A1'], gates: ['tests'], ...extra,
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
  // A stand-in for the harness `write` tool, so the guard has something to stop.
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

test('guard allows writes inside the scope and blocks the rest', async () => {
  const root = project([task()])
  const { tools } = await boot()
  const a = agent(root)
  assert.equal((await call(tools, a, 'write', { file_path: 'src/app.py', content: 'x = 2\n' })).error, false)
  const outside = await call(tools, a, 'write', { file_path: 'README.md', content: 'no' })
  assert.equal(outside.error, true)
  assert.match(outside.text, /outside the write scope of M01/)
  assert.equal(readFileSync(path.join(root, 'README.md'), 'utf8'), 'readme\n')
  const board = await call(tools, a, 'write', { file_path: 'board.json', content: '{}' })
  assert.match(board.text, /lead-owned/)
  const escape = await call(tools, a, 'write', { file_path: '../elsewhere.txt', content: 'x' })
  assert.match(escape.text, /outside the project/)
  const evidence = await call(tools, a, 'write', { file_path: 'reviews/evidence/x.log', content: 'x' })
  assert.notEqual(evidence.text.includes('blocked'), true)
})

test('forbidden paths win and no running task means no guard', async () => {
  const root = project([task('M01', 'in_progress', { scope_write: ['src/'], scope_write_forbidden: ['src/app.py'] })])
  const { tools } = await boot()
  assert.match((await call(tools, agent(root), 'write', { file_path: 'src/app.py', content: 'y' })).text, /scope_write_forbidden/)

  const idle = project([task('M01', 'pending')])
  assert.equal((await call(tools, agent(idle), 'write', { file_path: 'README.md', content: 'ok\n' })).error, false)
})

test('/pl lead lifts the guard for that session only', async () => {
  const root = project([task()])
  const { ctx, tools } = await boot()
  const cmd = plugin.command(ctx, plugin.resolveConfig())
  const lead = agent(root)
  const worker = agent(root)
  const res = await cmd.handler({ agent: lead, rawInput: 'lead', signal: new AbortController().signal })
  assert.equal(res.kind, 'success')
  assert.equal((await call(tools, lead, 'write', { file_path: 'README.md', content: 'lead\n' })).error, false)
  assert.equal((await call(tools, worker, 'write', { file_path: 'README.md', content: 'w\n' })).error, true)
  await cmd.handler({ agent: lead, rawInput: 'worker' })
  assert.equal((await call(tools, lead, 'write', { file_path: 'README.md', content: 'x\n' })).error, true)
})

test('/pl reviewer may write only under reviews/, with or without a running task', async () => {
  for (const status of ['in_progress', 'pending']) {
    const root = project([task('M01', status)])
    const { ctx, tools } = await boot()
    const cmd = plugin.command(ctx, plugin.resolveConfig())
    const r = agent(root)
    await cmd.handler({ agent: r, rawInput: 'reviewer' })
    assert.equal((await call(tools, r, 'write', { file_path: 'reviews/M01.md', content: 'verdict: pass\n' })).error, false)
    const code = await call(tools, r, 'write', { file_path: 'src/app.py', content: 'x = 9\n' })
    assert.equal(code.error, true)
    assert.match(code.text, /reviewer session writes only under reviews/)
  }
})

test('/pl task binds a session when several tasks run', async () => {
  const root = project([task('M01'), task('M02', 'in_progress', { scope_write: ['README.md'] })])
  const { ctx, tools } = await boot()
  const a = agent(root)
  // Unbound: the union of both scopes applies.
  assert.equal((await call(tools, a, 'write', { file_path: 'README.md', content: '1\n' })).error, false)
  const cmd = plugin.command(ctx, plugin.resolveConfig())
  await cmd.handler({ agent: a, rawInput: 'task m01' })
  assert.equal((await call(tools, a, 'write', { file_path: 'README.md', content: '2\n' })).error, true)
})

test('enforce off and ask', async () => {
  const root = project([task()])
  const off = await boot({ enforce: 'off' })
  assert.equal((await call(off.tools, agent(root), 'write', { file_path: 'README.md', content: 'x\n' })).error, false)
  // ask without an approval service turns into a denial
  const ask = await boot({ enforce: 'ask' })
  assert.equal((await call(ask.tools, agent(root), 'write', { file_path: 'README.md', content: 'y\n' })).error, true)
})

test('pl_status lists the running and ready tasks with handoffs', async () => {
  const root = project([
    task('M01', 'done', { handoff: ['use uv'], evidence: ['x'] }),
    task('M02', 'in_progress'),
    task('M03', 'pending', { depends_on: ['M01'] }),
  ])
  const { tools } = await boot()
  const { error, value } = await call(tools, agent(root), 'pl_status', {})
  assert.equal(error, false)
  assert.equal(value.running[0].id, 'M02')
  assert.deepEqual(value.running[0].scope_write, ['src/app.py'])
  assert.equal(value.ready[0].id, 'M03')
  assert.deepEqual(value.ready[0].handoff, ['M01: use uv'])
})

test('pl_gate writes a record and reports pass and fail', async () => {
  const root = project([task()])
  const { tools } = await boot({ python: PY })
  const a = agent(root)
  const pass = await call(tools, a, 'pl_gate', { task: 'M01', gate: 'tests', command: 'echo green' })
  assert.equal(pass.error, false, pass.text)
  assert.equal(pass.value.passed, true)
  assert.ok(existsSync(path.join(root, pass.value.record)))
  const fail = await call(tools, a, 'pl_gate', { task: 'M01', gate: 'tests', command: 'echo red; exit 3' })
  assert.equal(fail.value.passed, false)
  assert.equal(fail.value.exit_code, 3)
  const unknown = await call(tools, a, 'pl_gate', { task: 'M01', gate: 'deploy', command: 'true' })
  assert.equal(unknown.error, true)
  assert.match(unknown.text, /not listed/)
})

test('pl_scope_check and the stop check see writes made outside the tools', async () => {
  const root = project([task()])
  const config = { python: PY }
  const { ctx, tools } = await boot(config)
  const a = agent(root)
  writeFileSync(path.join(root, 'README.md'), 'changed by bash\n')
  const check = await call(tools, a, 'pl_scope_check', {})
  assert.equal(check.value.ok, false)
  assert.equal(check.value.violations[0].path, 'README.md')

  const cfg = plugin.resolveConfig(config)
  for (let i = 0; i < 4; i++) await plugin.onTurnStopping(ctx, cfg, { agent: a, turn: 1 })
  assert.equal(a.steered.length, cfg.maxStopReminders)
  assert.match(a.steered[0].content[0].text, /README.md: outside scope/)
  await plugin.onTurnStopping(ctx, cfg, { agent: a, turn: 2 })
  assert.equal(a.steered.length, cfg.maxStopReminders + 1)
})

test('pl_check runs tools/check.py', async () => {
  const { tools } = await boot({ python: PY })
  const example = path.resolve(import.meta.dirname, '../../../examples/minimal-cli')
  const res = await call(tools, agent(example), 'pl_check', {})
  assert.equal(res.value.ok, true, res.value.output)
})

test('the bundled skill parses', () => {
  const s = plugin.skill()
  assert.equal(s.name, 'polier')
  assert.ok(s.description.length > 50)
  assert.match(s.content, /Package folder/)
})

test('registers tools, the /pl command and the skill with the real services', async () => {
  const Commands = await import('@deepseek-ai/dsh-commands')
  const Skill = await import('@deepseek-ai/dsh-skill')
  const ctx = new Context()
  await ctx.plugin(SystemPrompt)
  await ctx.plugin(ToolRuntime)
  await ctx.plugin(Commands.default ?? Commands)
  await ctx.plugin(Skill.default)
  await ctx.plugin(plugin)
  await new Promise((r) => setTimeout(r, 100))
  const names = ctx.get('tools').schemas().map((s) => s.name)
  for (const n of ['pl_status', 'pl_gate', 'pl_scope_check', 'pl_check']) assert.ok(names.includes(n), n)
  const fake = { id: 'x', ctx, session: { header: {} } }
  assert.deepEqual(ctx.get('commands').list(fake).map((c) => c.name), ['pl'])
  const skills = await ctx.get('skills').list({})
  assert.ok(skills.some((s) => s.name === 'polier'))
})
