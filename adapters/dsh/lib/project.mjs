// Board and scope logic shared by the guard, the stop check and the tools.
// JavaScript mirror of core/board.py and core/scope.py (check_write), so the
// guard can decide synchronously, without starting a process. Keep the two in
// step: both are tested against core/tests/write_cases.json.

import { execFileSync } from 'node:child_process'
import { existsSync, readFileSync, realpathSync } from 'node:fs'
import path from 'node:path'

/** macOS and Windows file systems are case-insensitive: compare paths ignoring case (PL-16). */
export const CASE_INSENSITIVE = process.platform === 'darwin' || process.platform === 'win32'
/** Programs that stop processes (PL-16); the guard warns, it never denies on them. */
const KILLERS = new Set(['kill', 'killall', 'pkill'])
const SHELLS = new Set(['sh', 'bash', 'zsh', 'dash', 'ksh'])
const WRAPPERS = new Set(['sudo', 'env', 'nohup', 'time', 'command', 'exec', 'nice', 'ionice', 'stdbuf', 'doas'])
const XARGS_VALUE_OPTIONS = new Set(['-n', '--max-args', '-I', '--replace', '-P', '--max-procs',
  '-d', '--delimiter', '-L', '--max-lines', '-s', '--max-chars', '-E', '--eof'])

/** Always writable: gate logs and records belong to the task that produced them. */
export const ALWAYS_ALLOWED = ['reviews/evidence']
/** Lead-owned (1.1): the board, the generated status, the briefs and the run records. */
export const BOARD_FILES = ['board.json', 'STATUS.md', 'tasks', 'runs']
/** The only folder a reviewer session writes to. */
export const REVIEWS = 'reviews'
/** Approval records are the approver's: a reviewer writes review material, never approvals. */
export const APPROVALS = 'reviews/approvals'

/** Forward slashes, no trailing slash, `.` and `..` resolved; '' for the root. */
export function normalized(p) {
  const s = String(p ?? '').trim().replace(/\\/g, '/')
  if (!s) return ''
  const clean = path.posix.normalize(s)
  return clean === '.' || clean === './' ? '' : clean.replace(/\/+$/, '')
}

/** True if `p` equals `entry` or lies below the folder `entry`; ignores case on macOS/Windows. */
export function inside(p, entry) {
  let a = normalized(p)
  let b = normalized(entry)
  if (!b) return false
  if (CASE_INSENSITIVE) {
    a = a.toLowerCase()
    b = b.toLowerCase()
  }
  return a === b || a.startsWith(b + '/')
}

// ---------------------------------------------------------------------------
// worktrees (PL-05): the JS mirror of core.paths.is_main_checkout / core.scope
// ---------------------------------------------------------------------------

const mainCheckoutCache = new Map()

function gitValue(root, args) {
  try {
    return execFileSync('git', ['-C', String(root), ...args], {
      encoding: 'utf8', timeout: 5000, stdio: ['ignore', 'pipe', 'ignore'],
    }).trim()
  } catch {
    return undefined
  }
}

/** True when `root` is the main working tree; false in a linked worktree or outside git. */
export function isMainCheckout(root) {
  if (!root) return false
  const key = String(root)
  if (mainCheckoutCache.has(key)) return mainCheckoutCache.get(key)
  let value = false
  try {
    const top = gitValue(root, ['rev-parse', '--show-toplevel'])
    const common = gitValue(root, ['rev-parse', '--git-common-dir'])
    if (top && common) {
      const commonPath = path.isAbsolute(common) ? common : path.resolve(key, common)
      value = path.dirname(realpathSync(commonPath)) === realpathSync(top)
    }
  } catch {
    value = false
  }
  mainCheckoutCache.set(key, value)
  return value
}

/**
 * `worktrees` mode of the board: required, recommended or off.
 * M/L default to required on a 1.0 board and to recommended on a 0.9 board
 * (migration: an existing project keeps working until its owner opts in).
 */
export function worktreeMode(board) {
  if (!board || typeof board !== 'object') return 'off'
  if (['required', 'recommended', 'off'].includes(board.worktrees)) return board.worktrees
  if (board.profile !== 'M' && board.profile !== 'L') return 'off'
  return board.schema_version === '1.0' ? 'required' : 'recommended'
}

/** The worktree a worker must use instead of the main checkout, or undefined (PL-05). */
export function worktreeDenial(tasks, { board, root } = {}) {
  if (!root || worktreeMode(board) !== 'required') return undefined
  const tree = (tasks ?? []).find((t) => typeof t?.worktree === 'string' && t.worktree.trim())?.worktree
  if (!tree) return undefined
  return isMainCheckout(root) ? tree : undefined
}

/** The nearest folder at or above `start` that holds a board.json, or undefined. */
export function findRoot(start) {
  if (!start) return undefined
  let dir = path.resolve(start)
  for (;;) {
    if (existsSync(path.join(dir, 'board.json'))) return dir
    const parent = path.dirname(dir)
    if (parent === dir) return undefined
    dir = parent
  }
}

/** Parsed board.json, or undefined when missing or invalid (the guard then stays out of the way). */
export function loadBoard(root) {
  try {
    const board = JSON.parse(readFileSync(path.join(root, 'board.json'), 'utf8'))
    return board && Array.isArray(board.tasks) ? board : undefined
  } catch {
    return undefined
  }
}

/** Path of `abs` relative to `root`, with forward slashes; starts with '../' when outside. */
export function relative(root, abs) {
  return normalized(path.relative(root, abs).split(path.sep).join('/'))
}

/**
 * The tasks whose scope applies to a session.
 * Order: the task pinned with `/pl task <ID>`, the in_progress task whose
 * `worktree` contains the session's directory, every in_progress task.
 * @returns {{ tasks: object[], how: 'pinned'|'worktree'|'single'|'several'|'none' }}
 */
export function activeTasks(board, { root, cwd, pinned }) {
  const tasks = (board?.tasks ?? []).filter((t) => t && typeof t === 'object')
  if (pinned) {
    const task = tasks.find((t) => t.id === pinned)
    if (task) return { tasks: [task], how: 'pinned' }
  }
  const running = tasks.filter((t) => t.status === 'in_progress')
  if (running.length === 0) return { tasks: [], how: 'none' }
  if (cwd && root) {
    const here = path.resolve(cwd)
    const byTree = running.filter((t) => {
      if (typeof t.worktree !== 'string' || !t.worktree) return false
      const tree = path.resolve(root, t.worktree)
      return here === tree || here.startsWith(tree + path.sep)
    })
    if (byTree.length === 1) return { tasks: byTree, how: 'worktree' }
  }
  return { tasks: running, how: running.length === 1 ? 'single' : 'several' }
}

/**
 * Decide whether a worker may write `rel` (relative to the project root).
 * With several candidate tasks the path must fit one of them. The optional
 * `context` (`{ board, root, cwd }`) turns on the worktree rule of PL-05; with
 * two arguments the decision is the one the shared write_cases.json table pins.
 * @returns {{ ok: true } | { ok: false, reason: string, code: string }}
 */
export function decide(rel, tasks, context = {}) {
  if (rel === '..' || rel.startsWith('../') || path.isAbsolute(rel)) {
    return { ok: false, code: 'outside-project', reason: 'is outside the project folder' }
  }
  if (ALWAYS_ALLOWED.some((a) => inside(rel, a))) return { ok: true }
  if (BOARD_FILES.some((b) => inside(rel, b))) {
    return { ok: false, code: 'lead-owned', reason: 'is lead-owned (board, status or brief)' }
  }
  const tree = worktreeDenial(tasks, context)
  if (tree) return { ok: false, code: 'worktree', reason: `work in ${tree}` }
  let forbidden = false
  for (const task of tasks) {
    const deny = (task.scope_write_forbidden ?? []).filter((p) => typeof p === 'string')
    const allow = (task.scope_write ?? []).filter((p) => typeof p === 'string')
    if (deny.some((d) => inside(rel, d))) {
      forbidden = true
      continue
    }
    if (allow.some((a) => inside(rel, a))) return { ok: true }
  }
  return forbidden
    ? { ok: false, code: 'forbidden', reason: 'is listed in scope_write_forbidden' }
    : { ok: false, code: 'outside-scope', reason: 'is outside the write scope' }
}

/**
 * Guard decision for one session role, as core.scope.check_write: a reviewer
 * writes only under reviews/, a worker with a running task only inside its
 * scope, every other case is allowed.
 * @returns {{ ok: true } | { ok: false, reason: string, code: string }}
 */
export function checkPath(rel, tasks, role = 'worker', context = {}) {
  if (role === 'reviewer') {
    if (!inside(rel, REVIEWS) || rel.startsWith('../')) {
      return { ok: false, code: 'reviewer', reason: 'is outside reviews/' }
    }
    if (inside(rel, APPROVALS)) {
      return { ok: false, code: 'approvals', reason: 'is an approval record, not review material' }
    }
    return { ok: true }
  }
  if (role !== 'worker' || tasks.length === 0) return { ok: true }
  return decide(rel, tasks, context)
}

/** Ready tasks: pending, every dependency done. Same rule as tools/render_status.py. */
/** Ids of the declared stages, in board order (PL-08). */
export function stageIds(board) {
  return (Array.isArray(board?.stages) ? board.stages : [])
    .filter((s) => s && typeof s === 'object' && typeof s.id === 'string')
    .map((s) => s.id)
}

/** The stages[].id a task belongs to; an integer stage counts from 1. */
export function taskStageId(board, task) {
  const ids = stageIds(board)
  if (ids.length === 0) return undefined
  const value = task?.stage
  if (typeof value === 'string') return ids.includes(value) ? value : undefined
  if (Number.isInteger(value) && value >= 1 && value <= ids.length) return ids[value - 1]
  return undefined
}

/** Without the file system a done task of the stage with evidence counts as the gate (see core/board.py). */
function stageGateSatisfied(members, gate) {
  return members.some((t) => t.status === 'done' && (t.gates ?? []).includes(gate)
    && Array.isArray(t.evidence) && t.evidence.length > 0)
}

/** One entry per declared stage: stop state, owner decision, missing exit gates, completeness. */
export function stageReport(board) {
  const tasks = (board?.tasks ?? []).filter((t) => t && typeof t === 'object')
  const stages = (Array.isArray(board?.stages) ? board.stages : []).filter((s) => s && typeof s === 'object')
  const report = new Map()
  for (const [index, stage] of stages.entries()) {
    const sid = stage.id
    if (typeof sid !== 'string') continue
    const members = tasks.filter((t) => taskStageId(board, t) === sid)
    const gates = (stage.exit_gates ?? []).filter((g) => typeof g === 'string')
    const missingGates = gates.filter((g) => !stageGateSatisfied(members, g))
    const decision = stage.owner_decision ?? 'continue'
    report.set(sid, {
      id: sid,
      index: index + 1,
      ownerDecision: decision,
      ownerPending: decision === 'pending',
      stopped: decision === 'stop',
      missingGates,
      dependsOn: (stage.depends_on ?? []).filter((d) => typeof d === 'string'),
      incompleteDeps: [],
      complete: false,
    })
  }
  const complete = (sid, seen) => {
    const entry = report.get(sid)
    if (!entry || seen.has(sid)) return false
    seen.add(sid)
    const blocked = entry.dependsOn.filter((d) => !complete(d, new Set(seen)))
    entry.incompleteDeps = blocked
    entry.complete = !entry.stopped && !entry.ownerPending
      && entry.missingGates.length === 0 && blocked.length === 0
    return entry.complete
  }
  for (const sid of report.keys()) complete(sid, new Set())
  return [...report.values()]
}

/** Ready tasks: pending, every dependency done, blocking stages complete (PL-08). */
export function readyTasks(board) {
  const tasks = (board?.tasks ?? []).filter((t) => t && typeof t === 'object')
  const done = new Set(tasks.filter((t) => t.status === 'done').map((t) => t.id))
  const byId = new Map(tasks.map((t) => [t.id, t]))
  const stages = new Map(stageReport(board).map((entry) => [entry.id, entry]))
  return tasks
    .filter((t) => {
      if (t.status !== 'pending' || !(t.depends_on ?? []).every((d) => done.has(d))) return false
      const sid = taskStageId(board, t)
      const stage = sid ? stages.get(sid) : undefined
      return !stage || (!stage.stopped && stage.incompleteDeps.length === 0)
    })
    .map((t) => ({
      id: t.id,
      title: t.title,
      brief: `tasks/${t.id}.md`,
      handoff: (t.depends_on ?? []).flatMap((d) => (byId.get(d)?.handoff ?? []).map((h) => `${d}: ${h}`)),
    }))
}

// ---------------------------------------------------------------------------
// processes a command would stop (PL-16): the JS mirror of
// core.shell.process_kills. Lightweight on purpose; it only feeds a warning,
// never a denial.
// ---------------------------------------------------------------------------

const HEREDOC = /<<-?\s*(['"]?)([A-Za-z_][A-Za-z0-9_]*)\1/g
const ASSIGNMENT = /^[A-Za-z_][A-Za-z0-9_]*=/
const SEGMENT_BREAK = /;|&&|\|\||\||&|\(|\)|\n/

/** Drop heredoc bodies; their text is data, not commands. */
function stripHeredocs(command) {
  const out = []
  const pending = []
  for (const line of String(command ?? '').split('\n')) {
    if (pending.length > 0) {
      if (line.replace(/^\t+/, '') === pending[0]) pending.shift()
      continue
    }
    out.push(line)
    for (const match of line.matchAll(HEREDOC)) pending.push(match[2])
  }
  return out.join('\n')
}

/** Drop quoted strings: `echo "kill"` is text, not a command. */
function stripQuotes(command) {
  return command.replace(/'[^']*'/g, "''").replace(/"[^"]*"/g, '""')
}

function stripCommandPosition(args) {
  let rest = args
  while (rest.length > 0 && ASSIGNMENT.test(rest[0])) rest = rest.slice(1)
  while (rest.length > 0 && WRAPPERS.has(path.basename(rest[0]))) {
    rest = rest.slice(1)
    while (rest.length > 0 && (rest[0].startsWith('-') || ASSIGNMENT.test(rest[0]))) rest = rest.slice(1)
  }
  return rest
}

function firstXargsProgram(args) {
  let i = 0
  while (i < args.length) {
    const arg = args[i]
    if (arg.startsWith('-') && arg !== '-') {
      i += XARGS_VALUE_OPTIONS.has(arg) ? 2 : 1
      continue
    }
    return arg
  }
  return undefined
}

/**
 * Programs `command` would use to stop processes: kill, killall, pkill and
 * `xargs kill`, in command position; text in heredocs or quotes does not count.
 * @returns {string[]} matched program names, in order, without duplicates
 */
export function processKills(command, depth = 0) {
  const text = stripHeredocs(command)
  const found = []
  if (depth < 3) {
    const nested = /\b(?:sh|bash|zsh|dash|ksh)\s+-c\s+(['"])([\s\S]*?)\1/g
    for (const match of text.matchAll(nested)) {
      for (const name of processKills(match[2], depth + 1)) {
        if (!found.includes(name)) found.push(name)
      }
    }
  }
  for (const segment of stripQuotes(text).split(SEGMENT_BREAK)) {
    const args = stripCommandPosition(segment.trim().split(/\s+/).filter(Boolean))
    if (args.length === 0) continue
    const name = path.basename(args[0])
    if (KILLERS.has(name)) {
      if (!found.includes(name)) found.push(name)
      continue
    }
    if (name === 'xargs') {
      const program = firstXargsProgram(args.slice(1))
      const base = program ? path.basename(program) : ''
      if (KILLERS.has(base) && !found.includes(base)) found.push(base)
    }
  }
  return found
}

/** True when the command contains a kill pattern (a warning, never a denial). */
export function hasKillPattern(command) {
  return processKills(command).length > 0
}
