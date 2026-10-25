// DeepSeek Harness plugin for Polier.
//
// What it adds to every session:
// - a write guard: a worker session may only write inside the scope of its
//   running task (board.json → scope_write / scope_write_forbidden);
// - a stop check: before a turn ends, the git diff is compared with the scope
//   (catches writes through bash), and the agent is told to fix violations;
// - tools: pl_status, pl_gate, pl_scope_check, pl_check;
// - the human command /pl (lead, worker, off, task, status, render);
// - the Polier skill, with its files resolved inside this package.
//
// No build step and no static imports of harness packages: every service is
// looked up at call time, so a missing optional service degrades instead of
// breaking the harness boot.

import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { activeTasks, checkPath, findRoot, loadBoard, processKills, readyTasks, relative } from './lib/project.mjs'
import { agentCwd, run } from './lib/run.mjs'

export const name = 'polier'

const PACKAGE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..')
const TOOLS = path.join(PACKAGE, 'tools')
const SOURCE = 'polier'

const DEFAULTS = {
  /** deny: block out-of-scope writes · ask: ask the human · off: no guard */
  enforce: 'deny',
  /** File-writing tools to guard, with the argument that holds the path. */
  guardedTools: { write: 'file_path', edit: 'file_path', str_replace_editor: 'path' },
  /** Compare the git diff with the scope before a turn ends. */
  stopCheck: true,
  /** Reminders per turn before the stop check gives up and lets the turn end. */
  maxStopReminders: 2,
  /** Python interpreter for the package tools. */
  python: process.platform === 'win32' ? 'python' : 'python3',
  /** Register the bundled Polier skill. */
  skill: true,
}

/** Merge the row's config with defaults; unknown keys are ignored. */
export function resolveConfig(config = {}) {
  const out = { ...DEFAULTS }
  if (['deny', 'ask', 'off'].includes(config.enforce)) out.enforce = config.enforce
  if (config.guardedTools && typeof config.guardedTools === 'object') out.guardedTools = { ...config.guardedTools }
  if (typeof config.stopCheck === 'boolean') out.stopCheck = config.stopCheck
  if (Number.isInteger(config.maxStopReminders) && config.maxStopReminders >= 0) out.maxStopReminders = config.maxStopReminders
  if (typeof config.python === 'string' && config.python) out.python = config.python
  if (typeof config.skill === 'boolean') out.skill = config.skill
  return out
}

// ---------------------------------------------------------------------------
// per-session state: role, pinned task and the claims of this session. In
// memory only; a restarted harness starts every session as a worker again
// (the safe side).
// ---------------------------------------------------------------------------

const sessions = new Map()

function stateOf(agent) {
  const id = agent?.id
  if (!id) return { role: 'worker', pinned: undefined, claims: [], stop: { turn: -1, count: 0 } }
  let state = sessions.get(id)
  if (!state) {
    state = {
      role: 'worker', pinned: undefined, claims: [], lastBeat: 0,
      stop: { turn: -1, count: 0 }, turn: 0, killTurn: -1,
    }
    sessions.set(id, state)
  }
  if (!Array.isArray(state.claims)) state.claims = []
  return state
}

/** Project root, board and the tasks that bind this session; undefined when no task is running. */
function context(ctx, agent) {
  const cwd = agentCwd(ctx, agent)
  const root = findRoot(cwd)
  if (!root) return undefined
  const board = loadBoard(root)
  if (!board) return undefined
  const state = stateOf(agent)
  const active = activeTasks(board, { root, cwd, pinned: state.pinned })
  return { cwd, root, board, state, ...active }
}

// ---------------------------------------------------------------------------
// claims (PL-04): one JSON file per task in <git-common-dir>/polier/claims/,
// shared by every harness. The Python core owns the format; the plugin calls
// tools/claim.py so there is one implementation.
// ---------------------------------------------------------------------------

const CLAIM_TOOL = path.join(TOOLS, 'claim.py')
const HEARTBEAT_MS = 60_000

function polierSlot(folder) {
  try {
    const data = JSON.parse(readFileSync(path.join(String(folder), '.polier-slot'), 'utf8'))
    const value = data && typeof data === 'object' ? data.slot ?? data.N : undefined
    return Number.isInteger(value) && value >= 0 ? value : undefined
  } catch {
    return undefined
  }
}

function claimArgv(config, ...args) {
  return [config.python, CLAIM_TOOL, ...args]
}

function claimError(result) {
  const text = (result.stderr || result.stdout || `exit ${result.code}`).trim()
  return text.split('\n').filter(Boolean).pop() || `exit ${result.code}`
}

async function takeClaim(ctx, config, agent, root, id) {
  const argv = claimArgv(config, 'take', id, '--harness', 'dsh', '--session', String(agent.id), '--root', String(root))
  const task = (loadBoard(root)?.tasks ?? []).find((t) => t?.id === id)
  if (task && typeof task.worktree === 'string' && task.worktree.trim()) {
    argv.push('--worktree', path.resolve(root, task.worktree))
  }
  const slot = polierSlot(agentCwd(ctx, agent) || root)
  if (slot !== undefined) argv.push('--slot', String(slot))
  const result = await run(ctx, agent, argv, { cwd: String(root), timeoutMs: 30_000 })
  return { ok: result.code === 0, code: result.code, message: claimError(result), claim: result.stdout.trim() }
}

async function releaseClaim(ctx, config, agent, root, id) {
  try {
    const result = await run(ctx, agent,
      claimArgv(config, 'release', id, '--session', String(agent.id), '--root', String(root)),
      { cwd: String(root), timeoutMs: 20_000 })
    return result.code === 0
  } catch {
    return false
  }
}

async function beatClaims(ctx, config, agent, root) {
  const tasks = stateOf(agent).claims
  for (const id of tasks) {
    try {
      await run(ctx, agent,
        claimArgv(config, 'beat', id, '--session', String(agent.id), '--root', String(root)),
        { cwd: String(root), timeoutMs: 20_000 })
    } catch { /* best effort */ }
  }
}

async function liveClaims(ctx, config, agent, root) {
  try {
    const result = await run(ctx, agent,
      claimArgv(config, 'list', '--root', String(root), '--json'),
      { cwd: String(root), timeoutMs: 20_000 })
    const rows = JSON.parse(result.stdout.trim() || '[]')
    return Array.isArray(rows) ? rows : []
  } catch {
    return []
  }
}

function message(text) {
  return {
    id: `pl-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    role: 'user',
    content: [{ type: 'text', text }],
    source: { kind: 'plugin', plugin: SOURCE },
  }
}

// ---------------------------------------------------------------------------
// write guard
// ---------------------------------------------------------------------------

/** Target path of a guarded tool call, or undefined when the call does not write. */
function targetOf(exec, guarded) {
  const key = guarded[exec.name]
  if (!key) return undefined
  const args = exec.arguments && typeof exec.arguments === 'object' ? exec.arguments : {}
  if (exec.name === 'str_replace_editor' && args.command === 'view') return undefined
  const value = args[key]
  return typeof value === 'string' && value ? value : undefined
}

/**
 * The guard decision for one tool call.
 * @returns {string|undefined} a denial reason, or undefined to allow
 */
export function checkWrite(ctx, config, exec) {
  if (config.enforce === 'off') return undefined
  // Calls without an agent come from the harness itself, not from a model.
  if (!exec.agent) return undefined
  const target = targetOf(exec, config.guardedTools)
  if (!target) return undefined
  const info = context(ctx, exec.agent)
  if (!info) return undefined
  const abs = path.resolve(info.cwd, target)
  const rel = relative(info.root, abs)
  const verdict = checkPath(rel, info.tasks, info.state.role,
    { board: info.board, root: info.root, cwd: info.cwd })
  if (verdict.ok) return undefined
  if (info.state.role === 'reviewer') {
    return `Polier: write to ${rel || target} blocked, a reviewer session writes only under reviews/. Report the problem in the review instead of fixing it.`
  }
  const ids = info.tasks.map((t) => t.id).join(', ')
  if (verdict.code === 'worktree') {
    return [
      `Polier: write to ${rel || target} blocked, ${verdict.reason} (${ids}).`,
      "Do the work in the task's worktree, not in the main checkout.",
      'If the change is needed elsewhere, stop and report it under open_questions.',
    ].join(' ')
  }
  const allowed = [...new Set(info.tasks.flatMap((t) => t.scope_write ?? []))].join(', ') || 'nothing'
  return [
    `Polier: write to ${rel || target} blocked, the path ${verdict.reason} of ${ids}.`,
    `Allowed: ${allowed}.`,
    'Do not try another way to write it. If the change is needed, stop and report it under open_questions.',
  ].join(' ')
}

// ---------------------------------------------------------------------------
// stop check
// ---------------------------------------------------------------------------

async function scopeCheck(ctx, config, agent, info, taskId, signal) {
  const argv = [config.python, path.join(TOOLS, 'scope_check.py'), info.root, '--json']
  if (taskId) argv.push('--task', taskId)
  if (info.state.role === 'lead') argv.push('--allow-board')
  const result = await run(ctx, agent, argv, { cwd: info.root, timeoutMs: 60_000, signal })
  try {
    return JSON.parse(result.stdout.trim().split('\n').pop())
  } catch {
    return { ok: false, error: (result.stderr || result.stdout || `exit ${result.code}`).trim().slice(0, 500) }
  }
}

export async function onTurnStopping(ctx, config, payload) {
  if (!config.stopCheck) return
  const agent = payload?.agent
  if (!agent || typeof agent.steer !== 'function') return
  const info = context(ctx, agent)
  if (!info || info.state.role !== 'worker' || info.tasks.length !== 1) return
  const state = info.state
  if (state.stop.turn !== payload.turn) state.stop = { turn: payload.turn, count: 0 }
  if (state.stop.count >= config.maxStopReminders) return
  const task = info.tasks[0]
  let result
  try {
    result = await scopeCheck(ctx, config, agent, info, task.id, payload.signal)
  } catch {
    return
  }
  if (!result || result.ok || !Array.isArray(result.violations)) return
  state.stop.count += 1
  const lines = result.violations.slice(0, 20).map((v) => `- ${v.path}: ${v.reason}`)
  const foreign = Array.isArray(result.foreign) ? result.foreign : []
  if (foreign.length > 0) {
    lines.push('', 'Foreign changes from other live claims (not yours):')
    for (const item of foreign.slice(0, 20)) {
      lines.push(`- foreign changes (task ${item.task}, harness ${item.harness}): ${item.path}`)
    }
  }
  agent.steer(message([
    `Polier: the working tree has changes outside the scope of ${task.id}.`,
    ...lines,
    `Allowed: ${(task.scope_write ?? []).join(', ') || 'nothing'}.`,
    'Undo these changes (git checkout/rm for files you created or edited), or, if they are needed,',
    'keep them and report each one under open_questions in your result. Then finish.',
  ].join('\n')))
}

// ---------------------------------------------------------------------------
// heartbeat and kill warning on tool calls (PL-04, PL-16)
// ---------------------------------------------------------------------------

/**
 * Before every tool call: refresh the session's claim heartbeat (at most once
 * per minute) and warn once per turn when a bash command stops processes.
 * Never changes the call itself; a warning is a message, not a denial.
 */
export async function onToolPreExecute(ctx, config, exec, next) {
  try {
    const agent = exec.agent
    if (agent) {
      const state = stateOf(agent)
      if (state.claims.length > 0 && Date.now() - (state.lastBeat ?? 0) >= HEARTBEAT_MS) {
        state.lastBeat = Date.now()
        const info = context(ctx, agent)
        if (info) await beatClaims(ctx, config, agent, info.root)
      }
      if (exec.name === 'bash') {
        const args = exec.arguments && typeof exec.arguments === 'object' ? exec.arguments : {}
        if (typeof args.command === 'string' && processKills(args.command).length > 0) {
          const turn = Number.isInteger(state.turn) ? state.turn : 0
          if (state.killTurn !== turn) {
            state.killTurn = turn
            try {
              const outcome = agent.steer(message("Polier: do not stop processes you did not start; use your slot's ports."))
              if (outcome && typeof outcome.catch === 'function') outcome.catch(() => {})
            } catch { /* advisory only */ }
          }
        }
      }
    }
  } catch { /* never block a tool call on our own error */ }
  return next()
}

/** Release the claims a disposed session still holds (best effort). */
export async function onAgentDisposed(ctx, config, payload) {
  const agent = payload?.agent
  const id = agent?.id
  if (!id) return
  const state = sessions.get(id)
  sessions.delete(id)
  if (!state || !Array.isArray(state.claims) || state.claims.length === 0) return
  let root
  try {
    root = findRoot(agentCwd(ctx, agent))
  } catch {
    root = undefined
  }
  if (!root) return
  for (const task of state.claims) {
    try {
      await run(ctx, agent,
        claimArgv(config, 'release', task, '--session', String(id), '--root', String(root)),
        { cwd: String(root), timeoutMs: 20_000 })
    } catch { /* best effort */ }
  }
}

// ---------------------------------------------------------------------------
// tools
// ---------------------------------------------------------------------------

const ANY = {}

function jsonTool(def) {
  return {
    ...def,
    output: {
      schema: ANY,
      render: (_args, value) => [{ type: 'text', text: JSON.stringify(value, null, 2) }],
    },
  }
}

function needProject(ctx, agent, project) {
  const base = agentCwd(ctx, agent)
  const root = findRoot(project ? path.resolve(base, project) : base)
  if (!root) throw new Error('no board.json found in this folder or above; is this a Polier project?')
  const board = loadBoard(root)
  if (!board) throw new Error(`board.json in ${root} is missing or invalid`)
  return { root, board }
}

const PROJECT_PARAM = {
  type: 'string',
  description: 'Project folder (with board.json). Default: the session directory or the nearest parent with a board.',
}

export function tools(ctx, config) {
  const status = jsonTool({
    name: 'pl_status',
    description: 'Show the Polier board: the running task with its write scope and brief, the tasks ready to start with handoff notes from their dependencies, and open questions. Read this first in a project that has a board.json.',
    parameters: { type: 'object', properties: { project: PROJECT_PARAM } },
    isConcurrencySafe: () => true,
    async execute(args, exec) {
      const { root, board } = needProject(ctx, exec.agent, args.project)
      const state = stateOf(exec.agent)
      const active = activeTasks(board, { root, cwd: agentCwd(ctx, exec.agent), pinned: state.pinned })
      return {
        root,
        project: board.project,
        profile: board.profile,
        stage: board.stage ?? 1,
        role: state.role,
        enforce: config.enforce,
        running: active.tasks.map((t) => ({
          id: t.id,
          title: t.title,
          brief: `tasks/${t.id}.md`,
          scope_write: t.scope_write ?? [],
          scope_write_forbidden: t.scope_write_forbidden ?? [],
          gates: t.gates ?? [],
          round: t.round ?? 0,
        })),
        selected_by: active.how,
        claims: await liveClaims(ctx, config, exec.agent, root),
        ready: readyTasks(board),
        open_questions: (board.open_questions ?? []).filter((q) => q?.status === 'open'),
      }
    },
  })

  const gate = jsonTool({
    name: 'pl_gate',
    description: 'Run one quality gate of a task through tools/gate.py. The full output goes to reviews/evidence/, the result shows pass/fail, the failing lines and the record path. Put the record path into your result as evidence; it is the only accepted proof that a gate passed.',
    parameters: {
      type: 'object',
      properties: {
        task: { type: 'string', description: 'Task ID, e.g. M03.' },
        gate: { type: 'string', description: 'Gate name exactly as in the task\'s gates list, e.g. tests.' },
        command: { type: 'string', description: 'Shell command of the gate, from AGENTS.md or the brief.' },
        timeout_s: { type: 'integer', description: 'Seconds before the gate is stopped. Default 600.' },
        lock_wait_s: { type: 'integer', description: 'Seconds to wait for an exclusive resource; default 0 (report busy at once).' },
        project: PROJECT_PARAM,
      },
      required: ['task', 'gate', 'command'],
    },
    async execute(args, exec) {
      const { root, board } = needProject(ctx, exec.agent, args.project)
      const task = board.tasks.find((t) => t?.id === args.task)
      if (!task) throw new Error(`task ${args.task} is not on the board`)
      if (Array.isArray(task.gates) && task.gates.length && !task.gates.includes(args.gate)) {
        throw new Error(`gate ${args.gate} is not listed for ${args.task}; listed: ${task.gates.join(', ')}`)
      }
      const timeout = Number.isInteger(args.timeout_s) && args.timeout_s > 0 ? args.timeout_s : 600
      const lockWait = Number.isInteger(args.lock_wait_s) && args.lock_wait_s >= 0 ? args.lock_wait_s : 0
      const argv = [config.python, path.join(TOOLS, 'gate.py'), '--task', args.task, '--name', args.gate,
        '--root', root, '--timeout', String(timeout), '--lock-wait', String(lockWait)]
      const slot = polierSlot(root)
      if (slot !== undefined) argv.push('--slot', String(slot))
      for (const resource of task.exclusive ?? []) {
        if (typeof resource === 'string' && resource) argv.push('--exclusive', resource)
      }
      argv.push('--shell', args.command)
      const result = await run(ctx, exec.agent, argv, {
        cwd: root, timeoutMs: (timeout + 30) * 1000, signal: exec.signal, strictShell: true,
      })
      const lines = result.stdout.trim().split('\n')
      const last = lines[lines.length - 1] ?? ''
      const record = last.startsWith('record: ') ? last.slice(8).trim() : null
      const busy = result.code === 75
      const summary = (record ? lines.slice(0, -1) : lines).join('\n').slice(-4000)
      return {
        task: args.task,
        gate: args.gate,
        passed: result.code === 0 && record !== null,
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
    description: 'Compare every changed file in the project (git status) with the write scope of a task. Run it before you submit a task.',
    parameters: {
      type: 'object',
      properties: {
        task: { type: 'string', description: 'Task ID. Default: the running task.' },
        project: PROJECT_PARAM,
      },
    },
    isConcurrencySafe: () => true,
    async execute(args, exec) {
      const { root } = needProject(ctx, exec.agent, args.project)
      const state = stateOf(exec.agent)
      const result = await scopeCheck(ctx, config, exec.agent, { root, state }, args.task || state.pinned, exec.signal)
      if (result && Array.isArray(result.foreign) && result.foreign.length > 0) {
        result.foreign_changes = result.foreign.map(
          (item) => `foreign changes (task ${item.task}, harness ${item.harness}): ${item.path}`)
      }
      return result
    },
  })

  const check = jsonTool({
    name: 'pl_check',
    description: 'Run tools/check.py on the project: mandatory files, word budgets, board consistency, traceability and gate evidence. Exit 0 means no errors.',
    parameters: { type: 'object', properties: { project: PROJECT_PARAM } },
    isConcurrencySafe: () => true,
    async execute(args, exec) {
      const { root } = needProject(ctx, exec.agent, args.project)
      const result = await run(ctx, exec.agent, [config.python, path.join(TOOLS, 'check.py'), root],
        { cwd: root, timeoutMs: 120_000, signal: exec.signal })
      return { ok: result.code === 0, exit_code: result.code, output: (result.stdout + result.stderr).trim().slice(-6000) }
    },
  })

  return [status, gate, scope, check]
}

// ---------------------------------------------------------------------------
// human command /pl
// ---------------------------------------------------------------------------

const HELP = [
  '/pl status        role, running task and scope of this session',
  '/pl lead          this session may write everything (planning, board, briefs, merge)',
  '/pl worker        back to the scope of the running task (default)',
  '/pl reviewer      this session writes only under reviews/ (independent review)',
  '/pl task <ID>     bind this session to one task (several tasks in progress)',
  '/pl task          remove the binding',
  '/pl render        regenerate STATUS.md from board.json (lead only)',
].join('\n')

export function command(ctx, config) {
  return {
    name: 'pl',
    description: 'Polier: switch this session between lead, worker and reviewer, bind it to a task, show status.',
    input: { hint: 'status | lead | worker | reviewer | task <ID> | render' },
    async handler({ agent, rawInput, signal }) {
      const [verb = 'status', arg] = String(rawInput ?? '').trim().split(/\s+/).filter(Boolean)
      const state = stateOf(agent)
      const info = context(ctx, agent)
      switch (verb.toLowerCase()) {
        case 'lead':
          state.role = 'lead'
          return { kind: 'success', text: 'Lead mode: this session may write outside task scopes. Use /pl worker to return.' }
        case 'worker':
          state.role = 'worker'
          return { kind: 'success', text: 'Worker mode: writes are limited to the running task\'s scope.' }
        case 'reviewer':
          state.role = 'reviewer'
          return { kind: 'success', text: 'Reviewer mode: this session writes only under reviews/. Use /pl worker to return.' }
        case 'off':
          state.role = 'off'
          return { kind: 'success', text: 'Guard off for this session. Use /pl worker to turn it on again.' }
        case 'task': {
          if (!arg) {
            const released = []
            if (info && agent?.id) {
              for (const task of [...state.claims]) {
                if (await releaseClaim(ctx, config, agent, info.root, task)) released.push(task)
              }
            }
            state.claims = []
            state.pinned = undefined
            return {
              kind: 'success',
              text: `Task binding removed.${released.length ? ` Claim released: ${released.join(', ')}.` : ''}`,
            }
          }
          const id = arg.toUpperCase()
          if (info && !info.board.tasks.some((t) => t?.id === id)) return { kind: 'error', text: `Task ${id} is not on the board.` }
          if (info && agent?.id) {
            let taken
            try {
              taken = await takeClaim(ctx, config, agent, info.root, id)
            } catch (error) {
              return { kind: 'error', text: `Cannot claim ${id}: ${String(error?.message ?? error)}` }
            }
            if (!taken.ok) {
              if (taken.code !== 2) return { kind: 'error', text: `Cannot claim ${id}: ${taken.message}` }
              // No git repository yet: binding still works, the claim is best effort.
              state.pinned = id
              return {
                kind: 'success',
                text: `This session now works on ${id}. The claim was not taken: ${taken.message}`,
              }
            }
            state.claims = [...new Set([...state.claims, id])]
          }
          state.pinned = id
          return { kind: 'success', text: `This session now works on ${id}.` }
        }
        case 'render': {
          if (state.role !== 'lead') return { kind: 'error', text: 'Only a lead session renders STATUS.md. Use /pl lead first.' }
          if (!info) return { kind: 'error', text: 'No board.json in this folder or above.' }
          const result = await run(ctx, agent, [config.python, path.join(TOOLS, 'render_status.py'), info.root],
            { cwd: info.root, timeoutMs: 60_000, signal })
          return result.code === 0
            ? { kind: 'success', text: result.stdout.trim() }
            : { kind: 'error', text: (result.stderr || result.stdout).trim() || `exit ${result.code}` }
        }
        case 'status': {
          if (!info) return { kind: 'success', text: `Role: ${state.role}. No board.json in this folder or above.` }
          const tasks = info.tasks.map((t) => `${t.id} ${t.title} → ${(t.scope_write ?? []).join(', ')}`)
          return {
            kind: 'success',
            text: [
              `Project: ${info.board.project} (${info.root})`,
              `Role: ${state.role} · guard: ${config.enforce}${state.pinned ? ` · bound to ${state.pinned}` : ''}`,
              tasks.length ? `Running:\n${tasks.join('\n')}` : 'No task in progress: the guard is idle.',
            ].join('\n'),
          }
        }
        default:
          return { kind: 'success', text: HELP }
      }
    },
  }
}

// ---------------------------------------------------------------------------
// skill
// ---------------------------------------------------------------------------

export function skill() {
  const file = path.join(PACKAGE, 'SKILL.md')
  const text = readFileSync(file, 'utf8')
  const m = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?/.exec(text)
  if (!m) throw new Error('SKILL.md has no frontmatter')
  const meta = {}
  let key
  for (const line of m[1].split(/\r?\n/)) {
    const kv = /^([A-Za-z_-]+):\s*(.*)$/.exec(line)
    if (kv) {
      key = kv[1]
      meta[key] = kv[2]
    } else if (key && line.trim()) {
      meta[key] += ' ' + line.trim()
    }
  }
  const body = text.slice(m[0].length)
  return {
    name: meta.name,
    description: meta.description,
    content: `${body}\n\n> Package folder: \`${PACKAGE}\`. Paths such as \`prompt/generator.md\` and \`tools/check.py\` are relative to it.\n`,
    path: file,
    source: 'bundled',
    resourceBase: { kind: 'directory', path: PACKAGE },
  }
}

// ---------------------------------------------------------------------------
// plugin entry
// ---------------------------------------------------------------------------

function log(ctx, level, text) {
  try {
    const logger = ctx.logger?.(SOURCE)
    if (logger && typeof logger[level] === 'function') return logger[level](text)
  } catch { /* fall through */ }
  if (level === 'warn' || level === 'error') console.warn(`[${SOURCE}] ${text}`)
}

export function apply(ctx, rawConfig) {
  const config = resolveConfig(rawConfig ?? {})

  // Each optional service gets its own sub-plugin: it mounts when the service
  // exists and unwinds with it, so a missing service never blocks the rest.
  ctx.inject(['tools'], (c) => {
    if (config.enforce === 'deny') c.tools.guard((exec) => checkWrite(c, config, exec))
    else if (config.enforce === 'ask') {
      c.on('tools/pre-execute', async (exec, next) => {
        const reason = checkWrite(c, config, exec)
        return reason ? { kind: 'ask', reason } : next()
      })
    }
    c.on('tools/pre-execute', (exec, next) => onToolPreExecute(c, config, exec, next))
    for (const def of tools(c, config)) c.tools.register(def)
  })

  ctx.inject(['commands'], (c) => {
    c.commands.register(command(c, config))
  })

  if (config.skill) {
    ctx.inject(['skills'], (c) => {
      try {
        c.skills.register(skill())
      } catch (error) {
        log(c, 'warn', `skill not registered: ${String(error)}`)
      }
    })
  }

  ctx.on('agent/turn-stopping', (payload) => {
    const agent = payload?.agent
    if (agent?.id && Number.isInteger(payload.turn)) {
      const state = sessions.get(agent.id)
      if (state) state.turn = payload.turn
    }
    return onTurnStopping(ctx, config, payload)
  })
  ctx.on('agent/disposed', (payload) => {
    onAgentDisposed(ctx, config, payload).catch(() => {})
  })
  ctx.effect(() => () => sessions.clear())
}
