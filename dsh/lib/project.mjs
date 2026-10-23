// Board and scope logic shared by the guard, the stop check and the tools.
// Mirrors tools/scope_check.py so the guard can decide synchronously, without
// starting a process. Keep the two in step: the Python tests cover the rules.

import { existsSync, readFileSync } from 'node:fs'
import path from 'node:path'

/** Always writable: gate logs and records belong to the task that produced them. */
export const ALWAYS_ALLOWED = ['reviews/evidence']
/** Lead-owned: a worker must not edit the board, the generated status or briefs. */
export const BOARD_FILES = ['board.json', 'STATUS.md', 'tasks']

/** Forward slashes, no trailing slash, `.` and `..` resolved; '' for the root. */
export function normalized(p) {
  const s = String(p ?? '').trim().replace(/\\/g, '/')
  if (!s) return ''
  const clean = path.posix.normalize(s)
  return clean === '.' || clean === './' ? '' : clean.replace(/\/+$/, '')
}

/** True if `p` equals `entry` or lies below the folder `entry`. */
export function inside(p, entry) {
  const a = normalized(p)
  const b = normalized(entry)
  if (!b) return false
  return a === b || a.startsWith(b + '/')
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
 * With several candidate tasks the path must fit one of them.
 * @returns {{ ok: true } | { ok: false, reason: string, code: string }}
 */
export function decide(rel, tasks) {
  if (rel === '..' || rel.startsWith('../') || path.isAbsolute(rel)) {
    return { ok: false, code: 'outside-project', reason: 'is outside the project folder' }
  }
  if (ALWAYS_ALLOWED.some((a) => inside(rel, a))) return { ok: true }
  if (BOARD_FILES.some((b) => inside(rel, b))) {
    return { ok: false, code: 'lead-owned', reason: 'is lead-owned (board, status or brief)' }
  }
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

/** Ready tasks: pending, every dependency done. Same rule as tools/render_status.py. */
export function readyTasks(board) {
  const tasks = (board?.tasks ?? []).filter((t) => t && typeof t === 'object')
  const done = new Set(tasks.filter((t) => t.status === 'done').map((t) => t.id))
  const byId = new Map(tasks.map((t) => [t.id, t]))
  return tasks
    .filter((t) => t.status === 'pending' && (t.depends_on ?? []).every((d) => done.has(d)))
    .map((t) => ({
      id: t.id,
      title: t.title,
      brief: `tasks/${t.id}.md`,
      handoff: (t.depends_on ?? []).flatMap((d) => (byId.get(d)?.handoff ?? []).map((h) => `${d}: ${h}`)),
    }))
}
