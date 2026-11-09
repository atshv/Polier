// Per-session state (role, bound task, claims) and the claim calls. In memory
// only: a restarted harness starts every session as a worker again, the safe
// side. Claims are one JSON file per task in <git-common-dir>/polier/claims/,
// written by tools/claim.py so there is one implementation.

import { readFileSync } from 'node:fs'
import path from 'node:path'

import { activeTasks, findProject, loadBoard } from './project.mjs'
import { agentCwd, run } from './run.mjs'

export const ROLES = ['worker', 'reviewer', 'lead', 'off']
const HEARTBEAT_MS = 60_000
const sessions = new Map()

export function stateOf(agent) {
  const id = agent?.id
  if (!id) return { role: 'worker', pinned: undefined, claims: [], stop: { turn: -1, count: 0 } }
  let state = sessions.get(id)
  if (!state) {
    state = { role: 'worker', specialist: undefined, pinned: undefined, claims: [], lastBeat: 0, stop: { turn: -1, count: 0 }, turn: 0, killTurn: -1 }
    sessions.set(id, state)
  }
  return state
}

export function forget(agentId) {
  const state = sessions.get(agentId)
  sessions.delete(agentId)
  return state
}

export function clearSessions() {
  sessions.clear()
}

/** Project root, board and the tasks that bind this session; undefined outside a planned project. */
export function context(ctx, agent) {
  const cwd = agentCwd(ctx, agent)
  const root = findProject(cwd)
  if (!root) return undefined
  const board = loadBoard(root)
  if (!board) return undefined
  const state = stateOf(agent)
  return { cwd, root, board, state, ...activeTasks(board, { root, cwd, pinned: state.pinned }) }
}

export function polierSlot(folder) {
  try {
    const data = JSON.parse(readFileSync(path.join(String(folder), '.polier-slot'), 'utf8'))
    const value = data && typeof data === 'object' ? data.slot ?? data.N : undefined
    return Number.isInteger(value) && value >= 0 ? value : undefined
  } catch {
    return undefined
  }
}

function claimArgv(config, ...args) {
  return [config.python, path.join(config.tools, 'claim.py'), ...args]
}

function lastLine(result) {
  const text = (result.stderr || result.stdout || `exit ${result.code}`).trim()
  return text.split('\n').filter(Boolean).pop() || `exit ${result.code}`
}

export async function takeClaim(ctx, config, agent, root, id) {
  const argv = claimArgv(config, 'take', id, '--harness', 'dsh', '--session', String(agent.id), '--root', String(root))
  const task = (loadBoard(root)?.tasks ?? []).find((t) => t?.id === id)
  if (task && typeof task.worktree === 'string' && task.worktree.trim()) argv.push('--worktree', path.resolve(root, task.worktree))
  const slot = polierSlot(agentCwd(ctx, agent) || root)
  if (slot !== undefined) argv.push('--slot', String(slot))
  const result = await run(ctx, agent, argv, { cwd: String(root), timeoutMs: 30_000 })
  return { ok: result.code === 0, code: result.code, message: lastLine(result) }
}

export async function releaseClaim(ctx, config, agent, root, id, session = agent?.id) {
  try {
    const result = await run(ctx, agent, claimArgv(config, 'release', id, '--session', String(session), '--root', String(root)),
      { cwd: String(root), timeoutMs: 20_000 })
    return result.code === 0
  } catch {
    return false
  }
}

/** Refresh the heartbeat of this session's claims, at most once per minute. */
export async function beatClaims(ctx, config, agent) {
  const state = stateOf(agent)
  if (state.claims.length === 0 || Date.now() - (state.lastBeat ?? 0) < HEARTBEAT_MS) return
  state.lastBeat = Date.now()
  const root = findProject(agentCwd(ctx, agent))
  if (!root) return
  for (const id of state.claims) {
    try {
      await run(ctx, agent, claimArgv(config, 'beat', id, '--session', String(agent.id), '--root', String(root)),
        { cwd: String(root), timeoutMs: 20_000 })
    } catch { /* best effort */ }
  }
}

export async function liveClaims(ctx, config, agent, root) {
  try {
    const result = await run(ctx, agent, claimArgv(config, 'list', '--root', String(root), '--json'),
      { cwd: String(root), timeoutMs: 20_000 })
    const rows = JSON.parse(result.stdout.trim() || '[]')
    return Array.isArray(rows) ? rows : []
  } catch {
    return []
  }
}
