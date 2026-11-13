// Boots the real DeepSeek Harness tool registry, mounts the plugin and drives it
// with a fake agent on a throwaway git project. Run: npm test
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import os from 'node:os'
import path from 'node:path'

import { Context } from '@deepseek-ai/cordis'
import SystemPrompt from '@deepseek-ai/dsh-system-prompt'
import * as NativeExecutor from '@deepseek-ai/dsh-tool-executor-native'
import ToolRuntime from '@deepseek-ai/dsh-tools'

import * as plugin from '../index.mjs'
import { readyTasks } from '../lib/project.mjs'
import { agent, approvals, boot, call, mode, project, PY, task } from './harness.mjs'

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

test('pl_mode lead needs the owner and lifts the guard for that session only', async () => {
  const root = project([task()])
  const service = approvals('rejected', 'allowed-once')
  const { tools } = await boot({}, { approval: service })
  const lead = agent(root)
  const worker = agent(root)
  const refused = await mode(tools, lead, 'lead')
  assert.equal(refused.value.ok, false)
  assert.equal(refused.value.approval, 'rejected')
  assert.equal((await call(tools, lead, 'write', { file_path: 'README.md', content: 'no\n' })).error, true)
  assert.equal((await mode(tools, lead, 'lead')).value.ok, true)
  assert.equal(service.asked.length, 2)
  assert.match(service.asked[0], /Polier lead/)
  assert.equal((await call(tools, lead, 'write', { file_path: 'README.md', content: 'lead\n' })).error, false)
  assert.equal((await call(tools, worker, 'write', { file_path: 'README.md', content: 'w\n' })).error, true)
  assert.equal((await mode(tools, lead, 'worker')).value.ok, true)
  assert.equal(service.asked.length, 2, 'stepping down needs no approval')
  assert.equal((await call(tools, lead, 'write', { file_path: 'README.md', content: 'x\n' })).error, true)
})

test('pl_mode lead fails closed without an approval service', async () => {
  const root = project([task()])
  const { tools } = await boot()
  const res = await mode(tools, agent(root), 'lead')
  assert.equal(res.value.ok, false)
  assert.equal(res.value.approval, 'unavailable')
})

test('pl_mode reviewer may write only under reviews/, with or without a running task', async () => {
  for (const status of ['in_progress', 'pending']) {
    const root = project([task('M01', status)])
    const { tools } = await boot()
    const r = agent(root)
    assert.equal((await mode(tools, r, 'reviewer')).value.ok, true)
    assert.equal((await call(tools, r, 'write', { file_path: 'reviews/M01.md', content: 'verdict: pass\n' })).error, false)
    const code = await call(tools, r, 'write', { file_path: 'src/app.py', content: 'x = 9\n' })
    assert.equal(code.error, true)
    assert.match(code.text, /reviewer session writes only under reviews/)
  }
})

test('pl_task binds a session when several tasks run', async () => {
  const root = project([task('M01'), task('M02', 'in_progress', { scope_write: ['README.md'] })])
  const { tools } = await boot()
  const a = agent(root)
  // Unbound: the union of both scopes applies.
  assert.equal((await call(tools, a, 'write', { file_path: 'README.md', content: '1\n' })).error, false)
  assert.equal((await call(tools, a, 'pl_task', { task: 'm01' })).value.bound, 'M01')
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
  assert.match(pass.value.next, /as evidence for tests/)
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
  const example = path.resolve(import.meta.dirname, '../../tests/fixtures/minimal-cli')
  const res = await call(tools, agent(example), 'pl_check', {})
  assert.equal(res.value.ok, true, res.value.output)
})

test('the bundled skill parses', () => {
  const s = plugin.skill()
  assert.equal(s.name, 'polier')
  assert.ok(s.description.length > 50)
  assert.match(s.content, /Package folder/)
})

test('registers the tools, the live context and the skill with the real services', async () => {
  const Skill = await import('@deepseek-ai/dsh-skill')
  const ctx = new Context()
  await ctx.plugin(SystemPrompt)
  await ctx.plugin(ToolRuntime)
  await ctx.plugin(NativeExecutor)
  await ctx.plugin(Skill.default)
  await ctx.plugin(plugin)
  await new Promise((r) => setTimeout(r, 100))
  const names = ctx.get('tools').schemas().map((s) => s.name)
  for (const n of ['pl_preflight', 'pl_status', 'pl_gate', 'pl_scope_check', 'pl_review', 'pl_check', 'pl_next', 'pl_state', 'pl_quick', 'pl_factory', 'pl_mode', 'pl_role', 'pl_task', 'pl_approval']) {
    assert.ok(names.includes(n), n)
  }
  const skills = await ctx.get('skills').list({})
  assert.ok(skills.some((s) => s.name === 'polier'))

  const root = project([task()])
  const assembly = await ctx.get('systemPrompt').assemble({ agent: agent(root) })
  const state = assembly.contexts.find((c) => c.name === 'polier:state')
  assert.match(state.text, /<polier>/)
  assert.match(state.text, /Running: M01/)
  assert.ok(assembly.sections.some((s) => s.name === 'polier:guide' && /AI software factory/.test(s.text)))
  const elsewhere = await ctx.get('systemPrompt').assemble({ agent: agent(path.dirname(root)) })
  assert.equal(elsewhere.contexts.find((c) => c.name === 'polier:state')?.text ?? '', '')
})

// ---------------------------------------------------------------------------
// claims, worktrees + foreign changes, guard extras
// ---------------------------------------------------------------------------

const CLAIM_TOOL = path.resolve(import.meta.dirname, '../../tools/claim.py')

function claimPath(root, id) {
  return path.join(root, '.git', 'polier', 'claims', `${id}.json`)
}

function readClaim(root, id) {
  return JSON.parse(readFileSync(claimPath(root, id), 'utf8'))
}

function claimTakeCli(root, id, harness = 'cli', session = 'other') {
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

test('pl_task takes the claim and pl_status lists the live claims', async () => {
  const root = project([task()])
  const { ctx, tools } = await boot({ python: PY })
  const a = agent(root)
  const res = await call(tools, a, 'pl_task', { task: 'M01' })
  assert.equal(res.value.claimed, true, res.text)
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

test('pl_task refuses a task claimed by another harness and names the holder', async () => {
  const root = project([task()])
  claimTakeCli(root, 'M01', 'cli', 'cli-9')
  const { tools } = await boot()
  const a = agent(root)
  const res = await call(tools, a, 'pl_task', { task: 'M01' })
  assert.equal(res.value.ok, false)
  assert.match(res.value.error, /cli/)
  assert.match(res.value.error, /cli-9/)
  assert.equal(readClaim(root, 'M01').session, 'cli-9')
})

test('tool calls refresh the claim heartbeat at most once per minute', async () => {
  const root = project([task()])
  const { ctx, tools } = await boot({ python: PY })
  const a = agent(root)
  await call(tools, a, 'pl_task', { task: 'M01' })
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
  const { ctx, tools } = await boot()
  const a = agent(root)
  await call(tools, a, 'pl_task', { task: 'M01' })
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
  const config = plugin.resolveConfig({ python: PY })
  await call(tools, a, 'pl_task', { task: 'M01' })
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
  const { tools } = await boot()
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
    const help = execFileSync(PY, [path.resolve(import.meta.dirname, '../../tools/gate.py'), '--help'], { encoding: 'utf8' })
    gateSupportsExclusive.cache = !help.includes('--exclusive')
      ? 'tools/gate.py has no --exclusive yet'
      : !help.includes('--lock-wait') ? 'tools/gate.py has no --lock-wait yet' : false
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

// The ready list of the live context excludes tasks behind an
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

// ---------------------------------------------------------------------------
// factory line
// ---------------------------------------------------------------------------

const FACTORY_TOOL = path.resolve(import.meta.dirname, '../../tools/factory.py')

test('pl_factory works before the board exists and closes a station only with the owner', async () => {
  const root = project(null, { files: { 'project-input.md': '# Input\n' } })
  execFileSync(PY, [FACTORY_TOOL, '--root', root, 'init', '--platforms', 'ios'], { stdio: 'pipe' })
  const service = approvals('rejected', 'allowed-once')
  const { ctx, tools, config } = await boot({}, { approval: service })
  const a = agent(root)
  const status = await call(tools, a, 'pl_factory', { action: 'status' })
  assert.equal(status.value.current, 'idea')
  const next = await call(tools, a, 'pl_factory', {})
  assert.equal(next.value.station, 'idea')
  assert.ok(next.value.items.some((item) => item.id === 'IDEA-01'))

  const batch = await call(tools, a, 'pl_factory', {
    action: 'done',
    batch: ['IDEA-01', 'IDEA-02', 'IDEA-03', 'IDEA-04'].map((item) => ({ item, evidence: ['project-input.md'] })),
  })
  assert.equal(batch.value.ok, true, batch.text)
  assert.equal(batch.value.results.length, 4)
  assert.equal((await call(tools, a, 'pl_factory', { action: 'done', item: 'IDEA-05', evidence: ['factory.json'] })).value.ok, true)
  const noEvidence = await call(tools, a, 'pl_factory', { action: 'done', item: 'IDEA-06', evidence: ['missing.md'] })
  assert.equal(noEvidence.value.ok, false)
  assert.equal((await call(tools, a, 'pl_factory', { action: 'defer', item: 'IDEA-06', reason: 'no budget yet' })).value.ok, true)
  assert.ok(existsSync(path.join(root, 'docs', 'factory.md')), 'docs/factory.md is rendered on its own')

  const rejected = await call(tools, a, 'pl_factory', { action: 'advance' })
  assert.equal(rejected.value.ok, false)
  assert.equal(rejected.value.approval, 'rejected')
  const closed = await call(tools, a, 'pl_factory', { action: 'advance' })
  assert.equal(closed.value.ok, true, closed.text)
  assert.match(service.asked[0], /station "idea"/)
  const line = JSON.parse(readFileSync(path.join(root, 'factory.json'), 'utf8'))
  assert.equal(line.stations.idea.approved_by, 'owner (approved in DSH)')

  const snapshot = plugin.liveContext(ctx, config, a)
  assert.match(snapshot, /Factory: station concept \(2\/9/)
  assert.match(snapshot, /CON-02 Prioritised feature list/)
})

test('tool results name pl_* tools, and pl_review packs a task for the reviewer', async () => {
  const root = project([task('M01', 'in_progress', { gates: ['tests'] })])
  const { tools } = await boot({}, { approval: approvals('allowed-once') })
  const lead = agent(root)
  await mode(tools, lead, 'lead')
  const shown = await call(tools, lead, 'pl_state', { task: 'M01' })
  assert.doesNotMatch(shown.text, /python3? \S*tools\/state\.py/)
  const worker = agent(root)
  await call(tools, worker, 'pl_task', { task: 'M01' })
  await call(tools, worker, 'write', { file_path: 'src/app.py', content: 'x = 2\n' })
  await call(tools, worker, 'pl_gate', { task: 'M01', gate: 'tests', command: `${PY} -c pass` })
  const packet = await call(tools, worker, 'pl_review', { task: 'M01' })
  assert.equal(packet.value.gates_green, true, packet.text)
  assert.deepEqual(packet.value.files, ['src/app.py'])
  assert.match(packet.value.diff, /\+x = 2/)
})

test('pl_preflight checks machine, harness, guard and project without changing anything', async () => {
  const root = project([task('M01', 'in_progress')])
  const { tools } = await boot({}, { approval: approvals() })
  const result = await call(tools, agent(root), 'pl_preflight', {})
  const byName = Object.fromEntries(result.value.checks.map((c) => [c.check, c.level]))
  assert.equal(byName.python, 'ok', result.text)
  assert.equal(byName['write guard'], 'ok', result.text)
  assert.equal(byName['approval prompts'], 'ok')
  assert.equal(byName.board, 'ok')
  assert.ok(result.value.next)
  const outside = await call(tools, agent(os.tmpdir()), 'pl_preflight', {})
  assert.equal(outside.value.project, null)
})

test('pl_factory writes need the lead while tasks run', async () => {
  const root = project([task('M01', 'in_progress')])
  execFileSync(PY, [FACTORY_TOOL, '--root', root, 'init', '--platforms', 'cli'], { stdio: 'pipe' })
  const { tools } = await boot()
  const refused = await call(tools, agent(root), 'pl_factory', { action: 'na', item: 'IDEA-06', reason: 'hobby' })
  assert.equal(refused.error, true)
  assert.match(refused.text, /lead/)
})

test('pl_approval records the owner answer from the prompt', async () => {
  const root = project([task('M01', 'in_progress')])
  const service = approvals('allowed-once', 'rejected')
  const { tools } = await boot({}, { approval: service })
  const a = agent(root)
  const granted = await call(tools, a, 'pl_approval', { action: 'new_dependency', task: 'M01', note: 'adds httpx' })
  assert.equal(granted.value.status, 'granted', granted.text)
  const record = JSON.parse(readFileSync(path.join(root, 'reviews', 'approvals', `${granted.value.id}.json`), 'utf8'))
  assert.equal(record.status, 'granted')
  assert.equal(record.approved_by, 'owner')
  const denied = await call(tools, a, 'pl_approval', { action: 'release', note: 'ship 1.0' })
  assert.equal(denied.value.status, 'denied')
  assert.match(service.asked[0], /new_dependency for M01\. adds httpx/)
})

test('pl_factory init shows the plan, waits for the owner and then writes the line', async () => {
  const root = project(null)
  const service = approvals('rejected', 'allowed-once')
  const { tools } = await boot({}, { approval: service })
  const a = agent(root)
  const refused = await call(tools, a, 'pl_factory', { action: 'init', platforms: ['web'], traits: ['accounts'] })
  assert.equal(refused.value.ok, false)
  assert.equal(existsSync(path.join(root, 'factory.json')), false)
  assert.match(service.asked[0], /Start the Polier line .*checklist items for web/)
  const started = await call(tools, a, 'pl_factory', { action: 'init', platforms: ['web'], traits: ['accounts'] })
  assert.equal(started.value.ok, true, started.text)
  assert.equal(started.value.station, 'idea')
  assert.match(started.value.next, /open item\(s\) in station idea; next: IDEA-01/)
  assert.ok(existsSync(path.join(root, 'docs', 'factory.md')))
  const again = await call(tools, a, 'pl_factory', { action: 'init', platforms: ['web'] })
  assert.match(again.value.error, /already exists/)
})

test('pl_role adds the role instructions and only narrows the session', async () => {
  const root = project([task('M01', 'in_progress', { scope_write: ['src/', 'README.md'] })], {
    files: { 'docs/roles/roles.json': JSON.stringify({ roles: [{ id: 'frontend-builder', name: 'Lena', writes: ['src/ui/'] }] }) },
  })
  const { ctx, tools, config } = await boot()
  const a = agent(root)
  const taken = await call(tools, a, 'pl_role', { role: 'frontend-builder' })
  assert.equal(taken.value.ok, true, taken.text)
  assert.equal(taken.value.mode, 'worker')
  assert.match(plugin.liveContext(ctx, config, a), /Role: Frontend builder \(Lena\)/)
  const assembly = await ctx.get('systemPrompt').assemble({ agent: a })
  assert.ok(assembly.sections.some((s) => s.name === 'polier:role' && /frontend builder on one UI task/.test(s.text)))
  assert.equal((await call(tools, a, 'write', { file_path: 'src/ui/button.js', content: 'x' })).error, false)
  const outside = await call(tools, a, 'write', { file_path: 'src/app.py', content: 'x = 3\n' })
  assert.equal(outside.error, true)
  assert.match(outside.text, /role Frontend builder writes only src\/ui\//)
  const unknown = await call(tools, a, 'pl_role', { role: 'astronaut' })
  assert.equal(unknown.error, true)
  assert.equal((await call(tools, a, 'pl_role', {})).value.role, null)
  assert.equal((await call(tools, a, 'write', { file_path: 'src/app.py', content: 'x = 4\n' })).error, false)
})

test('pl_task gives a builder the task role and leaves a reviewer a reviewer', async () => {
  const root = project([task('M01', 'in_progress', { role: 'backend-builder' })])
  const { tools } = await boot()
  const builder = agent(root)
  const bound = await call(tools, builder, 'pl_task', { task: 'M01' })
  assert.equal(bound.value.role, 'backend-builder', bound.text)
  assert.match(bound.value.next, /tasks\/M01.md/)
  // The builder still holds the claim: a reviewer binds without one.
  const reviewer = agent(root)
  assert.equal((await call(tools, reviewer, 'pl_role', { role: 'reviewer' })).value.mode, 'reviewer')
  const review = await call(tools, reviewer, 'pl_task', { task: 'M01' })
  assert.equal(review.value.role, null, review.text)
  assert.equal(review.value.claimed, false)
  const code = await call(tools, reviewer, 'write', { file_path: 'src/app.py', content: 'x = 9\n' })
  assert.match(code.text, /reviewer session writes only under reviews/)
})

const closedLine = { 'factory.json': JSON.stringify({ stations: { build: { status: 'done' } } }), 'docs/quality.md': '- D1 It works.\n' }
const quickArgs = { title: 'Fix the crash on empty input', scope: ['src/app.py'], accept: ['WHEN the input is empty, THEN the app exits with a message'], satisfies: ['D1'] }

test('pl_quick: a lead creates the quick task, a refusal is a result, a bad request is a tool error', async () => {
  const root = project([task('M01', 'done')], { files: closedLine })
  const { tools } = await boot({}, { approval: approvals('allowed-once') })
  const lead = agent(root)
  await mode(tools, lead, 'lead')
  const created = await call(tools, lead, 'pl_quick', quickArgs)
  assert.equal(created.error, false, created.text)
  assert.equal(created.value.ok, true)
  assert.equal(created.value.task, 'M02')
  assert.ok(created.value.next)
  const board = JSON.parse(readFileSync(path.join(root, 'board.json'), 'utf8'))
  assert.equal(board.tasks.find((t) => t.id === 'M02').track, 'quick')
  assert.ok(existsSync(path.join(root, 'tasks/M02.md')))

  const refused = await call(tools, lead, 'pl_quick', { ...quickArgs, title: 'Another one' })
  assert.equal(refused.error, false)
  assert.equal(refused.value.ok, false)
  assert.match(refused.value.reasons.join(' '), /M02/)
  assert.ok(refused.value.next)

  const none = await call(tools, lead, 'pl_quick', { ...quickArgs, accept: [] })
  assert.equal(none.error, true)
  assert.match(none.text, /WHEN/)
  const asString = await call(tools, lead, 'pl_quick', { ...quickArgs, scope: 'src/app.py', title: 'Third' })
  assert.equal(asString.value.ok, false)
})

test('pl_quick: a worker is refused with the way to lead mode and nothing is written', async () => {
  const root = project([task('M01', 'done')], { files: closedLine })
  const before = readFileSync(path.join(root, 'board.json'), 'utf8')
  const { tools } = await boot({}, { approval: approvals() })
  const refused = await call(tools, agent(root), 'pl_quick', quickArgs)
  assert.equal(refused.error, true)
  assert.match(refused.text, /pl_mode lead/)
  assert.equal(readFileSync(path.join(root, 'board.json'), 'utf8'), before)
  assert.equal(existsSync(path.join(root, 'tasks/M02.md')), false)
})
