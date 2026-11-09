// What the model sees without asking: a live <polier> snapshot in the runtime
// context of every step, and a short guide in the system prompt of sessions
// inside a Polier project. Both are empty outside a project, so other work in
// the harness is not affected.

import { factoryView } from './factory.mjs'
import { enabled as policyEnabled, limits, loadPolicy, pendingApprovals } from './policy.mjs'
import { activeTasks, findProject, loadBoard, readyTasks } from './project.mjs'
import { agentCwd } from './run.mjs'
import { stateOf } from './session.mjs'

function list(values, max = 6) {
  const shown = values.slice(0, max).join('; ')
  return values.length > max ? `${shown}; … (${values.length - max} more)` : shown
}

/** The next sensible move, so the human never has to name a command. */
function hint({ view, board, state, running, ready, pending }) {
  if (pending.length > 0) return `${pending.length} approval(s) wait for the owner: pl_approval asks again, pl_status lists them.`
  if (view && view.current && (!board || ['idea', 'concept', 'design', 'architecture', 'plan'].includes(view.current))) {
    if (view.open.length === 0) return `Every item of station ${view.current} is resolved: ask the owner to close it (pl_factory advance shows the approval prompt).`
    return `Work on station ${view.current}: produce the outputs, then record each item with pl_factory (done with evidence, na or defer with a reason).`
  }
  if (!board) return 'No board yet: follow the Polier skill (prompt/generator.md) from the idea station.'
  if (state.role === 'worker' && running.length === 1) return `Work only inside the scope of ${running[0].id}; prove it with pl_gate, check with pl_scope_check, report to the lead.`
  if (state.role === 'reviewer') return 'Review only: read the diff, the brief and the gate records, write reviews/<ID>.md, change no code.'
  if (running.length === 0 && ready.length > 0) return `Next task: ${ready[0].id}. The lead starts it with pl_state (in_progress); a worker binds it with pl_task.`
  if (view?.current === 'build' || view?.current === 'verify') return 'Done tasks unlock their linked factory items: record them with pl_factory done.'
  return 'pl_next shows the dispatch plan.'
}

/** The live snapshot for one agent, or '' outside a Polier project. */
export function liveContext(ctx, config, agent) {
  if (!agent) return ''
  const cwd = agentCwd(ctx, agent)
  const root = findProject(cwd)
  if (!root) return ''
  const state = stateOf(agent)
  const board = loadBoard(root)
  let view
  try {
    view = factoryView(root, config.package)
  } catch {
    view = undefined
  }
  const running = board ? activeTasks(board, { root, cwd, pinned: state.pinned }).tasks : []
  const ready = board ? readyTasks(board) : []
  const policy = board ? loadPolicy(root) : undefined
  const pending = policy && policyEnabled(policy) ? pendingApprovals(root) : []
  const lines = [
    '<polier>',
    `Project: ${board?.project ?? '(no board yet)'} · root ${root} · mode ${state.role} · guard ${config.enforce}${state.pinned ? ` · bound to ${state.pinned}` : ''}`,
  ]
  const role = state.specialist
  if (role) lines.push(`Role: ${role.title}${role.name ? ` (${role.name})` : ''} · ${role.focus}`)
  if (view) {
    if (view.current) {
      const open = view.open.map((item) => `${item.id} ${item.title}`)
      lines.push(`Factory: station ${view.current} (${view.index}/${view.total}, ${view.station?.role}) · ${view.resolved}/${view.count} items resolved · platforms ${view.platforms.join(', ')}`)
      if (open.length) lines.push(`Open items: ${list(open)}`)
    } else {
      lines.push(`Factory: every station is closed · ${view.resolved}/${view.count} items resolved`)
    }
  }
  if (board) {
    for (const task of running.slice(0, 3)) {
      lines.push(`Running: ${task.id} ${task.title ?? ''}${task.role ? ` [${task.role}]` : ''} · scope ${(task.scope_write ?? []).join(', ') || 'none'} · gates ${(task.gates ?? []).join(', ') || 'none'}`)
    }
    if (ready.length) lines.push(`Ready: ${list(ready.map((t) => t.id), 8)}`)
    if (policy && policyEnabled(policy)) {
      const limit = limits(policy)
      lines.push(`Policy: attempts ${limit.max_attempts_per_task}, in progress ${limit.max_in_progress}, review rounds ${limit.max_review_rounds}${pending.length ? ` · pending approvals ${pending.map((p) => `${p.id} ${p.action}`).join(', ')}` : ''}`)
    }
  }
  lines.push(`Next: ${hint({ view, board, state, running, ready, pending })}`)
  lines.push('</polier>')
  return lines.join('\n')
}

export const GUIDE = `# Polier

This session is inside a Polier project: an AI software factory with nine stations (idea, concept, design, architecture, plan, build, verify, release, operate). The <polier> block in your context is the live state; read it instead of calling a status tool.

- The human speaks plainly ("weiter", "what is missing?", "build M03", "close the station"). Turn that into the matching Polier tool yourself; never ask the human to type a command.
- Records change only through tools: pl_factory (the line), pl_state (task status), pl_gate (evidence), pl_approval (approvals), pl_task (claims). Never edit factory.json, board.json, runs/ or reviews/approvals/ by hand. STATUS.md and docs/factory.md regenerate on their own.
- Human decisions are approval prompts, not chat: pl_mode lead, pl_factory advance and pl_approval open a prompt the owner answers. A "yes" in the chat is not an approval; call the tool.
- Evidence, not ticks: an item is done with a project file (optionally #heading) or with linked tasks that are done; must items are never deferred. A task is done with recorded gates, a passing review and a handoff.
- A whole station is long work: when goal tools exist and the human asks for it, create a goal such as "Close Polier station design: resolve every open item with evidence"; the <polier> block shows what is left each round.
- Specialists: a task names its role (frontend-builder, backend-builder, reviewer …). Delegate it to a fresh subagent whose first steps are pl_role with that role and pl_task with the task; pick the model strength the role suggests when the subagent tool lets you. A role only narrows what a session may do.
- Independent review: a fresh subagent in the reviewer role that sees only the brief, the diff and the gate records and writes reviews/<ID>.md.
- A Ralph or subagent report is a claim, not evidence: gates go through pl_gate and status through pl_state.`

/** The instructions of the session's role, '' without one. */
export function roleText(agent) {
  const role = agent ? stateOf(agent).specialist : undefined
  if (!role?.instructions) return ''
  return `# Your Polier role: ${role.title}${role.name ? ` (${role.name})` : ''}\n\n${role.instructions}`
}

/** The guide for sessions inside a Polier project, '' elsewhere. */
export function guideText(ctx, agent) {
  if (!agent) return ''
  return findProject(agentCwd(ctx, agent)) ? GUIDE : ''
}
