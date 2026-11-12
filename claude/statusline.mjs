#!/usr/bin/env node
// Polier for Claude Code: an optional status line. Set it in settings.json:
//   "statusLine": { "type": "command", "command": "node /path/to/polier/claude/statusline.mjs" }
// It prints one line inside a Polier project (station, open items, running
// task, mode) and nothing elsewhere. It only reads files and the session state.

import { factoryView } from '../plugin/lib/factory.mjs'
import { activeTasks, findProject, loadBoard, readyTasks } from '../plugin/lib/project.mjs'
import { configFromEnv, fetchState, sessionKey } from './lib/host.mjs'

let text = ''
for await (const chunk of process.stdin) text += chunk
let input = {}
try {
  input = JSON.parse(text || '{}')
} catch { /* nothing to show */ }

const cwd = input.workspace?.current_dir || input.cwd || process.cwd()
const root = findProject(cwd)
if (root) {
  const config = configFromEnv()
  const state = (await fetchState(input.session_id, sessionKey(input.session_id), 300)) ?? {}
  const parts = ['Polier']
  let view
  try {
    view = factoryView(root, config.package)
  } catch { /* no line yet */ }
  if (view?.current) parts.push(`${view.current} ${view.index}/${view.total} · ${view.open.length} open`)
  else if (view) parts.push('line closed')
  const board = loadBoard(root)
  if (board) {
    const running = activeTasks(board, { root, cwd, pinned: state.pinned }).tasks
    if (running.length) parts.push(`running ${running.map((t) => t.id).slice(0, 3).join(', ')}`)
    const ready = readyTasks(board)
    if (ready.length) parts.push(`${ready.length} ready`)
  }
  parts.push(state.role ?? 'worker')
  process.stdout.write(`${parts.join(' · ')}\n`)
}
