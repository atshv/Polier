// Shared fixtures for the plugin tests: a throwaway git project, a fake agent,
// a booted tool registry with the native executor and a scriptable approval
// service that stands in for the harness approval prompt.
import { execFileSync } from 'node:child_process'
import { mkdirSync, mkdtempSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'

import { Context } from '@deepseek-ai/cordis'
import SystemPrompt from '@deepseek-ai/dsh-system-prompt'
import * as NativeExecutor from '@deepseek-ai/dsh-tool-executor-native'
import ToolRuntime from '@deepseek-ai/dsh-tools'

import * as plugin from '../index.mjs'

export const PY = process.platform === 'win32' ? 'python' : 'python3'
export const PACKAGE = path.resolve(import.meta.dirname, '../..')

export function git(root, ...args) {
  return execFileSync('git', ['-C', root, ...args], { stdio: 'pipe' })
}

export function project(tasks, { files = {}, prefix = 'pl-dsh-' } = {}) {
  const root = mkdtempSync(path.join(tmpdir(), prefix))
  if (tasks) writeFileSync(path.join(root, 'board.json'), JSON.stringify({ project: 't', profile: 'S', base_branch: 'main', tasks }, null, 2))
  mkdirSync(path.join(root, 'src'))
  writeFileSync(path.join(root, 'src/app.py'), 'x = 1\n')
  writeFileSync(path.join(root, 'README.md'), 'readme\n')
  for (const [rel, text] of Object.entries(files)) {
    mkdirSync(path.dirname(path.join(root, rel)), { recursive: true })
    writeFileSync(path.join(root, rel), text)
  }
  git(root, 'init', '-q', '-b', 'main')
  git(root, 'config', 'user.email', 't@example.com')
  git(root, 'config', 'user.name', 't')
  git(root, 'add', '-A')
  git(root, 'commit', '-q', '-m', 'chore: scaffold')
  return root
}

export function task(id = 'M01', status = 'in_progress', extra = {}) {
  return {
    id, title: `Task ${id}`, goal: 'Do it.', status, depends_on: [], complexity: 2, stage: 1,
    scope_write: ['src/app.py'], acceptance: ['A1'], gates: ['tests'], ...extra,
  }
}

let seq = 0
export function agent(cwd) {
  const steered = []
  return { id: `agent-${++seq}`, session: { header: { cwd } }, steer: (m) => steered.push(m), steered }
}

/** An approval service whose answers come from a queue; records every question. */
export function approvals(...answers) {
  const asked = []
  return {
    asked,
    async request(req) {
      asked.push(req.reason)
      return answers.length ? answers.shift() : 'rejected'
    },
  }
}

export async function boot(config = {}, { approval } = {}) {
  const ctx = new Context()
  await ctx.plugin(SystemPrompt)
  await ctx.plugin(ToolRuntime)
  await ctx.plugin(NativeExecutor)
  if (approval) ctx.provide('approval', approval)
  await new Promise((resolve) => ctx.inject(['tools'], (c) => {
    c.tools.register({
      name: 'write',
      description: 'write a file',
      parameters: { type: 'object', properties: { file_path: { type: 'string' }, content: { type: 'string' } }, required: ['file_path', 'content'] },
      output: { schema: { type: 'string' }, render: (_a, v) => [{ type: 'text', text: v }] },
      async execute(args, exec) {
        const abs = path.resolve(exec.agent.session.header.cwd, args.file_path)
        mkdirSync(path.dirname(abs), { recursive: true })
        writeFileSync(abs, args.content)
        return 'written'
      },
    })
    c.tools.register({
      name: 'bash',
      description: 'run a shell command',
      parameters: { type: 'object', properties: { command: { type: 'string' } }, required: ['command'] },
      output: { schema: { type: 'string' }, render: (_a, v) => [{ type: 'text', text: String(v) }] },
      async execute() { return 'ran' },
    })
    resolve()
  }))
  await ctx.plugin(plugin, { python: PY, ...config })
  const tools = await new Promise((resolve) => ctx.inject(['tools'], (c) => resolve(c.tools)))
  return { ctx, tools, config: plugin.resolveConfig({ python: PY, ...config }) }
}

export async function call(tools, a, name, args) {
  const batch = await tools.execute({
    calls: [{ type: 'tool-call', id: `c${++seq}`, name, arguments: JSON.stringify(args ?? {}) }],
    agent: a,
    signal: new AbortController().signal,
  })
  const r = batch.results[0].result
  const text = r.content.map((b) => b.text).join('')
  let value
  try { value = JSON.parse(text) } catch { value = text }
  return { error: r.isError, text, value }
}

/** Switch a session's role through pl_mode; lead and off need an allowed approval in the booted service. */
export async function mode(tools, a, role) {
  return call(tools, a, 'pl_mode', { role, reason: 'test' })
}
