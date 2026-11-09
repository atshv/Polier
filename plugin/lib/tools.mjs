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
import { liveClaims, polierSlot, releaseClaim, ROLES, stateOf, takeClaim } from './session.mjs'

const ANY = {}
const PROJECT = { type: 'string', description: 'Project folder. Default: the session directory or the nearest parent with board.json or factory.json.' }

function jsonTool(def) {
  return { ...def, output: { schema: ANY, render: (_args, value) => [{ type: 'text', text: JSON.stringify(value, null, 2) }] } }
}

function projectRoot(ctx, agent, project) {
  const base = agentCwd(ctx, agent)
  const root = findProject(project ? path.resolve(base, project) : base)
  if (!root) throw new Error('no board.json or factory.json in this folder or above; is this a Polier project?')
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

  const check = jsonTool({
    name: 'pl_check',
    description: 'Run tools/check.py on the project: mandatory files, word budgets, board consistency, traceability, gate evidence and the factory line. ok: true means no errors.',
    parameters: { type: 'object', properties: { project: PROJECT } },
    isConcurrencySafe: () => true,
    async execute(args, exec) {
      const { root } = needBoard(ctx, exec.agent, args.project)
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
        const answer = await askOwner(ctx, exec, `Close the Polier station "${station}" and open the next one?`)
        if (!answer.ok) return { ok: false, station, approval: answer.outcome, ...(answer.note ? { note: answer.note } : {}) }
        const argv = [...base, 'advance', '--by', `${config.owner} (approved in DSH)`]
        if (typeof args.reason === 'string' && args.reason.trim()) argv.push('--note', args.reason.trim())
        const result = await run(ctx, exec.agent, argv, { cwd: root, timeoutMs: 60_000, signal: exec.signal })
        if (result.code === 0) await render(ctx, config, exec.agent, root, exec.signal)
        return { ok: result.code === 0, station, approval: answer.outcome, output: outputOf(result) }
      }
      const item = typeof args.item === 'string' ? args.item.trim().toUpperCase() : ''
      if (!item) throw new Error(`pl_factory ${action} needs the item ID`)
      const argv = [...base, action, item]
      if (action === 'done') for (const value of args.evidence ?? []) argv.push('--evidence', String(value))
      if (action === 'na' || action === 'defer') argv.push('--reason', String(args.reason ?? ''))
      if (action === 'link') argv.push('--task', (args.tasks ?? []).map(String).join(','))
      argv.push('--by', stateOf(exec.agent).role === 'lead' ? 'lead' : 'planner')
      const result = await run(ctx, exec.agent, argv, { cwd: root, timeoutMs: 60_000, signal: exec.signal })
      if (result.code !== 0) return { ok: false, action, item, exit_code: result.code, output: outputOf(result) }
      await render(ctx, config, exec.agent, root, exec.signal)
      return { ok: true, action, item, output: outputOf(result), ...(await whatIsLeft(base, root, exec)) }
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

  const bind = jsonTool({
    name: 'pl_task',
    description: 'Bind this session to one task and take its claim, so the guard uses that task\'s scope and no other session works on it. Without task: release the binding and the claims of this session.',
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
      if (!board.tasks.some((t) => t?.id === id)) throw new Error(`task ${id} is not on the board`)
      const taken = await takeClaim(ctx, config, exec.agent, root, id)
      if (!taken.ok && taken.code !== 2) return { ok: false, bound: state.pinned ?? null, error: `cannot claim ${id}: ${taken.message}` }
      state.pinned = id
      if (taken.ok) state.claims = [...new Set([...state.claims, id])]
      return { ok: true, bound: id, claimed: taken.ok, ...(taken.ok ? {} : { note: `no claim taken: ${taken.message}` }) }
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

  return [status, gate, scope, check, next, state, factory, mode, bind, approval]
}
