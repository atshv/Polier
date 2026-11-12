#!/usr/bin/env node
// Polier for Claude Code: the hooks. One process per event, called as
//   node claude/hook.mjs <SessionStart|UserPromptSubmit|SubagentStart|PreToolUse|Stop|SubagentStop>
// with the hook input on stdin. Outside a Polier project every event answers
// nothing, so other work in Claude Code is not affected.
//
// - SessionStart, SubagentStart: the guide and the live <polier> block.
// - UserPromptSubmit: the live <polier> block.
// - PreToolUse: notes who makes a pl_* call (the server reads it), asks
//   tools/guard.py before a write or a Bash command, warns once per prompt when
//   a command stops processes.
// - Stop, SubagentStop: the stop check, git diff against the worker's scope;
//   a subagent that finishes releases its claims.

import { checkCommand, checkWrite, stopReminder } from '../plugin/lib/guard.mjs'
import { liveContext } from '../plugin/lib/context.mjs'
import { findProject } from '../plugin/lib/project.mjs'
import { releaseClaim, stateOf } from '../plugin/lib/session.mjs'
import {
  agentOf, configFromEnv, counter, fetchState, GUIDE, hostContext, POLIER_TOOL, rememberCall, sessionKey,
} from './lib/host.mjs'

const KILL_WARNING = "Polier: do not stop processes you did not start; use your slot's ports."

async function readInput() {
  let text = ''
  for await (const chunk of process.stdin) text += chunk
  try {
    const value = JSON.parse(text || '{}')
    return value && typeof value === 'object' ? value : {}
  } catch {
    return {}
  }
}

/** The session this event belongs to, with the state the MCP server holds for it. */
async function session(input) {
  const key = sessionKey(input.session_id, input.agent_id)
  const agent = agentOf(key, input.cwd || process.env.CLAUDE_PROJECT_DIR || process.cwd())
  const remote = await fetchState(input.session_id, key)
  if (remote && typeof remote === 'object') Object.assign(stateOf(agent), remote)
  return { key, agent }
}

function context(event, text) {
  return text ? { hookSpecificOutput: { hookEventName: event, additionalContext: text } } : undefined
}

function decision(kind, reason, extra) {
  return { hookSpecificOutput: { hookEventName: 'PreToolUse', permissionDecision: kind, permissionDecisionReason: reason, ...extra } }
}

async function preToolUse(input, config, ctx) {
  const name = String(input.tool_name ?? '')
  if (POLIER_TOOL.test(name)) {
    rememberCall(input.tool_use_id, { session: input.session_id, agent: input.agent_id, cwd: input.cwd })
    return undefined
  }
  if (config.enforce === 'off') return undefined
  const shell = config.commandTools.includes(name)
  if (!config.guardedTools[name] && !shell) return undefined
  if (!findProject(input.cwd || process.cwd())) return undefined
  const { key, agent } = await session(input)
  const exec = { name, arguments: input.tool_input ?? {}, agent, callId: input.tool_use_id }
  if (!shell) {
    const reason = await checkWrite(ctx, config, exec)
    return reason ? decision(config.enforce === 'ask' ? 'ask' : 'deny', reason) : undefined
  }
  const { deny, kills } = await checkCommand(ctx, config, exec)
  if (deny) return decision('deny', deny)
  if (!kills) return undefined
  const warned = counter('kill', key)
  if (warned.read().prompt === input.prompt_id) return undefined
  warned.write({ prompt: input.prompt_id })
  return context('PreToolUse', KILL_WARNING)
}

/**
 * Block the end of a worker's turn while its tree has changes outside the
 * scope, a few times at most. A subagent that finishes gives its claims back.
 */
async function stop(input, config, ctx) {
  const root = findProject(input.cwd || process.cwd())
  if (!root) return undefined
  const { key, agent } = await session(input)
  if (config.stopCheck) {
    const reminders = counter('stop', key)
    const count = input.stop_hook_active ? Number(reminders.read().count) || 0 : 0
    if (count < config.maxStopReminders) {
      const text = await stopReminder(ctx, config, agent)
      reminders.write({ count: text ? count + 1 : 0 })
      if (text) return { decision: 'block', reason: text }
    }
  }
  if (input.agent_id) for (const task of stateOf(agent).claims ?? []) await releaseClaim(ctx, config, agent, root, task)
  return undefined
}

async function live(event, input, config, ctx, guide) {
  if (!config.context || !findProject(input.cwd || process.cwd())) return undefined
  const { agent } = await session(input)
  const block = liveContext(ctx, config, agent)
  const role = /^polier:([a-z][a-z0-9-]*)$/.exec(String(input.agent_type ?? ''))?.[1]
  const first = role ? `\n\nYou are the Polier ${role} subagent: call pl_role with role ${role}, then pl_task with your task ID, before anything else.` : ''
  return context(event, [guide ? GUIDE : '', block].filter(Boolean).join('\n\n') + first)
}

const HANDLERS = {
  SessionStart: (input, config, ctx) => live('SessionStart', input, config, ctx, true),
  SubagentStart: (input, config, ctx) => live('SubagentStart', input, config, ctx, true),
  UserPromptSubmit: (input, config, ctx) => live('UserPromptSubmit', input, config, ctx, false),
  PreToolUse: preToolUse,
  Stop: stop,
  SubagentStop: stop,
}

async function main() {
  const event = process.argv[2]
  const input = await readInput()
  const handler = HANDLERS[event ?? input.hook_event_name]
  if (!handler) return
  const output = await handler(input, configFromEnv(), hostContext(undefined))
  if (output) process.stdout.write(`${JSON.stringify(output)}\n`)
}

main().catch((error) => {
  // A hook error must not stop Claude Code; a write the guard cannot decide is already denied above.
  process.stderr.write(`polier hook: ${String(error?.message ?? error)}\n`)
})
