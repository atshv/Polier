// The guard: what a session may write and run, and the stop check at the end of
// a turn. Scope rules come from board.json, policy rules from policy.json; a
// project without policy.json keeps the plain scope guard.

import path from 'node:path'

import {
  approver, commandDenial, dependencyApproval, enabled as policyEnabled, hasGrant, loadPolicy,
  manifestMatch, protectedMatch,
} from './policy.mjs'
import { checkPath, inside, processKills, relative } from './project.mjs'
import { run } from './run.mjs'
import { beatClaims, context, stateOf } from './session.mjs'

const COMMAND_TOOLS = new Set(['bash'])

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

function boundTask(info) {
  return info.tasks.length === 1 ? info.tasks[0].id : undefined
}

function approvalHint(action, task, who) {
  return `If it is needed, call pl_approval with action ${action}${task ? ` and task ${task}` : ''}: the ${who} answers the prompt, then retry. Do not write it another way.`
}

function hasAnyGrant(info, action) {
  const ids = info.tasks.map((task) => task.id).filter(Boolean)
  if (ids.length === 0) return Boolean(hasGrant(info.root, action, null))
  return ids.some((id) => Boolean(hasGrant(info.root, action, id)))
}

/** The policy denial of writing `rel`; a lead session bypasses the path and dependency rules. */
function policyPathDenial(info, rel, shown) {
  const policy = loadPolicy(info.root)
  if (!policyEnabled(policy)) return undefined
  if (info.state.role === 'lead' || info.state.role === 'off') return undefined
  const protectedPattern = protectedMatch(policy, rel)
  if (protectedPattern) {
    return `Polier: write to ${shown} blocked, ${protectedPattern} is a protected path in policy.json. Only a lead session may write it: stop and report the change under open_questions instead of writing it another way.`
  }
  if (!dependencyApproval(policy)) return undefined
  const manifest = manifestMatch(policy, rel)
  if (manifest && !hasAnyGrant(info, 'new_dependency')) {
    return `Polier: write to ${shown} blocked, ${manifest} is a dependency manifest and policy.json requires a granted new_dependency approval. ${approvalHint('new_dependency', boundTask(info), approver(policy))}`
  }
  return undefined
}

/** Deny-list commands are blocked for every role; lead-only commands for workers and reviewers. */
function policyCommandDenial(config, info, command) {
  if (config.enforce === 'off' || info.state.role === 'off') return undefined
  const policy = loadPolicy(info.root)
  if (!policyEnabled(policy)) return undefined
  const denial = commandDenial(policy, command, info.state.role)
  if (!denial) return undefined
  if (denial.rule === 'deny') {
    return `Polier: command blocked, ${denial.reason}. This rule applies to every role, a lead included: do not run it another way. If the action is part of the task, stop and ask for it with pl_approval (action release${boundTask(info) ? `, task ${boundTask(info)}` : ''}) and report it under open_questions.`
  }
  return `Polier: command blocked, ${denial.reason}. A worker or reviewer reports the needed change instead of running it; the lead runs it (pl_mode lead, approved by the owner).`
}

/** A role with its own write list narrows the task scope further; evidence stays writable. */
function roleDenial(info, rel, shown) {
  const role = info.state.specialist
  const writes = Array.isArray(role?.writes) ? role.writes : []
  if (!writes.length || info.state.role !== 'worker' || info.tasks.length === 0) return undefined
  if (inside(rel, 'reviews/evidence') || writes.some((entry) => inside(rel, entry))) return undefined
  return `Polier: write to ${shown} blocked, the role ${role.title} writes only ${writes.join(', ')}. If the change is needed, report it under open_questions for the right role.`
}

/**
 * The guard decision for one tool call.
 * @returns {string|undefined} a denial reason, or undefined to allow
 */
export function checkWrite(ctx, config, exec) {
  if (config.enforce === 'off' || !exec.agent) return undefined
  const target = targetOf(exec, config.guardedTools)
  if (!target) return undefined
  const info = context(ctx, exec.agent)
  if (!info) return undefined
  const rel = relative(info.root, path.resolve(info.cwd, target))
  const shown = rel || target
  const verdict = checkPath(rel, info.tasks, info.state.role, { board: info.board, root: info.root, cwd: info.cwd })
  if (verdict.ok) return roleDenial(info, rel, shown) ?? policyPathDenial(info, rel, shown)
  if (info.state.role === 'reviewer') {
    return `Polier: write to ${shown} blocked, a reviewer session writes only under reviews/. Report the problem in the review instead of fixing it.`
  }
  const ids = info.tasks.map((t) => t.id).join(', ')
  if (verdict.code === 'worktree') {
    return `Polier: write to ${shown} blocked, ${verdict.reason} (${ids}). Do the work in the task's worktree, not in the main checkout. If the change is needed elsewhere, stop and report it under open_questions.`
  }
  const allowed = [...new Set(info.tasks.flatMap((t) => t.scope_write ?? []))].join(', ') || 'nothing'
  return `Polier: write to ${shown} blocked, the path ${verdict.reason} of ${ids}. Allowed: ${allowed}. Do not try another way to write it. If the change is needed, stop and report it under open_questions.`
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
 * Before every tool call: deny a policy-denied command, refresh the claim
 * heartbeat and warn once per turn when a bash command stops processes.
 */
export async function onToolPreExecute(ctx, config, exec, next) {
  try {
    const agent = exec.agent
    if (agent) {
      const args = exec.arguments && typeof exec.arguments === 'object' ? exec.arguments : {}
      const command = COMMAND_TOOLS.has(exec.name) && typeof args.command === 'string' ? args.command : ''
      if (command.trim()) {
        const info = context(ctx, agent)
        const reason = info && policyCommandDenial(config, info, command)
        if (reason) return { kind: 'deny', reason }
      }
      await beatClaims(ctx, config, agent)
      if (command && processKills(command).length > 0) {
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
  } catch { /* never block a tool call on our own error */ }
  return next()
}
