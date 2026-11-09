// The model-facing tools. Reads are free; every write goes through the
// package's Python tools so there is one implementation, and every human
// decision (lead mode, closing a station, an approval) is a DSH approval
// prompt the owner answers, never a chat message.

import { existsSync } from 'node:fs'
import path from 'node:path'

import { scopeCheck } from './guard.mjs'
import {
  approver, enabled as policyEnabled, limits, loadPolicy, pendingApprovals, ACTIONS,
} from './policy.mjs'
import { activeTasks, findProject, loadBoard, readyTasks } from './project.mjs'
import { agentCwd, run } from './run.mjs'
import { context, liveClaims, polierSlot, releaseClaim, ROLES, stateOf, takeClaim } from './session.mjs'

const ANY = {}
const PROJECT = { type: 'string', description: 'Project folder. Default: the session directory or the nearest parent with board.json or factory.json.' }

// The Python tools print their headless commands; inside DSH the agent calls the pl_* tools.
const TOOL_WORDS = [
  [/python3? (?:\S*\/)?tools\/state\.py set (\S+) (\S+)/g, 'pl_state (task $1, status $2)'],
  [/python3? (?:\S*\/)?tools\/state\.py show (\S+?)(?: --json)?(?=[\s"',;)]|$)/g, 'pl_state (task $1)'],
  [/python3? (?:\S*\/)?tools\/state\.py show(?: --json)?/g, 'pl_state'],
  [/python3? (?:\S*\/)?tools\/dispatch\.py(?: --json)?/g, 'pl_next'],
  [/python3? (?:\S*\/)?tools\/approve\.py request --action (\S+)/g, 'pl_approval (action $1)'],
  [/python3? (?:\S*\/)?tools\/approve\.py (?:grant|deny) \S+ --by \S+/g, 'the owner answers the pl_approval prompt'],
  [/python3? (?:\S*\/)?tools\/render_status\.py[^"\n]*/g, 'pl_check (regenerates STATUS.md)'],
]

function toolWords(value) {
  if (typeof value === 'string') return TOOL_WORDS.reduce((text, [pattern, words]) => text.replace(pattern, words), value)
  if (Array.isArray(value)) return value.map(toolWords)
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, toolWords(v)]))
  return value
}

function jsonTool(def) {
  return { ...def, output: { schema: ANY, render: (_args, value) => [{ type: 'text', text: JSON.stringify(toolWords(value), null, 2) }] } }
}

function projectRoot(ctx, agent, project) {
  const base = agentCwd(ctx, agent)
  const root = findProject(project ? path.resolve(base, project) : base)
  if (!root) throw new Error('no board.json or factory.json in this folder or above. To start a Polier project here, write project-input.md and call pl_factory with action init, platforms and traits.')
  return root
}

function needBoard(ctx, agent, project) {
  const root = projectRoot(ctx, agent, project)
  const board = loadBoard(root)
  if (!board) throw new Error(`board.json in ${root} is missing or invalid; the plan station writes it`)
  return { root, board }
}

function lastJson(stdout) {
  const text = String(stdout ?? '').trim()
  if (!text) return undefined
  for (const candidate of [text, text.split('\n').pop()]) {
    try {
      return JSON.parse(candidate)
    } catch { /* try the next candidate */ }
  }
  return undefined
}

function outputOf(result) {
  return (result.stdout + result.stderr).trim().slice(-6000)
}

function py(config, file, ...args) {
  return [config.python, path.join(config.tools, file), ...args]
}

/** Ask the human through the harness approval service; fails closed without one. */
async function askOwner(ctx, exec, reason) {
  const service = ctx.get?.('approval')
  if (!service || typeof service.request !== 'function') {
    return { ok: false, outcome: 'unavailable', note: 'no approval prompt in this harness profile; the owner runs the matching tools/*.py command instead' }
  }
  const outcome = await service.request({
    agent: exec.agent, toolName: exec.name, callId: exec.callId, reason, displayReason: { en: reason }, signal: exec.signal,
  })
  return { ok: outcome === 'allowed-once', outcome }
}

/** Planning without a running task needs no lead mode: there is nothing to protect yet. */
function mayPlan(agent, root) {
  if (stateOf(agent).role === 'lead') return true
  const board = loadBoard(root)
  return !board || !(board.tasks ?? []).some((t) => ['in_progress', 'verifying', 'review'].includes(t?.status))
}

async function render(ctx, config, agent, root, signal) {
  try {
    if (existsSync(path.join(root, 'board.json'))) {
      await run(ctx, agent, py(config, 'render_status.py', root), { cwd: root, timeoutMs: 60_000, signal })
    }
    if (existsSync(path.join(root, 'factory.json'))) {
      await run(ctx, agent, py(config, 'factory.py', '--root', root, 'render'), { cwd: root, timeoutMs: 60_000, signal })
    }
  } catch { /* the record is written; a stale page is check.py's finding */ }
}

export function tools(ctx, config) {
  const preflight = jsonTool({
    name: 'pl_preflight',
    description: 'Check that everything is in place before work starts or continues: Python, git, the Polier package, the harness services Polier uses (approval prompts, shell), the write guard and, inside a project, git state, factory.json, board.json, policy.json, STATUS.md and claims. Changes nothing; every problem comes with its fix.',
    parameters: { type: 'object', properties: { project: PROJECT } },
    isConcurrencySafe: () => true,
    async execute(args, exec) {
      const where = path.resolve(agentCwd(ctx, exec.agent), String(args.project ?? '.'))
      const checks = []
      let result
      try {
        const ran = await run(ctx, exec.agent, py(config, 'preflight.py', where, '--json'), { cwd: where, timeoutMs: 60_000, signal: exec.signal, preferShell: false })
        result = lastJson(ran.stdout)
        if (!result) checks.push({ check: 'python', level: 'fail', detail: `${config.python} did not answer: ${(ran.stderr || ran.stdout || `exit ${ran.code}`).trim().slice(-300)}`, fix: 'set the plugin option python to a Python 3.9+ interpreter' })
      } catch (error) {
        checks.push({ check: 'python', level: 'fail', detail: `${config.python} cannot be started: ${String(error?.message ?? error)}`, fix: 'install Python 3.9+ or set the plugin option python' })
      }
      if (result) checks.push(...result.checks)
      const approval = ctx.get?.('approval')
      checks.push(approval && typeof approval.request === 'function'
        ? { check: 'approval prompts', level: 'ok', detail: 'owner decisions open a DSH approval prompt' }
        : { check: 'approval prompts', level: 'warn', detail: 'no approval service: station closes, lead mode and approvals fail closed', fix: 'enable dsh-user-approval in the profile, or let the owner run tools/*.py by hand' })
      checks.push(ctx.get?.('shell')
        ? { check: 'shell', level: 'ok', detail: 'gates run in the harness shell' }
        : { check: 'shell', level: 'warn', detail: 'no harness shell: gates run as plain processes without the sandbox', fix: 'enable a tool executor with a shell in the profile' })
      if (config.enforce === 'off') {
        checks.push({ check: 'write guard', level: 'warn', detail: 'enforce is off: writes outside the task scope are not blocked', fix: 'set the plugin option enforce to deny' })
      } else if (result?.project) {
        const info = context(ctx, exec.agent)
        const probe = info ? await run(ctx, exec.agent, [config.python, path.join(config.tools, 'guard.py'), JSON.stringify({ root: info.root, cwd: info.root, role: 'reviewer', tasks: [], path: 'src/__polier_probe__' })], { cwd: info.root, timeoutMs: 20_000, signal: exec.signal, preferShell: false }).catch(() => undefined) : undefined
        const answer = probe ? lastJson(probe.stdout) : undefined
        checks.push(answer && answer.deny
          ? { check: 'write guard', level: 'ok', detail: `enforce ${config.enforce}; a probe write outside reviews/ was refused` }
          : { check: 'write guard', level: 'fail', detail: 'tools/guard.py did not refuse a probe write', fix: 'check the python option; writes are blocked while the guard cannot answer' })
      }
      const state = stateOf(exec.agent)
      checks.push({ check: 'session', level: 'ok', detail: `mode ${state.role}${state.specialist ? `, role ${state.specialist.id}` : ''}${state.pinned ? `, bound to ${state.pinned}` : ''}` })
      const level = checks.some((c) => c.level === 'fail') ? 'fail' : checks.some((c) => c.level === 'warn') ? 'warn' : 'ok'
      const problems = checks.filter((c) => c.level !== 'ok')
      return { ok: level !== 'fail', result: level, project: result?.project ?? null, checks,
        next: problems.length ? `Fix first: ${problems[0].check}: ${problems[0].fix ?? problems[0].detail}` : 'Everything is in place.' }
    },
  })

  const status = jsonTool({
    name: 'pl_status',
    description: 'The full Polier state as JSON: the factory line, the running task with scope and brief, ready tasks with handoffs, live claims, policy limits, pending approvals and open questions. The <polier> context already shows the summary; call this only when you need the details.',
    parameters: { type: 'object', properties: { project: PROJECT } },
    isConcurrencySafe: () => true,
    async execute(args, exec) {
      const root = projectRoot(ctx, exec.agent, args.project)
      const state = stateOf(exec.agent)
      const value = { root, role: state.role, enforce: config.enforce }
      const factory = await run(ctx, exec.agent, py(config, 'factory.py', '--root', root, 'status', '--json'), { cwd: root, timeoutMs: 60_000, signal: exec.signal })
      if (factory.code === 0) value.factory = lastJson(factory.stdout)
      const board = loadBoard(root)
      if (!board) return value
      const active = activeTasks(board, { root, cwd: agentCwd(ctx, exec.agent), pinned: state.pinned })
      const policy = loadPolicy(root)
      return {
        ...value,
        project: board.project,
        profile: board.profile,
        running: active.tasks.map((t) => ({
          id: t.id, title: t.title, brief: `tasks/${t.id}.md`, scope_write: t.scope_write ?? [],
          scope_write_forbidden: t.scope_write_forbidden ?? [], gates: t.gates ?? [], round: t.round ?? 0,
        })),
        selected_by: active.how,
        claims: await liveClaims(ctx, config, exec.agent, root),
        ready: readyTasks(board),
        policy: policyEnabled(policy)
          ? { limits: limits(policy), approver: approver(policy), protected_paths: policy.scope?.protected_paths ?? [], pending_approvals: pendingApprovals(root) }
          : { enabled: false },
        open_questions: (board.open_questions ?? []).filter((q) => q?.status === 'open'),
      }
    },
  })

  const gate = jsonTool({
    name: 'pl_gate',
    description: 'Run one quality gate of a task through tools/gate.py. The full output goes to reviews/evidence/; the result shows pass/fail, the failing lines and the record path. The record path is the only accepted proof that a gate passed.',
    parameters: {
      type: 'object',
      properties: {
        task: { type: 'string', description: 'Task ID, e.g. M03.' },
        gate: { type: 'string', description: "Gate name exactly as in the task's gates list, e.g. tests." },
        command: { type: 'string', description: 'Shell command of the gate, from AGENTS.md or the brief.' },
        timeout_s: { type: 'integer', description: 'Seconds before the gate is stopped. Default 600.' },
        lock_wait_s: { type: 'integer', description: 'Seconds to wait for an exclusive resource; default 0 (report busy at once).' },
        project: PROJECT,
      },
      required: ['task', 'gate', 'command'],
    },
    async execute(args, exec) {
      const { root, board } = needBoard(ctx, exec.agent, args.project)
      const task = board.tasks.find((t) => t?.id === args.task)
      if (!task) throw new Error(`task ${args.task} is not on the board`)
      if (Array.isArray(task.gates) && task.gates.length && !task.gates.includes(args.gate)) {
        throw new Error(`gate ${args.gate} is not listed for ${args.task}; listed: ${task.gates.join(', ')}`)
      }
      const timeout = Number.isInteger(args.timeout_s) && args.timeout_s > 0 ? args.timeout_s : 600
      const lockWait = Number.isInteger(args.lock_wait_s) && args.lock_wait_s >= 0 ? args.lock_wait_s : 0
      const argv = py(config, 'gate.py', '--task', args.task, '--name', args.gate, '--root', root,
        '--timeout', String(timeout), '--lock-wait', String(lockWait))
      const slot = polierSlot(root)
      if (slot !== undefined) argv.push('--slot', String(slot))
      for (const resource of task.exclusive ?? []) if (typeof resource === 'string' && resource) argv.push('--exclusive', resource)
      argv.push('--shell', args.command)
      const result = await run(ctx, exec.agent, argv, { cwd: root, timeoutMs: (timeout + 30) * 1000, signal: exec.signal, strictShell: true })
      const lines = result.stdout.trim().split('\n')
      const last = lines[lines.length - 1] ?? ''
      const record = last.startsWith('record: ') ? last.slice(8).trim() : null
      const busy = result.code === 75
      const summary = (record ? lines.slice(0, -1) : lines).join('\n').slice(-4000)
      const passed = result.code === 0 && record !== null
      return {
        task: args.task,
        gate: args.gate,
        passed,
        next: busy
          ? 'The gate did not run: wait for the resource or rerun alone; a BUSY record is not evidence.'
          : passed
            ? `Put ${record} into your result as evidence for ${args.gate}.`
            : 'Find the cause in the failing lines and fix it; this is the same attempt. Never change a test to make it pass.',
        busy,
        exit_code: result.code,
        record,
        summary: busy ? `resource busy, rerun alone (the gate did not run).\n${summary}` : summary,
        ...(result.stderr.trim() ? { stderr: result.stderr.trim().slice(-2000) } : {}),
      }
    },
  })

  const scope = jsonTool({
    name: 'pl_scope_check',
    description: 'Compare every changed file (git status) with the write scope of a task. Run it before you report a task as finished.',
    parameters: { type: 'object', properties: { task: { type: 'string', description: 'Task ID. Default: the bound or running task.' }, project: PROJECT } },
    isConcurrencySafe: () => true,
    async execute(args, exec) {
      const { root } = needBoard(ctx, exec.agent, args.project)
      const state = stateOf(exec.agent)
      const result = await scopeCheck(ctx, config, exec.agent, { root, state }, args.task || state.pinned, exec.signal)
      if (result && Array.isArray(result.foreign) && result.foreign.length > 0) {
        result.foreign_changes = result.foreign.map((item) => `foreign changes (task ${item.task}, harness ${item.harness}): ${item.path}`)
      }
      return result
    },
  })

  const review = jsonTool({
    name: 'pl_review',
    description: 'The review packet of one task: brief, acceptance IDs, earlier review verdicts, the latest gate record per gate (green or not), the changed files inside the scope and their diff. Hand it to the reviewer instead of collecting files by hand.',
    parameters: { type: 'object', properties: { task: { type: 'string', description: 'Task ID. Default: the bound or running task.' }, project: PROJECT } },
    isConcurrencySafe: () => true,
    async execute(args, exec) {
      const { root } = needBoard(ctx, exec.agent, args.project)
      const argv = py(config, 'review.py', root)
      const task = args.task || stateOf(exec.agent).pinned
      if (task) argv.push('--task', String(task))
      const result = await run(ctx, exec.agent, argv, { cwd: root, timeoutMs: 60_000, signal: exec.signal })
      const value = lastJson(result.stdout)
      if (value === undefined) return { ok: false, exit_code: result.code, error: (result.stderr || result.stdout).trim().slice(-2000) }
      return { ok: value.ok !== false, ...value }
    },
  })

  const check = jsonTool({
    name: 'pl_check',
    description: 'Regenerate STATUS.md and docs/factory.md, then run tools/check.py on the project: mandatory files, word budgets, board consistency, traceability, gate evidence and the factory line. ok: true means no errors.',
    parameters: { type: 'object', properties: { project: PROJECT } },
    isConcurrencySafe: () => true,
    async execute(args, exec) {
      const { root } = needBoard(ctx, exec.agent, args.project)
      await render(ctx, config, exec.agent, root, exec.signal)
      const result = await run(ctx, exec.agent, py(config, 'check.py', root), { cwd: root, timeoutMs: 120_000, signal: exec.signal })
      return { ok: result.code === 0, exit_code: result.code, output: outputOf(result) }
    },
  })

  const next = jsonTool({
    name: 'pl_next',
    description: 'The dispatch plan: running tasks with attempts, the next wave that can run in parallel, blocked tasks with what unblocks them, scope conflicts and pending approvals. Read it before starting a task.',
    parameters: { type: 'object', properties: { limit: { type: 'integer', description: 'Maximum tasks per wave.' }, project: PROJECT } },
    isConcurrencySafe: () => true,
    async execute(args, exec) {
      const { root } = needBoard(ctx, exec.agent, args.project)
      const argv = py(config, 'dispatch.py', '--json', '--root', root)
      if (Number.isInteger(args.limit) && args.limit > 0) argv.push('--limit', String(args.limit))
      const result = await run(ctx, exec.agent, argv, { cwd: root, timeoutMs: 60_000, signal: exec.signal })
      const plan = lastJson(result.stdout)
      if (plan === undefined) return { ok: false, exit_code: result.code, error: (result.stderr || result.stdout).trim().slice(-4000) || `exit ${result.code}` }
      return { root, ...plan }
    },
  })

  const state = jsonTool({
    name: 'pl_state',
    description: 'Read the execution state of the board or of one task, or (lead session) move a task through one checkpoint: pending, in_progress, verifying, review, done, rework, blocked, failed. A refusal names what is missing. STATUS.md is regenerated after every change.',
    parameters: {
      type: 'object',
      properties: {
        task: { type: 'string', description: 'Task ID, e.g. M03. Without it and without status: the whole board.' },
        status: { type: 'string', description: 'New status. Omit to read.' },
        note: { type: 'string', description: 'Reason; required for rework, blocked and failed.' },
        force: { type: 'boolean', description: 'Override a checkpoint; needs a granted state_override approval.' },
        handoff: { type: 'array', items: { type: 'string' }, description: 'With status done: 1–3 lines the dependent tasks need (what exists now, where, how to use it).' },
        project: PROJECT,
      },
    },
    async execute(args, exec) {
      const { root } = needBoard(ctx, exec.agent, args.project)
      const taskId = typeof args.task === 'string' && args.task.trim() ? args.task.trim().toUpperCase() : undefined
      const newStatus = typeof args.status === 'string' ? args.status.trim() : ''
      if (newStatus) {
        if (stateOf(exec.agent).role !== 'lead') {
          throw new Error('Polier: only a lead session changes task state. Report the checkpoint to the lead, or switch with pl_mode lead (the owner approves it).')
        }
        if (!taskId) throw new Error('pl_state needs the task ID to set a status')
        const argv = py(config, 'state.py', 'set', taskId, newStatus, '--actor', 'lead', '--root', root)
        if (typeof args.note === 'string' && args.note.trim()) argv.push('--note', args.note.trim())
        if (args.force === true) argv.push('--force')
        for (const line of Array.isArray(args.handoff) ? args.handoff : []) {
          if (typeof line === 'string' && line.trim()) argv.push('--handoff', line.trim())
        }
        const result = await run(ctx, exec.agent, argv, { cwd: root, timeoutMs: 120_000, signal: exec.signal })
        if (result.code === 0) await render(ctx, config, exec.agent, root, exec.signal)
        return { ok: result.code === 0, task: taskId, status: newStatus, exit_code: result.code, output: outputOf(result) }
      }
      const argv = py(config, 'state.py', 'show')
      if (taskId) argv.push(taskId)
      argv.push('--json', '--root', root)
      const result = await run(ctx, exec.agent, argv, { cwd: root, timeoutMs: 60_000, signal: exec.signal })
      const value = lastJson(result.stdout)
      return value === undefined ? { ok: false, exit_code: result.code, error: (result.stderr || result.stdout).trim().slice(-4000) || `exit ${result.code}` } : value
    },
  })

  const factory = jsonTool({
    name: 'pl_factory',
    description: 'The factory line (factory.json). init shows the owner the planned line (platforms, traits, items per station) in an approval prompt and writes it only on yes. Read: status, next (open items of the current station with the evidence they need). Write (lead, or any session while no task runs): done (with evidence paths, optionally #heading), na or defer (with a reason), reopen, link (board tasks that deliver an item). advance asks the owner and closes the current station. Every write returns what is left and the next step; docs/factory.md is regenerated.',
    parameters: {
      type: 'object',
      properties: {
        action: { type: 'string', enum: ['init', 'status', 'next', 'done', 'na', 'defer', 'reopen', 'link', 'advance'], description: 'Default: next.' },
        platforms: { type: 'array', items: { type: 'string' }, description: 'For init: web, ios, android, desktop, cli, service.' },
        traits: { type: 'array', items: { type: 'string' }, description: 'For init: accounts, payments, personal_data, uploads, realtime, notifications, offline, i18n, ai, analytics, location, public, eu_users, cross_platform, brownfield.' },
        item: { type: 'string', description: 'Checklist item ID, e.g. BLD-30.' },
        evidence: { type: 'array', items: { type: 'string' }, description: 'Project paths for done, e.g. docs/concept.md#user-stories.' },
        reason: { type: 'string', description: 'Reason for na or defer; a note for advance.' },
        tasks: { type: 'array', items: { type: 'string' }, description: 'Board task IDs for link.' },
        batch: {
          type: 'array',
          description: 'Several items with the same action in one call (done, na, defer, link): each entry has item and its own evidence, reason or tasks.',
          items: { type: 'object', properties: { item: { type: 'string' }, evidence: { type: 'array', items: { type: 'string' } }, reason: { type: 'string' }, tasks: { type: 'array', items: { type: 'string' } } }, required: ['item'] },
        },
        project: PROJECT,
      },
    },
    async execute(args, exec) {
      const action = typeof args.action === 'string' && args.action ? args.action : 'next'
      if (action === 'init') return initLine(args, exec)
      const root = projectRoot(ctx, exec.agent, args.project)
      const base = py(config, 'factory.py', '--root', root)
      if (action === 'status' || action === 'next') {
        const result = await run(ctx, exec.agent, [...base, action, '--json'], { cwd: root, timeoutMs: 60_000, signal: exec.signal })
        const value = lastJson(result.stdout)
        if (value === undefined) return { ok: false, exit_code: result.code, error: (result.stderr || result.stdout).trim().slice(-4000) || `exit ${result.code}` }
        return { root, ...value }
      }
      if (!mayPlan(exec.agent, root)) {
        throw new Error('Polier: tasks are running, so only a lead session changes factory.json. Switch with pl_mode lead (the owner approves it).')
      }
      if (action === 'advance') {
        const view = await run(ctx, exec.agent, [...base, 'next', '--json'], { cwd: root, timeoutMs: 60_000, signal: exec.signal })
        const station = lastJson(view.stdout)?.station
        if (!station) return { ok: false, error: 'every station is already closed' }
        const status = lastJson((await run(ctx, exec.agent, [...base, 'status', '--json'], { cwd: root, timeoutMs: 60_000, signal: exec.signal })).stdout)
        const row = (status?.stations ?? []).find((s) => s.id === station)
        const counts = row ? ` ${row.done} done, ${row.na} n/a, ${row.deferred} deferred, ${row.open} open.` : ''
        const answer = await askOwner(ctx, exec, `Close the Polier station "${station}" and open the next one?${counts} Details: docs/factory.md.`)
        if (!answer.ok) return { ok: false, station, approval: answer.outcome, ...(answer.note ? { note: answer.note } : {}) }
        const argv = [...base, 'advance', '--by', `${config.owner} (approved in DSH)`]
        if (typeof args.reason === 'string' && args.reason.trim()) argv.push('--note', args.reason.trim())
        const result = await run(ctx, exec.agent, argv, { cwd: root, timeoutMs: 60_000, signal: exec.signal })
        if (result.code === 0) await render(ctx, config, exec.agent, root, exec.signal)
        const closed = { ok: result.code === 0, station, approval: answer.outcome, output: outputOf(result) }
        if (result.code === 0 && station === 'plan') closed.next = 'Commit the plan files (one commit, e.g. "chore: plan"), then start the first task from pl_next.'
        return closed
      }
      const entries = Array.isArray(args.batch) && args.batch.length ? args.batch : [args]
      const by = stateOf(exec.agent).role === 'lead' ? 'lead' : 'planner'
      const results = []
      for (const entry of entries) {
        const item = typeof entry?.item === 'string' ? entry.item.trim().toUpperCase() : ''
        if (!item) throw new Error(`pl_factory ${action} needs the item ID`)
        const argv = [...base, action, item]
        if (action === 'done') for (const value of entry.evidence ?? []) argv.push('--evidence', String(value))
        if (action === 'na' || action === 'defer') argv.push('--reason', String(entry.reason ?? ''))
        if (action === 'link') argv.push('--task', (entry.tasks ?? []).map(String).join(','))
        argv.push('--by', by)
        const result = await run(ctx, exec.agent, argv, { cwd: root, timeoutMs: 60_000, signal: exec.signal })
        results.push(result.code === 0
          ? { ok: true, item, output: outputOf(result) }
          : { ok: false, item, exit_code: result.code, output: outputOf(result) })
      }
      if (results.some((r) => r.ok)) await render(ctx, config, exec.agent, root, exec.signal)
      const left = await whatIsLeft(base, root, exec)
      if (results.length === 1) return { ...results[0], action, ...(results[0].ok ? left : {}) }
      return { ok: results.every((r) => r.ok), action, results, ...left }
    },
  })

  /** After a write: the station, its remaining open items and the next step. */
  async function whatIsLeft(base, root, exec) {
    const view = lastJson((await run(ctx, exec.agent, [...base, 'next', '--json'], { cwd: root, timeoutMs: 60_000, signal: exec.signal })).stdout)
    if (!view?.station) return { next: 'Every station is closed.' }
    const remaining = (view.items ?? []).map((item) => item.id)
    return {
      station: view.station,
      remaining,
      next: remaining.length
        ? `${remaining.length} open item(s) in station ${view.station}; next: ${remaining[0]}.`
        : `Station ${view.station} has no open item: ask the owner to close it with pl_factory advance.`,
    }
  }

  /** Start the line: show the plan, ask the owner, write only on yes. */
  async function initLine(args, exec) {
    const base = agentCwd(ctx, exec.agent)
    const root = args.project ? path.resolve(base, args.project) : base
    const platforms = (args.platforms ?? []).map(String).join(',')
    if (!platforms) throw new Error('pl_factory init needs platforms, e.g. ["web"] or ["ios", "android"]')
    const traits = (args.traits ?? []).map(String).join(',')
    const argv = py(config, 'factory.py', '--root', root, 'init', '--platforms', platforms, ...(traits ? ['--traits', traits] : []))
    const preview = await run(ctx, exec.agent, [...argv, '--dry-run', '--json'], { cwd: root, timeoutMs: 60_000, signal: exec.signal })
    const planned = lastJson(preview.stdout)
    if (preview.code !== 0 || !planned) return { ok: false, error: outputOf(preview) || `exit ${preview.code}` }
    if (planned.exists) return { ok: false, error: `factory.json already exists in ${root}; change the scope instead of starting again` }
    const perStation = Object.entries(planned.stations).filter(([, n]) => n > 0).map(([id, n]) => `${id} ${n}`).join(', ')
    const answer = await askOwner(ctx, exec, `Start the Polier line in ${root}: ${planned.items} checklist items for ${planned.platforms.join(', ')} (traits ${planned.traits.join(', ') || 'none'}; ${perStation})?`)
    if (!answer.ok) return { ok: false, planned, approval: answer.outcome, ...(answer.note ? { note: answer.note } : {}) }
    const result = await run(ctx, exec.agent, [...argv, '--by', `${config.owner} (approved in DSH)`], { cwd: root, timeoutMs: 60_000, signal: exec.signal })
    if (result.code !== 0) return { ok: false, planned, output: outputOf(result) }
    await render(ctx, config, exec.agent, root, exec.signal)
    return { ok: true, planned, ...(await whatIsLeft(py(config, 'factory.py', '--root', root), root, exec)) }
  }

  const mode = jsonTool({
    name: 'pl_mode',
    description: 'Switch the role of this session. worker (default: writes only inside the running task\'s scope) and reviewer (writes only under reviews/) switch at once. lead (plans, merges, records state) and off (no guard) open an approval prompt for the owner first.',
    parameters: {
      type: 'object',
      properties: {
        role: { type: 'string', enum: ROLES },
        reason: { type: 'string', description: 'Why the session needs this role; shown to the owner.' },
      },
      required: ['role'],
    },
    async execute(args, exec) {
      const role = String(args.role ?? '')
      if (!ROLES.includes(role)) throw new Error(`role must be one of ${ROLES.join(', ')}`)
      const state = stateOf(exec.agent)
      if (role === state.role) return { ok: true, role, changed: false }
      if (role === 'lead' || role === 'off') {
        const why = typeof args.reason === 'string' && args.reason.trim() ? ` Reason: ${args.reason.trim()}` : ''
        const answer = await askOwner(ctx, exec, `Let this session work as Polier ${role}${role === 'off' ? ' (no write guard)' : ' (outside task scopes)'}?${why}`)
        if (!answer.ok) return { ok: false, role: state.role, approval: answer.outcome, ...(answer.note ? { note: answer.note } : {}) }
      }
      state.role = role
      return { ok: true, role, changed: true }
    },
  })

  /** Load a role through tools/roles.py and make it this session's: mode, instructions, write list. */
  async function takeRole(exec, root, id) {
    const result = await run(ctx, exec.agent, py(config, 'roles.py', '--root', root, 'show', id, '--json'), { cwd: root, timeoutMs: 30_000, signal: exec.signal })
    const role = lastJson(result.stdout)
    if (result.code !== 0 || !role) throw new Error((result.stderr || result.stdout).trim() || `unknown role ${id}`)
    const state = stateOf(exec.agent)
    state.specialist = role
    state.role = role.mode
    return role
  }

  const roleTool = jsonTool({
    name: 'pl_role',
    description: 'Take a specialist role for this session (analyst, designer, architect, frontend-builder, backend-builder, mobile-builder, reviewer, security-reviewer, release-manager, or one the project adds in docs/roles/). The role adds its instructions to the system prompt, sets the session to worker or reviewer mode and may narrow where it writes; it never widens anything. Without role: drop it.',
    parameters: { type: 'object', properties: { role: { type: 'string', description: 'Role id. Omit to drop the role.' }, project: PROJECT } },
    async execute(args, exec) {
      const id = typeof args.role === 'string' ? args.role.trim().toLowerCase() : ''
      const state = stateOf(exec.agent)
      if (!id) {
        state.specialist = undefined
        return { ok: true, role: null, mode: state.role }
      }
      const role = await takeRole(exec, projectRoot(ctx, exec.agent, args.project), id)
      return {
        ok: true, role: role.id, title: role.title, mode: role.mode, model: role.model, reads: role.reads ?? [], gates: role.gates ?? [],
        next: role.mode === 'reviewer' ? 'Read the brief, the diff and the gate records; write reviews/<ID>.md.' : 'Bind your task with pl_task, then read the files the role names.',
      }
    },
  })

  const bind = jsonTool({
    name: 'pl_task',
    description: 'Bind this session to one task and take its claim, so the guard uses that task\'s scope and no other session works on it. A task with a role gives the session that role. Without task: release the binding and the claims of this session.',
    parameters: { type: 'object', properties: { task: { type: 'string', description: 'Task ID, e.g. M03. Omit to release.' }, project: PROJECT } },
    async execute(args, exec) {
      const { root, board } = needBoard(ctx, exec.agent, args.project)
      const state = stateOf(exec.agent)
      const id = typeof args.task === 'string' && args.task.trim() ? args.task.trim().toUpperCase() : ''
      if (!id) {
        const released = []
        for (const task of [...state.claims]) if (await releaseClaim(ctx, config, exec.agent, root, task)) released.push(task)
        state.claims = []
        state.pinned = undefined
        return { ok: true, bound: null, released }
      }
      const entry = board.tasks.find((t) => t?.id === id)
      if (!entry) throw new Error(`task ${id} is not on the board`)
      // A reviewer keeps reviewing: the task's role and its claim are for the session that builds it.
      const builds = state.role !== 'reviewer'
      if (!builds) {
        state.pinned = id
        return { ok: true, bound: id, claimed: false, role: null,
          next: `Review ${id}: read tasks/${id}.md, the diff and the gate records in reviews/evidence/, then write reviews/${id}.md.` }
      }
      const held = state.claims.includes(id)
      const taken = await takeClaim(ctx, config, exec.agent, root, id)
      if (!taken.ok && taken.code !== 2) return { ok: false, bound: state.pinned ?? null, error: `cannot claim ${id}: ${taken.message}` }
      state.pinned = id
      if (taken.ok) state.claims = [...new Set([...state.claims, id])]
      // What was already changed before this session took the task is not the builder's doing.
      if (taken.ok && !held) {
        await run(ctx, exec.agent, py(config, 'scope_check.py', root, '--task', id, '--snapshot'), { cwd: root, timeoutMs: 60_000, signal: exec.signal })
      }
      const role = typeof entry.role === 'string' && entry.role ? await takeRole(exec, root, entry.role) : undefined
      return {
        ok: true, bound: id, claimed: taken.ok, role: role?.id ?? null,
        ...(taken.ok ? {} : { note: `no claim taken: ${taken.message}` }),
        next: `Read tasks/${id}.md, build inside ${(entry.scope_write ?? []).join(', ') || 'the scope'}, prove it with pl_gate (${(entry.gates ?? []).join(', ') || 'the listed gates'}).`,
      }
    },
  })

  const approval = jsonTool({
    name: 'pl_approval',
    description: 'Ask the owner for a Polier approval (new_dependency, scope_change, merge_to_base, release, reopen_done, protected_path, state_override). Writes the request to reviews/approvals/, opens an approval prompt and records the owner\'s answer as granted or denied. Never act before it is granted.',
    parameters: {
      type: 'object',
      properties: {
        action: { type: 'string', enum: ACTIONS },
        task: { type: 'string', description: 'Task the approval is for; omit for project-wide.' },
        note: { type: 'string', description: 'What exactly and why; shown to the owner.' },
        project: PROJECT,
      },
      required: ['action', 'note'],
    },
    async execute(args, exec) {
      const { root } = needBoard(ctx, exec.agent, args.project)
      const action = String(args.action ?? '')
      const task = typeof args.task === 'string' && args.task.trim() ? args.task.trim().toUpperCase() : undefined
      const note = String(args.note ?? '').trim()
      const argv = py(config, 'approve.py', 'request', '--action', action, '--by', stateOf(exec.agent).role, '--root', root)
      if (task) argv.push('--task', task)
      if (note) argv.push('--note', note)
      const requested = await run(ctx, exec.agent, argv, { cwd: root, timeoutMs: 60_000, signal: exec.signal })
      const id = /AP-\d{3,}/.exec(requested.stdout)?.[0]
      if (requested.code !== 0 || !id) return { ok: false, error: outputOf(requested) || `exit ${requested.code}` }
      const answer = await askOwner(ctx, exec, `Polier approval ${id}: ${action}${task ? ` for ${task}` : ''}. ${note}`)
      if (answer.outcome === 'unavailable' || answer.outcome === 'cancelled') {
        return { ok: false, id, status: 'pending', approval: answer.outcome, ...(answer.note ? { note: answer.note } : {}) }
      }
      const verdict = answer.ok ? 'grant' : 'deny'
      const result = await run(ctx, exec.agent,
        py(config, 'approve.py', verdict, id, '--by', config.owner, '--note', 'answered in the DSH approval prompt', '--root', root),
        { cwd: root, timeoutMs: 60_000, signal: exec.signal })
      return { ok: answer.ok && result.code === 0, id, status: answer.ok ? 'granted' : 'denied', output: outputOf(result) }
    },
  })

  return [preflight, status, gate, scope, review, check, next, state, factory, mode, roleTool, bind, approval]
}
