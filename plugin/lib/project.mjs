// Project lookup and the read-only board views for the live context and the
// tools: which tasks bind a session and which tasks are ready. The rules that
// decide a write or a command live in core/ (see guard.mjs).

import { existsSync, readFileSync } from 'node:fs'
import path from 'node:path'

/** The nearest folder at or above `start` with a board.json or a factory.json (a line before its plan), or undefined. */
export function findProject(start) {
  if (!start) return undefined
  let dir = path.resolve(start)
  for (;;) {
    if (existsSync(path.join(dir, 'board.json')) || existsSync(path.join(dir, 'factory.json'))) return dir
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

/**
 * The tasks whose scope applies to a session.
 * Order: the task bound with `pl_task`, the in_progress task whose
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

/** Ids of the declared stages, in board order. */
function stageIds(board) {
  return (Array.isArray(board?.stages) ? board.stages : [])
    .filter((s) => s && typeof s === 'object' && typeof s.id === 'string')
    .map((s) => s.id)
}

/** The stages[].id a task belongs to; an integer stage counts from 1. */
function taskStageId(board, task) {
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
function stageReport(board) {
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

/** Ready tasks: pending, every dependency done, blocking stages complete. */
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
