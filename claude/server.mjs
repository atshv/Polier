#!/usr/bin/env node
// Polier for Claude Code: the pl_* tools as a stdio MCP server.
//
// The tools are the plugin library's (plugin/lib/tools.mjs), so every rule and
// every write still goes through tools/*.py. What this file adds:
// - JSON-RPC over stdio (MCP), with no dependency;
// - owner decisions as MCP elicitation: Claude Code shows the owner a dialog,
//   the model never sees an answer it could give itself;
// - session state in memory, one entry per Claude Code session and subagent,
//   which the hooks read over a local socket (read-only);
// - claim heartbeats while the session lives, released when it ends.

import { execFileSync } from 'node:child_process'
import { existsSync, readFileSync, rmSync } from 'node:fs'
import net from 'node:net'
import path from 'node:path'
import readline from 'node:readline'

import { findProject } from '../plugin/lib/project.mjs'
import { beatClaims, stateOf } from '../plugin/lib/session.mjs'
import { tools } from '../plugin/lib/tools.mjs'
import { agentOf, configFromEnv, hostContext, recallCall, sessionKey, snapshot, socketPath } from './lib/host.mjs'

const PROTOCOLS = ['2025-11-25', '2025-06-18', '2025-03-26', '2024-11-05']
const READ_ONLY = new Set(['pl_preflight', 'pl_status', 'pl_scope_check', 'pl_review', 'pl_next'])
const HEARTBEAT_MS = 60_000

const config = configFromEnv()
const VERSION = readFileSync(path.join(config.package, 'VERSION'), 'utf8').trim()
let client = { capabilities: {} }
let nextId = 0
const outgoing = new Map()
const running = new Map()
const sessions = new Map()
const sockets = new Map()

function send(message) {
  process.stdout.write(`${JSON.stringify({ jsonrpc: '2.0', ...message })}\n`)
}

function request(method, params, signal) {
  const id = `polier-${++nextId}`
  return new Promise((resolve, reject) => {
    const abort = () => {
      outgoing.delete(id)
      reject(new Error('cancelled'))
    }
    if (signal?.aborted) return abort()
    signal?.addEventListener('abort', abort, { once: true })
    outgoing.set(id, { resolve, reject })
    send({ id, method, params })
  })
}

/** The owner's dialog: MCP elicitation, answered by the person at the terminal. */
const elicitation = {
  async request({ reason, signal }) {
    try {
      const answer = await request('elicitation/create', {
        mode: 'form',
        message: `Polier asks the owner:\n\n${reason}`,
        requestedSchema: {
          type: 'object',
          properties: { decision: { type: 'string', title: 'Decision', enum: ['approve', 'reject'] } },
          required: ['decision'],
        },
      }, signal)
      if (answer?.action === 'accept') return answer.content?.decision === 'approve' ? 'allowed-once' : 'rejected'
      return answer?.action === 'decline' ? 'rejected' : 'cancelled'
    } catch {
      return signal?.aborted ? 'cancelled' : 'unavailable'
    }
  },
}

function approvalService() {
  return client.capabilities?.elicitation ? elicitation : undefined
}

const ctx = { get: (name) => hostContext(approvalService()).get(name) }

/** The preflight checks only Claude Code can answer: the owner dialog, the hooks, CLAUDE.md. */
async function hostChecks(exec, project) {
  const checks = [
    approvalService()
      ? { check: 'owner dialogs', level: 'ok', detail: 'owner decisions open a Claude Code dialog (MCP elicitation)' }
      : { check: 'owner dialogs', level: 'warn', detail: 'this client cannot show an MCP elicitation dialog: station closes, lead mode and approvals fail closed', fix: 'run Polier in an interactive Claude Code session, or let the owner run tools/*.py with ! in the prompt' },
    exec.hooked
      ? { check: 'hooks', level: 'ok', detail: 'write guard, command guard, live context and stop check run as Claude Code hooks' }
      : { check: 'hooks', level: 'warn', detail: 'no Polier hook saw this call: the write guard, the live context and the stop check are not active', fix: 'install Polier as a plugin (/plugin marketplace add atshv/polier, then /plugin install polier@polier) instead of adding only the MCP server' },
  ]
  if (project && existsSync(path.join(project, 'AGENTS.md')) && !existsSync(path.join(project, 'CLAUDE.md'))) {
    checks.push({ check: 'CLAUDE.md', level: 'warn', detail: 'the project has AGENTS.md but no CLAUDE.md, so Claude Code does not load its rules', fix: 'add CLAUDE.md with the single line @AGENTS.md' })
  }
  return checks
}

const defs = new Map(tools(ctx, { ...config, hostChecks }).map((def) => [def.name, def]))

function listTools() {
  return [...defs.values()].map((def) => ({
    name: def.name,
    description: def.description,
    inputSchema: def.parameters ?? { type: 'object', properties: {} },
    ...(READ_ONLY.has(def.name) ? { annotations: { readOnlyHint: true } } : {}),
  }))
}

/** Serve one session's state to its hooks: read-only, one JSON line per question. */
function serve(session) {
  if (sockets.has(session)) return
  const where = socketPath(session)
  if (process.platform !== 'win32') rmSync(where, { force: true })
  const server = net.createServer((socket) => {
    let data = ''
    socket.on('error', () => {})
    socket.on('data', (chunk) => {
      data += chunk
      const end = data.indexOf('\n')
      if (end < 0) return
      let key
      try {
        key = JSON.parse(data.slice(0, end)).key
      } catch { /* answered below */ }
      socket.end(`${JSON.stringify(typeof key === 'string' ? snapshot(stateOf({ id: key })) : {})}\n`)
    })
  })
  server.on('error', () => sockets.delete(session))
  server.listen(where)
  server.unref()
  sockets.set(session, { server, where })
}

/** Role instructions join the tool result: Claude Code has no per-session system prompt section. */
function withInstructions(name, value, agent) {
  if (!['pl_role', 'pl_task'].includes(name) || !value?.ok || !value.role) return value
  const role = stateOf(agent).specialist
  return role?.instructions ? { ...value, instructions: role.instructions } : value
}

async function callTool(id, params) {
  const def = defs.get(params?.name)
  if (!def) return send({ id, error: { code: -32602, message: `unknown tool ${params?.name}` } })
  const useId = params._meta?.['claudecode/toolUseId']
  const call = recallCall(useId)
  const session = call?.session || process.env.CLAUDE_CODE_SESSION_ID || 'local'
  const key = sessionKey(session, call?.agent)
  const cwd = call?.cwd || process.env.CLAUDE_PROJECT_DIR || process.cwd()
  const agent = agentOf(key, cwd)
  sessions.set(key, agent)
  serve(session)
  const controller = new AbortController()
  running.set(id, controller)
  const args = params.arguments && typeof params.arguments === 'object' ? params.arguments : {}
  try {
    const value = withInstructions(def.name, await def.execute(args, {
      name: def.name, agent, callId: useId || `call-${id}`, signal: controller.signal, hooked: Boolean(call),
    }), agent)
    const text = def.output.render(args, value).map((block) => block.text).join('')
    send({ id, result: { content: [{ type: 'text', text }], isError: false } })
  } catch (error) {
    send({ id, result: { content: [{ type: 'text', text: String(error?.message ?? error) }], isError: true } })
  } finally {
    running.delete(id)
  }
}

function onMessage(message) {
  if (message.id !== undefined && !message.method) {
    const waiting = outgoing.get(message.id)
    if (!waiting) return
    outgoing.delete(message.id)
    if (message.error) waiting.reject(new Error(message.error.message ?? 'error'))
    else waiting.resolve(message.result)
    return
  }
  const { id, method, params } = message
  if (method === 'initialize') {
    client = { capabilities: params?.capabilities ?? {} }
    const asked = params?.protocolVersion
    return send({
      id,
      result: {
        protocolVersion: PROTOCOLS.includes(asked) ? asked : PROTOCOLS[0],
        capabilities: { tools: {} },
        serverInfo: { name: 'polier', version: VERSION },
        instructions: 'Polier, the AI software factory: the pl_* tools record the factory line, task states, gate evidence, claims and owner approvals of a Polier project. Read the polier skill before starting a project.',
      },
    })
  }
  if (method === 'notifications/cancelled') return running.get(params?.requestId)?.abort()
  if (method === 'tools/list') return send({ id, result: { tools: listTools() } })
  if (method === 'tools/call') return void callTool(id, params)
  if (method === 'ping') return send({ id, result: {} })
  if (id !== undefined) send({ id, error: { code: -32601, message: `method not found: ${method}` } })
}

/** Keep the claims of every session alive while Claude Code runs. */
const heartbeat = setInterval(() => {
  for (const agent of sessions.values()) beatClaims(ctx, config, agent).catch(() => {})
}, HEARTBEAT_MS)
heartbeat.unref()

/**
 * The session ended: release what it still claims, close the sockets. Claude
 * Code stops the server quickly, so the releases run synchronously.
 */
function shutdown() {
  clearInterval(heartbeat)
  for (const agent of sessions.values()) {
    const root = findProject(agent.session.header.cwd)
    if (!root) continue
    for (const task of stateOf(agent).claims ?? []) {
      try {
        execFileSync(config.python, [path.join(config.tools, 'claim.py'), 'release', task, '--session', agent.id, '--root', root],
          { cwd: root, timeout: 10_000, stdio: 'ignore', windowsHide: true })
      } catch { /* a stale claim expires with its TTL */ }
    }
  }
  for (const { server, where } of sockets.values()) {
    server.close()
    if (process.platform !== 'win32') rmSync(where, { force: true })
  }
  process.exit(0)
}

readline.createInterface({ input: process.stdin }).on('line', (line) => {
  if (!line.trim()) return
  let message
  try {
    message = JSON.parse(line)
  } catch {
    return send({ id: null, error: { code: -32700, message: 'parse error' } })
  }
  onMessage(message)
}).on('close', shutdown)
process.on('SIGTERM', shutdown)
process.on('SIGINT', shutdown)
