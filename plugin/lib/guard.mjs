// The guard: what a session may write and run, and the stop check at the end of
// a turn. The rules live in core/guard.py; this file forwards each guarded call
// to tools/guard.py and shows the answer. A write the guard cannot decide is
// blocked, a command is let through (the stop check still sees its writes).

import path from 'node:path'

import { run } from './run.mjs'
import { beatClaims, context, stateOf } from './session.mjs'

const COMMAND_TOOLS = new Set(['bash'])
const MAX_VERDICTS = 256

export function message(text) {
  return {
    id: `pl-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    role: 'user',
    content: [{ type: 'text', text }],
    source: { kind: 'plugin', plugin: 'polier' },
  }
}

/** Target path of a guarded tool call, or undefined when the call does not write. */
function targetOf(exec, guarded) {
  const key = guarded[exec.name]
  if (!key) return undefined
  const args = exec.arguments && typeof exec.arguments === 'object' ? exec.arguments : {}
  if (exec.name === 'str_replace_editor' && args.command === 'view') return undefined
  const value = args[key]
  return typeof value === 'string' && value ? value : undefined
}

function commandOf(exec) {
  const args = exec.arguments && typeof exec.arguments === 'object' ? exec.arguments : {}
  return COMMAND_TOOLS.has(exec.name) && typeof args.command === 'string' ? args.command : ''
}

/** Ask tools/guard.py; returns { deny, kills } or { error }. */
async function ask(ctx, config, agent, info, fields) {
  const specialist = info.state.specialist
  const request = {
    root: info.root,
    cwd: info.cwd,
    role: info.state.role,
    tasks: info.tasks.map((t) => t.id).filter(Boolean),
    ...(specialist ? { specialist: { id: specialist.id, title: specialist.title, writes: specialist.writes ?? [] } } : {}),
    ...fields,
  }
  const argv = [config.python, path.join(config.tools, 'guard.py'), JSON.stringify(request)]
  try {
    const result = await run(ctx, agent, argv, { cwd: info.root, timeoutMs: 20_000, preferShell: false })
    const answer = JSON.parse(result.stdout.trim().split('\n').pop() || '{}')
    if (result.code !== 0 || answer.error) return { error: answer.error || (result.stderr || `exit ${result.code}`).trim() }
    return { deny: answer.deny || undefined, kills: answer.kills === true }
  } catch (error) {
    return { error: String(error?.message ?? error) }
  }
}

/**
 * The guard decision for one write.
 * @returns {Promise<string|undefined>} a denial reason, or undefined to allow
 */
export async function checkWrite(ctx, config, exec) {
  if (config.enforce === 'off' || !exec.agent) return undefined
  const target = targetOf(exec, config.guardedTools)
  if (!target) return undefined
  const info = context(ctx, exec.agent)
  if (!info || info.state.role === 'off') return undefined
  const answer = await ask(ctx, config, exec.agent, info, { path: target })
  if (answer.error) {
    return `Polier: write to ${target} blocked, the guard could not decide (${answer.error.slice(0, 300)}). Check that ${config.python} runs, then retry.`
  }
  return answer.deny
}

/**
 * Verdicts of the async check, read by the synchronous harness guard so a later
 * listener cannot turn a denial into permission.
 */
export function verdicts() {
  const map = new Map()
  return {
    put(exec, reason) {
      if (!exec?.callId || !reason) return
      map.set(exec.callId, reason)
      if (map.size > MAX_VERDICTS) map.delete(map.keys().next().value)
    },
    take(exec) {
      const reason = map.get(exec?.callId)
      map.delete(exec?.callId)
      return reason
    },
  }
}

export async function scopeCheck(ctx, config, agent, info, taskId, signal) {
  const argv = [config.python, path.join(config.tools, 'scope_check.py'), info.root, '--json']
  if (taskId) argv.push('--task', taskId)
  if (info.state.role === 'lead') argv.push('--allow-board')
  const result = await run(ctx, agent, argv, { cwd: info.root, timeoutMs: 60_000, signal })
  try {
    return JSON.parse(result.stdout.trim().split('\n').pop())
  } catch {
    return { ok: false, error: (result.stderr || result.stdout || `exit ${result.code}`).trim().slice(0, 500) }
  }
}

/** Before a worker's turn ends: compare the git diff with the scope (catches writes through bash). */
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
    for (const item of foreign.slice(0, 20)) lines.push(`- foreign changes (task ${item.task}, harness ${item.harness}): ${item.path}`)
  }
  agent.steer(message([
    `Polier: the working tree has changes outside the scope of ${task.id}.`,
    ...lines,
    `Allowed: ${(task.scope_write ?? []).join(', ') || 'nothing'}.`,
    'Undo these changes (git checkout/rm for files you created or edited), or, if they are needed,',
    'keep them and report each one under open_questions in your result. Then finish.',
  ].join('\n')))
}

/**
 * Before every tool call: check a write against scope and policy, deny a
 * policy-denied command, refresh the claim heartbeat and warn once per turn
 * when a bash command stops processes.
 */
export async function onToolPreExecute(ctx, config, exec, next, store) {
  const agent = exec.agent
  if (agent && config.enforce !== 'off') {
    const reason = await checkWrite(ctx, config, exec)
    if (reason) {
      if (config.enforce === 'ask') return { kind: 'ask', reason }
      store?.put(exec, reason)
      return { kind: 'deny', reason }
    }
  }
  try {
    if (agent) {
      const command = commandOf(exec)
      let kills = false
      if (command.trim() && config.enforce !== 'off') {
        const info = context(ctx, agent)
        if (info && info.state.role !== 'off') {
          const answer = await ask(ctx, config, agent, info, { command })
          if (answer.deny) {
            store?.put(exec, answer.deny)
            return { kind: 'deny', reason: answer.deny }
          }
          kills = answer.kills === true
        }
      }
      await beatClaims(ctx, config, agent)
      if (kills) {
        const state = stateOf(agent)
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
  } catch { /* never block a command on our own error */ }
  return next()
}
