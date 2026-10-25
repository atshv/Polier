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
import { readyTasks } from '../lib/project.mjs'

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

// ---------------------------------------------------------------------------
// PL-04 claims, PL-05 worktrees + foreign changes, PL-16 guard extras
// ---------------------------------------------------------------------------

import { checkPath, inside } from '../lib/project.mjs'

const CLAIM_TOOL = path.resolve(import.meta.dirname, '../../../tools/claim.py')

function claimPath(root, id) {
  return path.join(root, '.git', 'polier', 'claims', `${id}.json`)
}

function readClaim(root, id) {
  return JSON.parse(readFileSync(claimPath(root, id), 'utf8'))
}

function claimTakeCli(root, id, harness = 'claude-code', session = 'other') {
  execFileSync(PY, [CLAIM_TOOL, 'take', id, '--harness', harness, '--session', session, '--root', root], { stdio: 'pipe' })
}

function setBoard(root, changes = {}, taskChanges = {}) {
  const file = path.join(root, 'board.json')
  const board = JSON.parse(readFileSync(file, 'utf8'))
  Object.assign(board, changes)
  for (const t of board.tasks) Object.assign(t, taskChanges)
  writeFileSync(file, JSON.stringify(board, null, 2))
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function waitFor(check, timeoutMs = 5000) {
  const end = Date.now() + timeoutMs
  while (Date.now() < end) {
    if (await check()) return true
    await sleep(25)
  }
  return false
}

/** boot() plus a stand-in for the harness `bash` tool (the kill warning guards it). */
async function bootWithBash(config = {}) {
  const booted = await boot(config)
  await new Promise((resolve) => booted.ctx.inject(['tools'], (c) => {
    c.tools.register({
      name: 'bash',
      description: 'run a shell command',
      parameters: { type: 'object', properties: { command: { type: 'string' } }, required: ['command'] },
      output: { schema: { type: 'string' }, render: (_a, v) => [{ type: 'text', text: String(v) }] },
      async execute() { return 'ran' },
    })
    resolve()
  }))
  return booted
}

test('/pl task takes the claim and pl_status lists the live claims', async () => {
  const root = project([task()])
  const { ctx, tools } = await boot({ python: PY })
  const a = agent(root)
  const cmd = plugin.command(ctx, plugin.resolveConfig({ python: PY }))
  const res = await cmd.handler({ agent: a, rawInput: 'task m01', signal: new AbortController().signal })
  assert.equal(res.kind, 'success', res.text)
  const claim = readClaim(root, 'M01')
  assert.equal(claim.task, 'M01')
  assert.equal(claim.harness, 'dsh')
  assert.equal(claim.session, a.id)
  const status = await call(tools, a, 'pl_status', {})
  assert.equal(status.error, false)
  assert.equal(status.value.claims.length, 1)
  assert.equal(status.value.claims[0].task, 'M01')
  assert.equal(status.value.claims[0].harness, 'dsh')
})

test('/pl task refuses a task claimed by another harness and names the holder', async () => {
  const root = project([task()])
  claimTakeCli(root, 'M01', 'claude-code', 'claude-9')
  const { ctx } = await boot({ python: PY })
  const a = agent(root)
  const cmd = plugin.command(ctx, plugin.resolveConfig({ python: PY }))
  const res = await cmd.handler({ agent: a, rawInput: 'task m01' })
  assert.equal(res.kind, 'error')
  assert.match(res.text, /claude-code/)
  assert.match(res.text, /claude-9/)
  assert.equal(readClaim(root, 'M01').session, 'claude-9')
})

test('tool calls refresh the claim heartbeat at most once per minute', async () => {
  const root = project([task()])
  const { ctx, tools } = await boot({ python: PY })
  const a = agent(root)
  const cmd = plugin.command(ctx, plugin.resolveConfig({ python: PY }))
  await cmd.handler({ agent: a, rawInput: 'task m01' })
  const stale = () => {
    const claim = readClaim(root, 'M01')
    claim.heartbeat = '2020-01-01T00:00:00+00:00'
    writeFileSync(claimPath(root, 'M01'), JSON.stringify(claim))
  }
  stale()
  assert.equal((await call(tools, a, 'write', { file_path: 'src/app.py', content: 'x = 2\n' })).error, false)
  assert.notEqual(readClaim(root, 'M01').heartbeat, '2020-01-01T00:00:00+00:00')
  // Second call within the same minute: throttled, the heartbeat stays as it is.
  stale()
  assert.equal((await call(tools, a, 'write', { file_path: 'src/app.py', content: 'x = 3\n' })).error, false)
  assert.equal(readClaim(root, 'M01').heartbeat, '2020-01-01T00:00:00+00:00')
})

test('disposing an agent releases the claims it held', async () => {
  const root = project([task()])
  const { ctx } = await boot({ python: PY })
  const a = agent(root)
  const cmd = plugin.command(ctx, plugin.resolveConfig({ python: PY }))
  await cmd.handler({ agent: a, rawInput: 'task m01' })
  assert.ok(existsSync(claimPath(root, 'M01')))
  ctx.emit('agent/disposed', { agent: a })
  assert.ok(await waitFor(() => !existsSync(claimPath(root, 'M01'))))
})

test('the guard denies writes in the main checkout when worktrees are required', async () => {
  const root = project([task()])
  setBoard(root, { profile: 'M', schema_version: '1.0' }, { worktree: '/somewhere/repo-M01' })
  const { tools } = await boot()
  const a = agent(root)
  const blocked = await call(tools, a, 'write', { file_path: 'src/app.py', content: 'x' })
  assert.equal(blocked.error, true)
  assert.match(blocked.text, /work in \/somewhere\/repo-M01/)
  const evidence = await call(tools, a, 'write', { file_path: 'reviews/evidence/x.log', content: 'x' })
  assert.equal(evidence.error, false)
})

test('foreign changes are reported separately and do not trigger the stop reminder', async () => {
  const root = project([task('M01'), task('M02', 'pending', { scope_write: ['docs/'] })])
  claimTakeCli(root, 'M02', 'dsh', 'other-agent')
  const { ctx, tools } = await boot({ python: PY })
  const a = agent(root)
  const cmd = plugin.command(ctx, plugin.resolveConfig({ python: PY }))
  const config = plugin.resolveConfig({ python: PY })
  await cmd.handler({ agent: a, rawInput: 'task m01' })
  mkdirSync(path.join(root, 'docs'), { recursive: true })
  writeFileSync(path.join(root, 'docs', 'x.md'), 'foreign\n')

  const check = await call(tools, a, 'pl_scope_check', {})
  assert.equal(check.error, false)
  assert.equal(check.value.ok, true)
  assert.deepEqual(check.value.violations, [])
  assert.equal(check.value.foreign.length, 1)
  assert.equal(check.value.foreign[0].task, 'M02')
  assert.equal(check.value.foreign[0].harness, 'dsh')
  assert.match(check.value.foreign_changes[0], /foreign changes \(task M02, harness dsh\)/)

  await plugin.onTurnStopping(ctx, config, { agent: a, turn: 1 })
  assert.equal(a.steered.length, 0, 'foreign changes alone must not trigger the reminder')

  writeFileSync(path.join(root, 'README.md'), 'changed\n')
  await plugin.onTurnStopping(ctx, config, { agent: a, turn: 2 })
  assert.equal(a.steered.length, 1)
  assert.match(a.steered[0].content[0].text, /README.md: outside scope/)
  assert.match(a.steered[0].content[0].text, /foreign changes \(task M02, harness dsh\)/)
})

test('a bash kill command steers once per turn and is never a denial', async () => {
  const root = project([task()])
  const { tools } = await bootWithBash()
  const a = agent(root)
  const first = await call(tools, a, 'bash', { command: "pkill -f 'next dev'" })
  assert.equal(first.error, false)
  assert.equal(a.steered.length, 1)
  assert.match(a.steered[0].content[0].text,
    /do not stop processes you did not start; use your slot's ports/)
  await call(tools, a, 'bash', { command: 'kill 123' })
  assert.equal(a.steered.length, 1)
  const plain = await call(tools, a, 'bash', { command: 'echo kill' })
  assert.equal(plain.error, false)
  assert.equal(a.steered.length, 1)
})

test('the JS guard mirrors the case rule and the worktree rule', () => {
  const caseInsensitive = process.platform === 'darwin' || process.platform === 'win32'
  assert.equal(inside('Board.json', 'board.json'), caseInsensitive)
  assert.equal(inside('SRC/a.py', 'src'), caseInsensitive)
  assert.equal(inside('src/a.py', 'src'), true)

  const root = project([task()])
  const tasks = [{ id: 'M01', status: 'in_progress', scope_write: ['src/app.py'], worktree: '/tmp/repo-M01' }]
  const denied = checkPath('src/app.py', tasks, 'worker', { board: { profile: 'M', schema_version: '1.0', tasks }, root, cwd: root })
  assert.equal(denied.ok, false)
  assert.equal(denied.code, 'worktree')
  assert.match(denied.reason, /work in \/tmp\/repo-M01/)
  assert.equal(checkPath('src/app.py', tasks).ok, true, 'three arguments keep the old behaviour')
  assert.equal(checkPath('reviews/evidence/a.log', tasks, 'worker', { board: { profile: 'M' }, root }).ok, true)
  assert.equal(checkPath('src/app.py', tasks, 'worker', { board: { profile: 'S' }, root }).ok, true)
})

test('pl_gate passes the slot and the exclusive resources of the task', { skip: gateSupportsExclusive() }, async () => {
  const root = project([task('M01', 'in_progress', { exclusive: ['e2e'] })])
  setBoard(root, { schema_version: '1.0' })
  writeFileSync(path.join(root, '.polier-slot'), JSON.stringify({ slot: 0, worktree: root }))
  const { tools } = await boot({ python: PY })
  const result = await call(tools, agent(root), 'pl_gate', { task: 'M01', gate: 'tests', command: 'echo green' })
  assert.equal(result.error, false, result.text)
  assert.equal(result.value.passed, true, result.text)
  assert.equal(result.value.busy, false)
  const record = JSON.parse(readFileSync(path.join(root, result.value.record), 'utf8'))
  assert.equal(record.slot, 0)
  assert.deepEqual(record.exclusive, ['e2e'])

  // A gate that never ran because the resource is busy exits 75.
  const holder = {
    task: 'M01', slot: 0, harness: 'cli', pid: process.pid, host: osHostname(),
    started: new Date().toISOString(),
  }
  mkdirSync(path.join(root, '.git', 'polier', 'locks'), { recursive: true })
  writeFileSync(path.join(root, '.git', 'polier', 'locks', 'e2e.lock'), JSON.stringify(holder))
  const busy = await call(tools, agent(root), 'pl_gate', { task: 'M01', gate: 'tests', command: 'echo never' })
  assert.equal(busy.error, false, busy.text)
  assert.equal(busy.value.busy, true)
  assert.equal(busy.value.exit_code, 75)
  assert.match(busy.value.summary, /resource busy, rerun alone/)
  assert.ok(existsSync(path.join(root, busy.value.record)), 'the busy record is kept')
})

function gateSupportsExclusive() {
  if (gateSupportsExclusive.cache !== undefined) return gateSupportsExclusive.cache
  try {
    const help = execFileSync(PY, [path.resolve(import.meta.dirname, '../../../tools/gate.py'), '--help'], { encoding: 'utf8' })
    gateSupportsExclusive.cache = !help.includes('--exclusive')
      ? 'tools/gate.py has no --exclusive yet (PL-03)'
      : !help.includes('--lock-wait') ? 'tools/gate.py has no --lock-wait yet (PL-03)' : false
  } catch {
    gateSupportsExclusive.cache = 'tools/gate.py not runnable'
  }
  return gateSupportsExclusive.cache
}

function osHostname() {
  try {
    return execFileSync(PY, ['-c', 'import socket; print(socket.gethostname())'], { encoding: 'utf8' }).trim() || 'localhost'
  } catch {
    return 'localhost'
  }
}

// PL-08: the JS mirror of core.board.ready_tasks excludes tasks behind an
// incomplete stage (owner decision pending) and lets them through once the
// stage's exit gates are evidenced and the owner continues.
test('ready tasks respect stage exit gates and the owner decision', () => {
  const stages = [
    { id: 'foundation', title: 'Foundation', exit_gates: ['tests'] },
    { id: 'engine', title: 'Engine', depends_on: ['foundation'], exit_gates: ['wasm-build'],
      owner_decision: 'pending' },
    { id: 'web', title: 'Web', depends_on: ['engine'] },
  ]
  const tasks = [
    { id: 'F-01', title: 'Scaffold', status: 'done', stage: 'foundation', gates: ['tests'],
      evidence: ['reviews/evidence/F-01-tests-1.json'], depends_on: [] },
    { id: 'ENG-01', title: 'Spike', status: 'pending', stage: 'engine', depends_on: ['F-01'],
      gates: ['wasm-build'] },
    { id: 'WEB-01', title: 'App', status: 'pending', stage: 'web', depends_on: ['F-01'],
      gates: ['e2e'] },
  ]
  const board = { project: 't', profile: 'L', base_branch: 'main', schema_version: '1.0', stages, tasks }
  assert.deepEqual(readyTasks(board).map((t) => t.id), ['ENG-01'])

  const continued = JSON.parse(JSON.stringify(board))
  continued.stages[1].owner_decision = 'continue'
  continued.tasks[1].status = 'done'
  continued.tasks[1].evidence = ['reviews/evidence/ENG-01-wasm-build-1.json']
  assert.deepEqual(readyTasks(continued).map((t) => t.id), ['WEB-01'])
})
