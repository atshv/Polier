// Polier for DeepSeek Harness: an AI software factory inside the agent loop.
//
// What it adds, with no command to type:
// - a live <polier> block in every step's runtime context (station, open items,
//   running task and scope, ready tasks, pending approvals, the next move) and
//   a short guide in the system prompt of sessions inside a Polier project;
// - the guard: a worker writes only inside its task's scope, policy.json
//   protects paths, manifests and commands, and a stop check compares the git
//   diff with the scope before a turn ends;
// - tools: pl_status, pl_gate, pl_scope_check, pl_check, pl_next, pl_state,
//   pl_factory, pl_mode, pl_task, pl_approval — human decisions are harness
//   approval prompts, never chat;
// - the Polier skill, with its files resolved inside this package.
//
// No build step and no static imports of harness packages: every service is
// looked up when it exists, so a missing optional service degrades instead of
// breaking the harness boot.

import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { GUIDE, guideText, liveContext } from './lib/context.mjs'
import { checkWrite, onToolPreExecute, onTurnStopping } from './lib/guard.mjs'
import { findProject } from './lib/project.mjs'
import { agentCwd } from './lib/run.mjs'
import { clearSessions, forget, releaseClaim, stateOf } from './lib/session.mjs'
import { tools } from './lib/tools.mjs'

export const name = 'polier'
export { checkWrite, GUIDE, liveContext, onTurnStopping }

const PACKAGE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')

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
  /** Name written into records the owner decides through an approval prompt. */
  owner: 'owner',
  /** Show the live <polier> block and the guide to the model. */
  context: true,
  /** Register the bundled Polier skill. */
  skill: true,
}

/** Merge the row's config with defaults; unknown keys are ignored. */
export function resolveConfig(config = {}) {
  const out = { ...DEFAULTS, package: PACKAGE, tools: path.join(PACKAGE, 'tools') }
  if (['deny', 'ask', 'off'].includes(config.enforce)) out.enforce = config.enforce
  if (config.guardedTools && typeof config.guardedTools === 'object') out.guardedTools = { ...config.guardedTools }
  if (typeof config.stopCheck === 'boolean') out.stopCheck = config.stopCheck
  if (Number.isInteger(config.maxStopReminders) && config.maxStopReminders >= 0) out.maxStopReminders = config.maxStopReminders
  if (typeof config.python === 'string' && config.python) out.python = config.python
  if (typeof config.owner === 'string' && config.owner.trim()) out.owner = config.owner.trim()
  if (typeof config.context === 'boolean') out.context = config.context
  if (typeof config.skill === 'boolean') out.skill = config.skill
  return out
}

/** The bundled skill: SKILL.md with its folder as resource base. */
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
      meta[key] += ` ${line.trim()}`
    }
  }
  return {
    name: meta.name,
    description: meta.description,
    content: `${text.slice(m[0].length)}\n\n> Package folder: \`${PACKAGE}\`. Paths such as \`prompt/generator.md\` and \`tools/check.py\` are relative to it.\n`,
    path: file,
    source: 'bundled',
    resourceBase: { kind: 'directory', path: PACKAGE },
  }
}

function warn(ctx, text) {
  try {
    const logger = ctx.logger?.('polier')
    if (logger && typeof logger.warn === 'function') return logger.warn(text)
  } catch { /* fall through */ }
  console.warn(`[polier] ${text}`)
}

/** Release the claims a disposed session still holds (best effort). */
async function onAgentDisposed(ctx, config, agent) {
  if (!agent?.id) return
  const state = forget(agent.id)
  if (!state?.claims?.length) return
  const root = findProject(agentCwd(ctx, agent))
  if (!root) return
  for (const task of state.claims) await releaseClaim(ctx, config, agent, root, task, agent.id)
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

  if (config.context) {
    ctx.inject(['systemPrompt'], (c) => {
      c.systemPrompt.section({ name: 'polier:guide', order: 2950, interpolate: false, text: (assembly) => guideText(c, assembly?.agent) })
      c.systemPrompt.context({ name: 'polier:state', order: 130, interpolate: false, text: (assembly) => liveContext(c, config, assembly?.agent) })
    })
  }

  if (config.skill) {
    ctx.inject(['skills'], (c) => {
      try {
        c.skills.register(skill())
      } catch (error) {
        warn(c, `skill not registered: ${String(error)}`)
      }
    })
  }

  ctx.on('agent/turn-stopping', (payload) => {
    const agent = payload?.agent
    if (agent?.id && Number.isInteger(payload.turn)) stateOf(agent).turn = payload.turn
    return onTurnStopping(ctx, config, payload)
  })
  ctx.on('agent/disposed', (payload) => {
    onAgentDisposed(ctx, config, payload?.agent).catch(() => {})
  })
  ctx.effect(() => () => clearSessions())
}
