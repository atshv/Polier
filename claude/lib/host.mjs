// What the Claude Code adapter shares between its MCP server, its hooks and the
// status line: the configuration, the stand-ins for the harness objects the
// plugin library expects (ctx, agent), the session key, the call registry and
// the read-only state socket.
//
// Claude Code runs the MCP server once per session and every hook as a fresh
// process. Session state (mode, specialist role, bound task, claims) lives in
// the server's memory only, as in DSH: a restarted session starts as a worker
// again. Hooks read it over a local socket the server owns; nothing writes it
// but the pl_* tools.

import { createHash } from 'node:crypto'
import { mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import net from 'node:net'
import { tmpdir, userInfo } from 'node:os'
import path from 'node:path'

import { resolveConfig } from '../../plugin/index.mjs'

/** The pl_* tools as Claude Code names them: plugin server, or a server added by hand. */
export const POLIER_TOOL = /^mcp__(?:plugin_polier_)?polier__pl_/

/** The file tools Claude Code writes with, and the argument that holds the path. */
const GUARDED = { Write: 'file_path', Edit: 'file_path', MultiEdit: 'file_path', NotebookEdit: 'notebook_path' }

const OPTIONS = {
  enforce: ['POLIER_ENFORCE', 'CLAUDE_PLUGIN_OPTION_ENFORCE'],
  stopCheck: ['POLIER_STOP_CHECK', 'CLAUDE_PLUGIN_OPTION_STOP_CHECK'],
  maxStopReminders: ['POLIER_MAX_STOP_REMINDERS', 'CLAUDE_PLUGIN_OPTION_MAX_STOP_REMINDERS'],
  python: ['POLIER_PYTHON', 'CLAUDE_PLUGIN_OPTION_PYTHON'],
  owner: ['POLIER_OWNER', 'CLAUDE_PLUGIN_OPTION_OWNER'],
  context: ['POLIER_CONTEXT', 'CLAUDE_PLUGIN_OPTION_CONTEXT'],
}

function option(env, names) {
  for (const name of names) {
    const raw = env[name]
    // An option the user never set can arrive as the unexpanded placeholder.
    if (typeof raw === 'string' && raw.trim() && !raw.includes('${')) return raw.trim()
  }
  return undefined
}

function parse(key, raw) {
  if (raw === undefined) return undefined
  if (key === 'stopCheck' || key === 'context') return raw === 'true' ? true : raw === 'false' ? false : undefined
  if (key === 'maxStopReminders') return /^\d+$/.test(raw) ? Number(raw) : undefined
  return raw
}

/** The plugin configuration from the environment (MCP env block or CLAUDE_PLUGIN_OPTION_*). */
export function configFromEnv(env = process.env) {
  const raw = {}
  for (const [key, names] of Object.entries(OPTIONS)) {
    const value = parse(key, option(env, names))
    if (value !== undefined) raw[key] = value
  }
  return {
    ...resolveConfig(raw),
    guardedTools: { ...GUARDED },
    commandTools: ['Bash'],
    harness: 'claude-code',
    host: 'Claude Code',
  }
}

/** One Polier session per Claude Code session and subagent. */
export function sessionKey(session, agentId) {
  return `${session || 'local'}:${agentId || 'main'}`
}

/** The agent object the plugin library reads: an id and the working folder. */
export function agentOf(key, cwd) {
  return { id: key, session: { header: { cwd } } }
}

/** The plugin library's ctx: only the approval service exists here; gates run as plain processes. */
export function hostContext(approval) {
  return { get: (name) => (name === 'approval' ? approval : undefined) }
}

function hash(text) {
  return createHash('sha256').update(String(text)).digest('hex').slice(0, 20)
}

function user() {
  try {
    return userInfo().username.replace(/[^\w.-]/g, '_') || 'user'
  } catch {
    return 'user'
  }
}

/** A private folder for the socket, the call registry and the stop counters. */
function runtimeDir() {
  const dir = path.join(process.env.POLIER_RUNTIME_DIR || tmpdir(), `polier-claude-${user()}`)
  mkdirSync(path.join(dir, 'calls'), { recursive: true, mode: 0o700 })
  return dir
}

export function socketPath(session) {
  if (process.platform === 'win32') return `\\\\.\\pipe\\polier-claude-${user()}-${hash(session)}`
  return path.join(runtimeDir(), `${hash(session)}.sock`)
}

/** The PreToolUse hook notes who makes a pl_* call; the server reads it by the tool use id. */
export function rememberCall(toolUseId, entry) {
  if (!toolUseId) return
  writeFileSync(path.join(runtimeDir(), 'calls', `${hash(toolUseId)}.json`), JSON.stringify(entry), { mode: 0o600 })
}

export function recallCall(toolUseId) {
  if (!toolUseId) return undefined
  const file = path.join(runtimeDir(), 'calls', `${hash(toolUseId)}.json`)
  try {
    const entry = JSON.parse(readFileSync(file, 'utf8'))
    rmSync(file, { force: true })
    return entry && typeof entry === 'object' ? entry : undefined
  } catch {
    return undefined
  }
}

/** A small per-session counter file (stop reminders, kill warnings); losing it only repeats a reminder. */
export function counter(name, key) {
  const file = path.join(runtimeDir(), `${name}-${hash(key)}.json`)
  return {
    read() {
      try {
        return JSON.parse(readFileSync(file, 'utf8'))
      } catch {
        return {}
      }
    },
    write(value) {
      try {
        writeFileSync(file, JSON.stringify(value), { mode: 0o600 })
      } catch { /* advisory only */ }
    },
  }
}

/** The fields of a session's state the hooks need. */
export function snapshot(state) {
  return {
    role: state.role,
    pinned: state.pinned,
    claims: [...(state.claims ?? [])],
    specialist: state.specialist,
  }
}

/**
 * The state of one session from the server, or undefined when no server answers
 * (no pl_* call yet, or the MCP server is not running): the caller then keeps
 * the default, a worker without a bound task.
 */
export function fetchState(session, key, timeoutMs = 1500) {
  return new Promise((resolve) => {
    let done = false
    let data = ''
    const finish = (value) => {
      if (done) return
      done = true
      socket.destroy()
      resolve(value)
    }
    const socket = net.createConnection(socketPath(session))
    socket.setTimeout(timeoutMs, () => finish(undefined))
    socket.on('error', () => finish(undefined))
    socket.on('connect', () => socket.write(`${JSON.stringify({ key })}\n`))
    socket.on('data', (chunk) => {
      data += chunk
      const end = data.indexOf('\n')
      if (end < 0) return
      try {
        finish(JSON.parse(data.slice(0, end)))
      } catch {
        finish(undefined)
      }
    })
  })
}

export const GUIDE = `# Polier

This session is inside a Polier project: an AI software factory with nine stations (idea, concept, design, architecture, plan, build, verify, release, operate). The <polier> block in your context is the live state; read it instead of calling a status tool. In Claude Code the Polier tools are named mcp__plugin_polier_polier__pl_* (pl_status, pl_factory, …); load them with ToolSearch when they are deferred.

- The human speaks plainly ("weiter", "what is missing?", "build M03", "close the station"). Turn that into the matching Polier tool yourself; never ask the human to type a command.
- Records change only through tools: pl_factory (the line), pl_state (task status), pl_gate (evidence), pl_approval (approvals), pl_task (claims). Never edit factory.json, board.json, runs/ or reviews/approvals/ by hand or with Bash. STATUS.md and docs/factory.md regenerate on their own.
- Human decisions are dialogs, not chat: pl_mode lead, pl_factory init and advance and pl_approval open a Polier dialog the owner answers. A "yes" in the chat is not an approval; call the tool.
- Evidence, not ticks: an item is done with a project file (optionally #heading) or with linked tasks that are done; must items are never deferred. A task is done with recorded gates, a passing review and a handoff.
- Specialists: a task names its role (frontend-builder, backend-builder, reviewer …). Delegate it with the Agent tool to the subagent type polier:<role> (a general-purpose subagent for a role the project adds); its first calls are pl_role with that role and pl_task with the task. A role only narrows what a session may do.
- Independent review: a fresh polier:reviewer subagent gets the pl_review packet (brief, diff, gate records, earlier rounds) and writes reviews/<ID>.md; later rounds are appended and the last verdict counts.
- A task is done with pl_state done and, when other tasks depend on it, 1–3 handoff lines in the same call.
- Claude Code reads CLAUDE.md, not AGENTS.md: a Polier project keeps its rules in AGENTS.md and a CLAUDE.md with the single line @AGENTS.md (per package at profile L too).
- When something seems broken (a tool fails, a write is blocked without reason, a session resumes after a break), call pl_preflight first and fix what it lists.
- A subagent's report is a claim, not evidence: gates go through pl_gate and status through pl_state.`
