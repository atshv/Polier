// The Claude Code adapter as Claude Code runs it: the MCP server as a child
// process spoken to over stdio, every hook as its own process with the hook
// input on stdin, on throwaway git projects. The owner's dialog is the MCP
// elicitation request the server sends; the test answers it as the owner.
import assert from 'node:assert/strict'
import { spawn, spawnSync } from 'node:child_process'
import { existsSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import readline from 'node:readline'
import test from 'node:test'

import { PACKAGE, PY, git, project, task } from '../../plugin/test/harness.mjs'

const SERVER = path.join(PACKAGE, 'claude', 'server.mjs')
const HOOK = path.join(PACKAGE, 'claude', 'hook.mjs')
const RUNTIME = mkdtempSync(path.join(tmpdir(), 'pl-cc-run-'))
const TOOL = (name) => `mcp__plugin_polier_polier__${name}`

let seq = 0
const env = (extra = {}) => ({ ...process.env, POLIER_PYTHON: PY, POLIER_RUNTIME_DIR: RUNTIME, ...extra })

/** A Claude Code stand-in: initialize, list and call tools, answer elicitation with queued answers. */
async function connect(root, { elicitation = true, answers = [] } = {}) {
  const session = `s-${process.pid}-${++seq}`
  const child = spawn(process.execPath, [SERVER], {
    cwd: root, env: env({ CLAUDE_CODE_SESSION_ID: session, CLAUDE_PROJECT_DIR: root }), stdio: ['pipe', 'pipe', 'inherit'],
  })
  const waiting = new Map()
  const asked = []
  let id = 0
  readline.createInterface({ input: child.stdout }).on('line', (line) => {
    const msg = JSON.parse(line)
    if (msg.method === 'elicitation/create') {
      asked.push(msg.params.message)
      const answer = answers.length ? answers.shift() : { action: 'decline' }
      child.stdin.write(`${JSON.stringify({ jsonrpc: '2.0', id: msg.id, result: answer })}\n`)
    } else if (waiting.has(msg.id)) {
      waiting.get(msg.id)(msg)
      waiting.delete(msg.id)
    }
  })
  const rpc = (method, params) => new Promise((resolve) => {
    const n = ++id
    waiting.set(n, resolve)
    child.stdin.write(`${JSON.stringify({ jsonrpc: '2.0', id: n, method, params })}\n`)
  })
  const init = await rpc('initialize', {
    protocolVersion: '2025-11-25', clientInfo: { name: 'test', version: '1' },
    capabilities: elicitation ? { elicitation: { form: {} } } : {},
  })
  child.stdin.write(`${JSON.stringify({ jsonrpc: '2.0', method: 'notifications/initialized' })}\n`)
  return {
    session, asked, init, rpc,
    /** A pl_* call the way Claude Code makes it: PreToolUse hook first, then tools/call with the tool use id. */
    async call(name, args = {}, { agent } = {}) {
      const useId = `toolu_${++seq}`
      hook('PreToolUse', { session_id: session, agent_id: agent, cwd: root, tool_name: TOOL(name), tool_input: args, tool_use_id: useId })
      const msg = await rpc('tools/call', { name, arguments: args, _meta: { 'claudecode/toolUseId': useId } })
      const text = msg.result.content.map((b) => b.text).join('')
      let value
      try { value = JSON.parse(text) } catch { value = text }
      return { error: msg.result.isError, value }
    },
    close() {
      return new Promise((resolve) => {
        child.on('exit', resolve)
        child.stdin.end()
      })
    },
  }
}

function hook(event, input, extra = {}) {
  const ran = spawnSync(process.execPath, [HOOK, event], { input: JSON.stringify({ hook_event_name: event, ...input }), env: env(extra), encoding: 'utf8' })
  assert.equal(ran.status, 0, ran.stderr)
  return ran.stdout.trim() ? JSON.parse(ran.stdout) : undefined
}

const write = (cc, root, file, agent) => hook('PreToolUse', {
  session_id: cc.session, agent_id: agent, cwd: root, tool_name: 'Write', tool_input: { file_path: path.join(root, file), content: 'x' }, tool_use_id: `toolu_w${++seq}`,
})

test('the server lists every pl_* tool with its schema', async () => {
  const root = project([task()])
  const cc = await connect(root)
  try {
    assert.equal(cc.init.result.serverInfo.name, 'polier')
    const { result } = await cc.rpc('tools/list')
    const names = result.tools.map((t) => t.name)
    for (const name of ['pl_preflight', 'pl_status', 'pl_gate', 'pl_factory', 'pl_mode', 'pl_role', 'pl_task', 'pl_approval']) assert.ok(names.includes(name), name)
    for (const tool of result.tools) assert.equal(tool.inputSchema.type, 'object')
    assert.ok(result.tools.find((t) => t.name === 'pl_status').annotations.readOnlyHint)
  } finally {
    await cc.close()
  }
})

test('outside a Polier project every hook stays silent', () => {
  const root = mkdtempSync(path.join(tmpdir(), 'pl-cc-empty-'))
  for (const event of ['SessionStart', 'UserPromptSubmit', 'SubagentStart', 'Stop']) {
    assert.equal(hook(event, { session_id: 'x', cwd: root }), undefined, event)
  }
  assert.equal(hook('PreToolUse', { session_id: 'x', cwd: root, tool_name: 'Write', tool_input: { file_path: path.join(root, 'a.txt') } }), undefined)
  assert.equal(hook('PreToolUse', { session_id: 'x', cwd: root, tool_name: 'Bash', tool_input: { command: 'git push' } }), undefined)
})

test('inside a project the session starts with the guide and every prompt carries the live block', () => {
  const root = project([task('M01', 'pending')])
  const start = hook('SessionStart', { session_id: 'x', cwd: root })
  assert.match(start.hookSpecificOutput.additionalContext, /# Polier/)
  assert.match(start.hookSpecificOutput.additionalContext, /<polier>/)
  const prompt = hook('UserPromptSubmit', { session_id: 'x', cwd: root, prompt: 'weiter' })
  assert.equal(prompt.hookSpecificOutput.hookEventName, 'UserPromptSubmit')
  assert.match(prompt.hookSpecificOutput.additionalContext, /Ready: M01/)
  assert.doesNotMatch(prompt.hookSpecificOutput.additionalContext, /# Polier\n/)
  const sub = hook('SubagentStart', { session_id: 'x', agent_id: 'a1', agent_type: 'polier:backend-builder', cwd: root })
  assert.match(sub.hookSpecificOutput.additionalContext, /call pl_role with role backend-builder/)
  assert.equal(hook('UserPromptSubmit', { session_id: 'x', cwd: root }, { POLIER_CONTEXT: 'false' }), undefined)
})

test('a worker writes inside its scope only; ask mode turns the denial into a permission prompt', () => {
  const root = project([task()])
  const cc = { session: 'w1' }
  assert.equal(write(cc, root, 'src/app.py'), undefined)
  const denied = write(cc, root, 'README.md')
  assert.equal(denied.hookSpecificOutput.permissionDecision, 'deny')
  assert.match(denied.hookSpecificOutput.permissionDecisionReason, /README\.md/)
  const asked = hook('PreToolUse', { session_id: 'w1', cwd: root, tool_name: 'Edit', tool_input: { file_path: path.join(root, 'README.md') } }, { POLIER_ENFORCE: 'ask' })
  assert.equal(asked.hookSpecificOutput.permissionDecision, 'ask')
  assert.equal(hook('PreToolUse', { session_id: 'w1', cwd: root, tool_name: 'Write', tool_input: { file_path: path.join(root, 'README.md') } }, { POLIER_ENFORCE: 'off' }), undefined)
})

test('a command the policy denies is refused; a kill is warned about once per prompt', () => {
  const root = project([task()], { files: { 'policy.json': readFileSync(path.join(PACKAGE, 'templates', 'policy.json'), 'utf8') } })
  const bash = (command, prompt) => hook('PreToolUse', { session_id: 'b1', prompt_id: prompt, cwd: root, tool_name: 'Bash', tool_input: { command } })
  assert.equal(bash('git push origin main', 'p1').hookSpecificOutput.permissionDecision, 'deny')
  assert.equal(bash('ls', 'p1'), undefined)
  const warned = bash('pkill node', 'p1')
  assert.match(warned.hookSpecificOutput.additionalContext, /do not stop processes/)
  assert.equal(warned.hookSpecificOutput.permissionDecision, undefined)
  assert.equal(bash('pkill node', 'p1'), undefined)
  assert.ok(bash('pkill node', 'p2'))
})

test('lead mode needs the owner: approve in the dialog widens the session, a subagent stays a worker', async () => {
  const root = project([task()])
  const cc = await connect(root, { answers: [{ action: 'accept', content: { decision: 'reject' } }, { action: 'accept', content: { decision: 'approve' } }] })
  try {
    const refused = await cc.call('pl_mode', { role: 'lead', reason: 'plan the next stage' })
    assert.equal(refused.value.ok, false)
    assert.equal(refused.value.approval, 'rejected')
    assert.match(cc.asked[0], /Polier lead/)
    assert.equal(write(cc, root, 'README.md').hookSpecificOutput.permissionDecision, 'deny')
    const granted = await cc.call('pl_mode', { role: 'lead', reason: 'plan the next stage' })
    assert.equal(granted.value.ok, true)
    assert.equal(write(cc, root, 'README.md'), undefined)
    assert.equal(write(cc, root, 'README.md', 'agent-7').hookSpecificOutput.permissionDecision, 'deny')
    const status = await cc.call('pl_status', {}, { agent: 'agent-7' })
    assert.equal(status.value.role, 'worker')
  } finally {
    await cc.close()
  }
})

test('without an elicitation dialog every owner decision fails closed', async () => {
  const root = mkdtempSync(path.join(tmpdir(), 'pl-cc-init-'))
  writeFileSync(path.join(root, 'project-input.md'), '# Input\n')
  const cc = await connect(root, { elicitation: false })
  try {
    const init = await cc.call('pl_factory', { action: 'init', platforms: ['cli'] })
    assert.equal(init.value.ok, false)
    assert.equal(init.value.approval, 'unavailable')
    assert.equal(existsSync(path.join(root, 'factory.json')), false)
    const pre = await cc.call('pl_preflight')
    const dialog = pre.value.checks.find((c) => c.check === 'owner dialogs')
    assert.equal(dialog.level, 'warn')
    assert.equal(pre.value.checks.find((c) => c.check === 'hooks').level, 'ok')
  } finally {
    await cc.close()
  }
})

test('the owner starts the line in a dialog and the record names Claude Code', async () => {
  const root = mkdtempSync(path.join(tmpdir(), 'pl-cc-line-'))
  writeFileSync(path.join(root, 'project-input.md'), '# Input\n')
  const cc = await connect(root, { answers: [{ action: 'accept', content: { decision: 'approve' } }] })
  try {
    const init = await cc.call('pl_factory', { action: 'init', platforms: ['cli'] })
    assert.equal(init.value.ok, true, JSON.stringify(init.value))
    assert.match(cc.asked[0], /Start the Polier line/)
    const line = JSON.parse(readFileSync(path.join(root, 'factory.json'), 'utf8'))
    assert.match(JSON.stringify(line), /owner \(approved in Claude Code\)/)
    assert.ok(init.value.remaining.length > 0)
  } finally {
    await cc.close()
  }
})

test('a bound task is claimed for Claude Code, its role instructions come back, and the claim ends with the session', async () => {
  const root = project([task('M01', 'in_progress', { role: 'backend-builder' })])
  const cc = await connect(root)
  try {
    const bound = await cc.call('pl_task', { task: 'M01' }, { agent: 'sub-1' })
    assert.equal(bound.value.ok, true, JSON.stringify(bound.value))
    assert.equal(bound.value.role, 'backend-builder')
    assert.match(bound.value.instructions, /\S/)
    const claims = JSON.parse(spawnSync(PY, [path.join(PACKAGE, 'tools', 'claim.py'), 'list', '--root', root, '--json'], { encoding: 'utf8' }).stdout)
    assert.equal(claims[0].harness, 'claude-code')
    assert.equal(claims[0].session, `${cc.session}:sub-1`)
  } finally {
    await cc.close()
  }
  const after = JSON.parse(spawnSync(PY, [path.join(PACKAGE, 'tools', 'claim.py'), 'list', '--root', root, '--json'], { encoding: 'utf8' }).stdout)
  assert.deepEqual(after, [])
})

test('the stop check holds a worker back while its tree has changes outside the scope', () => {
  const root = project([task()])
  writeFileSync(path.join(root, 'README.md'), 'changed by bash\n')
  const first = hook('Stop', { session_id: 'st', cwd: root, stop_hook_active: false })
  assert.equal(first.decision, 'block')
  assert.match(first.reason, /README\.md/)
  assert.equal(hook('Stop', { session_id: 'st', cwd: root, stop_hook_active: true }).decision, 'block')
  assert.equal(hook('Stop', { session_id: 'st', cwd: root, stop_hook_active: true }), undefined)
  assert.equal(hook('SubagentStop', { session_id: 'st', agent_id: 'w', cwd: root, stop_hook_active: false }).decision, 'block')
  git(root, 'checkout', 'README.md')
  assert.equal(hook('Stop', { session_id: 'st', cwd: root, stop_hook_active: false }), undefined)
  assert.equal(hook('Stop', { session_id: 'st2', cwd: root, stop_hook_active: false }, { POLIER_STOP_CHECK: 'false' }), undefined)
})

test('the plugin manifest matches the package', () => {
  const manifest = JSON.parse(readFileSync(path.join(PACKAGE, '.claude-plugin', 'plugin.json'), 'utf8'))
  assert.equal(manifest.version, readFileSync(path.join(PACKAGE, 'VERSION'), 'utf8').trim())
  for (const file of [...manifest.agents, manifest.hooks, manifest.icon]) assert.ok(existsSync(path.join(PACKAGE, file)), file)
  const roles = JSON.parse(readFileSync(path.join(PACKAGE, 'roles', 'roles.json'), 'utf8')).roles.map((r) => `./claude/agents/${r.id}.md`)
  assert.deepEqual(manifest.agents, roles)
  const hooks = JSON.parse(readFileSync(path.join(PACKAGE, 'claude', 'hooks.json'), 'utf8')).hooks
  const matcher = new RegExp(hooks.PreToolUse[0].matcher)
  for (const name of ['Write', 'Edit', 'MultiEdit', 'NotebookEdit', 'Bash', TOOL('pl_gate'), 'mcp__polier__pl_gate']) assert.ok(matcher.test(name), name)
  for (const name of ['Read', 'Grep', 'mcp__other__pl_gate']) assert.equal(matcher.test(name), false, name)
})
