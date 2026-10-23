// Run the package's Python tools. Prefers the harness shell service so the
// session's sandbox policy applies (gate commands run project code); falls back
// to a direct process without a shell on Windows or when no shell is mounted.

import { execFile } from 'node:child_process'

const DEFAULT_TIMEOUT_MS = 10 * 60 * 1000
const MAX_OUTPUT = 4 * 1024 * 1024

/** POSIX single-quote one argument. */
export function quote(arg) {
  return `'${String(arg).replace(/'/g, `'\\''`)}'`
}

function sessionCwd(ctx, agent) {
  const wd = ctx.get?.('workingDirectory')
  try {
    if (wd && agent?.session && typeof wd.get === 'function') return wd.get(agent.session)
  } catch { /* fall through */ }
  return agent?.session?.header?.cwd
}

/** The directory a session works in: working-directory service, session header, process cwd. */
export function agentCwd(ctx, agent) {
  return sessionCwd(ctx, agent) || process.cwd()
}

function text(out) {
  if (typeof out === 'string') return out
  return out && typeof out.text === 'string' ? out.text : ''
}

async function viaShell(ctx, shell, agent, argv, { cwd, timeoutMs, signal }) {
  let sandboxPolicy
  const policy = ctx.get?.('sandboxPolicy')
  if (policy && typeof policy.resolve === 'function') {
    try {
      sandboxPolicy = policy.resolve(agent?.session ? { session: agent.session } : {})
    } catch { /* executor default applies */ }
  }
  const spec = shell.resolve({
    command: argv.map(quote).join(' '),
    workdir: cwd,
    timeoutMs,
    stdoutMaxBytes: MAX_OUTPUT,
    ...(sandboxPolicy !== undefined ? { sandboxPolicy } : {}),
    ...(signal ? { signal } : {}),
  })
  let result
  if (typeof shell.execute === 'function') result = await (await shell.execute(spec)).result()
  else result = await shell.run(spec)
  return {
    code: result.exitCode ?? (result.timedOut ? 124 : 1),
    stdout: text(result.stdout),
    stderr: text(result.stderr),
    timedOut: result.timedOut === true,
    via: 'shell',
  }
}

function direct(argv, { cwd, timeoutMs, signal }) {
  return new Promise((resolve) => {
    execFile(argv[0], argv.slice(1), {
      cwd, timeout: timeoutMs, maxBuffer: MAX_OUTPUT, signal, windowsHide: true,
    }, (error, stdout, stderr) => {
      let code = 0
      if (error) code = typeof error.code === 'number' ? error.code : error.killed ? 124 : 127
      resolve({
        code,
        stdout: String(stdout ?? ''),
        stderr: String(stderr ?? '') || (error && typeof error.code !== 'number' ? String(error.message) : ''),
        timedOut: Boolean(error?.killed),
        via: 'direct',
      })
    })
  })
}

/**
 * Run an argument list. Never throws for a failing command; the exit code is in the result.
 * @param {object} ctx - plugin context
 * @param {object|undefined} agent - calling agent, for sandbox policy and cwd
 * @param {string[]} argv - program and arguments
 * @param {{ cwd: string, timeoutMs?: number, signal?: AbortSignal, preferShell?: boolean, strictShell?: boolean }} options
 */
export async function run(ctx, agent, argv, options) {
  const opts = { timeoutMs: DEFAULT_TIMEOUT_MS, ...options }
  const shell = ctx.get?.('shell')
  const useShell = opts.preferShell !== false && process.platform !== 'win32'
    && shell && typeof shell.resolve === 'function'
    && (typeof shell.execute === 'function' || typeof shell.run === 'function')
  if (useShell) {
    try {
      return await viaShell(ctx, shell, agent, argv, opts)
    } catch (error) {
      // Gate commands run project code: never retry them outside the sandbox.
      if (opts.signal?.aborted || opts.strictShell) throw error
      // Our own scripts fall back to a direct process when the shell refuses the request.
    }
  }
  return direct(argv, opts)
}
