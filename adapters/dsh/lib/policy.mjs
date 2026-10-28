// Policy rules for the guard: the JavaScript mirror of core/policy.py.
//
// `policy.json` is optional. Without it nothing here is enforced and a 1.0
// project keeps working exactly as before (`{ enabled: false }`).
//
// The functions mirror the Python decision API one to one:
//   loadPolicy(root)            policy.json + defaults, or { enabled: false }
//   policyErrors(policy)        validation messages, empty for a valid policy
//   limits(policy)              the three integer limits with defaults
//   actionRequired(policy, a)   is the approval action required by the policy
//   approver(policy)            who grants the approvals
//   pathMatches(pattern, rel)   '**'-segment path matching
//   protectedMatch(policy, rel) first matching protected path, or null
//   manifestMatch(policy, rel)  first matching dependency manifest, or null
//   commandDenial(policy, cmd, role)  a denied command, or null
//   hasGrant(root, action, task)      the newest granted approval, or null
//
// Command matching reads a command line the way core/policy.py does: split it
// into shell segments (core/shell.py helpers), strip heredocs, quotes,
// assignments and wrapper programs, recurse into `sh -c`/`eval`, join the
// tokens of one segment with single spaces, then match the policy glob against
// that text. Text inside quotes or heredocs is data and never a command.
//
// Keep this file in step with core/policy.py: both are tested against
// core/tests/policy_cases.json.

import { readdirSync, readFileSync } from 'node:fs'
import path from 'node:path'

import { CASE_INSENSITIVE, normalized } from './project.mjs'

export const POLICY = 'policy.json'
/** Approvals live next to the run records, one file per approval (JSON). */
export const APPROVALS = 'reviews/approvals'

/** The default policy of design §1.1; a project only gets it with a policy.json. */
export const DEFAULTS = {
  version: 1,
  limits: { max_attempts_per_task: 3, max_in_progress: 2, max_review_rounds: 3 },
  scope: {
    protected_paths: ['.env', '.env.*', 'secrets/**', '**/*.pem', '**/*.key', '**/id_rsa*'],
  },
  dependencies: {
    approval: true,
    manifests: ['package.json', 'pyproject.toml', 'Cargo.toml', 'go.mod', 'Package.swift', 'requirements.txt'],
  },
  approvals: {
    actions: ['new_dependency', 'scope_change', 'merge_to_base', 'release', 'reopen_done', 'protected_path'],
    approver: 'owner',
  },
  commands: {
    deny: ['git push*', 'npm publish*', 'pnpm publish*', 'yarn publish*', 'docker push*', 'gh release*',
      'kubectl apply*', 'kubectl delete*', 'terraform apply*', 'rm -rf /*'],
    lead_only: ['*tools/state.py set*', '*tools/approve.py grant*', '*tools/approve.py deny*',
      '*tools/worktree.py finish*'],
    warn: ['*kill*', '*pkill*', 'killall*'],
  },
  checks: { review_before_done: true, handoff_before_done: true, run_record: true, disjoint_scopes: true },
}

/** Every approval action core.approvals knows; the policy lists the required ones. */
export const ACTIONS = [...DEFAULTS.approvals.actions, 'state_override']

/** Keys allowed per section: anything else is a validation error. */
const SECTIONS = {
  limits: ['max_attempts_per_task', 'max_in_progress', 'max_review_rounds'],
  scope: ['protected_paths'],
  dependencies: ['approval', 'manifests'],
  approvals: ['actions', 'approver'],
  commands: ['deny', 'lead_only', 'warn'],
  checks: ['review_before_done', 'handoff_before_done', 'run_record', 'disjoint_scopes'],
}
const LIMIT_RANGES = {
  max_attempts_per_task: [1, 10],
  max_in_progress: [1, 64],
  max_review_rounds: [1, 20],
}

function isObject(value) {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

/** Deep merge: objects merge, everything else (arrays included) replaces. */
function merge(base, override) {
  const out = { ...base }
  for (const [key, value] of Object.entries(override)) {
    out[key] = isObject(value) && isObject(base[key]) ? merge(base[key], value) : value
  }
  return out
}

/** Load `policy.json` from the project root; absent or broken means disabled (fail open). */
export function loadPolicy(root) {
  const file = path.join(String(root ?? ''), POLICY)
  let text
  try {
    text = readFileSync(file, 'utf8')
  } catch {
    return { enabled: false }
  }
  let raw
  try {
    raw = JSON.parse(text)
  } catch (error) {
    return { enabled: false, errors: [`policy.json is not valid JSON: ${String(error?.message ?? error)}`] }
  }
  if (!isObject(raw)) return { enabled: false, errors: ['policy.json must contain a JSON object'] }
  const policy = merge(DEFAULTS, raw)
  policy.enabled = true
  policy.errors = policyErrors(policy)
  return policy
}

/** Validation messages for a (merged) policy; an empty list means valid. */
export function policyErrors(policy) {
  if (!isObject(policy)) return ['policy.json must contain a JSON object']
  const errors = []
  if (policy.version !== 1) errors.push('policy.json: version must be 1')
  for (const [key, value] of Object.entries(policy)) {
    if (key === 'version' || key === 'enabled' || key === 'errors') continue
    if (!(key in SECTIONS)) {
      errors.push(`policy.json: unknown key "${key}"`)
      continue
    }
    if (!isObject(value)) {
      errors.push(`policy.json: "${key}" must be an object`)
      continue
    }
    for (const sub of Object.keys(value)) {
      if (!SECTIONS[key].includes(sub)) errors.push(`policy.json: unknown key "${key}.${sub}"`)
    }
  }
  const limits = policy.limits
  if (isObject(limits)) {
    for (const [name, [low, high]] of Object.entries(LIMIT_RANGES)) {
      if (!(name in limits)) continue
      const value = limits[name]
      if (!Number.isInteger(value) || value < low || value > high) {
        errors.push(`policy.json: limits.${name} must be an integer between ${low} and ${high}`)
      }
    }
  }
  const lists = [
    ['scope.protected_paths', policy.scope?.protected_paths],
    ['dependencies.manifests', policy.dependencies?.manifests],
    ['approvals.actions', policy.approvals?.actions],
    ['commands.deny', policy.commands?.deny],
    ['commands.lead_only', policy.commands?.lead_only],
    ['commands.warn', policy.commands?.warn],
  ]
  for (const [name, list] of lists) {
    if (!Array.isArray(list)) {
      errors.push(`policy.json: ${name} must be a list`)
      continue
    }
    if (list.some((entry) => typeof entry !== 'string' || !entry.trim())) {
      errors.push(`policy.json: ${name} must contain non-empty strings`)
    }
  }
  if (policy.dependencies && typeof policy.dependencies.approval !== 'boolean') {
    errors.push('policy.json: dependencies.approval must be true or false')
  }
  if (policy.approvals && (typeof policy.approvals.approver !== 'string' || !policy.approvals.approver.trim())) {
    errors.push('policy.json: approvals.approver must be a non-empty string')
  }
  if (isObject(policy.checks)) {
    for (const name of SECTIONS.checks) {
      if (name in policy.checks && typeof policy.checks[name] !== 'boolean') {
        errors.push(`policy.json: checks.${name} must be true or false`)
      }
    }
  }
  return errors
}

/** True for a loaded policy of an existing policy.json (the 1.0 default is false). */
export function enabled(policy) {
  if (!isObject(policy) || Object.keys(policy).length === 0) return false
  return policy.enabled !== false
}

/** The integer limits with defaults: a missing or non-integer value falls back, never raises. */
export function limits(policy) {
  const out = { ...DEFAULTS.limits }
  const raw = isObject(policy?.limits) ? policy.limits : {}
  for (const name of Object.keys(out)) {
    if (Number.isInteger(raw[name])) out[name] = raw[name]
  }
  return out
}

/** True when the policy requires an approval for `action` (false when it is disabled). */
export function actionRequired(policy, action) {
  if (!enabled(policy)) return false
  const actions = Array.isArray(policy?.approvals?.actions)
    ? policy.approvals.actions
    : DEFAULTS.approvals.actions
  return actions.includes(action)
}

/** Who grants the approvals: `owner` unless the policy says otherwise. */
export function approver(policy) {
  const value = policy?.approvals?.approver
  return typeof value === 'string' && value.trim() ? value.trim() : DEFAULTS.approvals.approver
}

// ---------------------------------------------------------------------------
// path matching: `**` segments, `*`/`?` inside one segment, basename patterns
// ---------------------------------------------------------------------------

/** Glob one path segment (fnmatch: `*`, `?`, `[...]`); `caseInsensitive` on macOS/Windows. */
function segmentMatch(pattern, segment, caseInsensitive) {
  const source = String(pattern ?? '')
  const text = String(segment ?? '')
  let regex = ''
  for (let i = 0; i < source.length; i++) {
    const char = source[i]
    if (char === '*') regex += '.*'
    else if (char === '?') regex += '.'
    else if (char === '[') {
      const end = source.indexOf(']', i + 1)
      if (end === -1) {
        regex += '\\['
      } else {
        let body = source.slice(i + 1, end)
        if (body.startsWith('!')) body = `^${body.slice(1)}`
        regex += `[${body.replace(/\\/g, '\\\\')}]`
        i = end
      }
    } else regex += char.replace(/[.+^${}()|\\]/g, '\\$&')
  }
  try {
    return new RegExp(`^${regex}$`, caseInsensitive ? 'i' : '').test(text)
  } catch {
    return false
  }
}

function segmentsMatch(patternSegments, pathSegments, caseInsensitive) {
  if (patternSegments.length === 0) return pathSegments.length === 0
  if (patternSegments[0] === '**') {
    if (segmentsMatch(patternSegments.slice(1), pathSegments, caseInsensitive)) return true
    return pathSegments.length > 0 && segmentsMatch(patternSegments, pathSegments.slice(1), caseInsensitive)
  }
  if (pathSegments.length === 0) return false
  if (!segmentMatch(patternSegments[0], pathSegments[0], caseInsensitive)) return false
  return segmentsMatch(patternSegments.slice(1), pathSegments.slice(1), caseInsensitive)
}

/**
 * Does `rel` (project-relative) match the path `pattern`?
 * A pattern without `/` matches the basename at any depth; `**` matches zero or
 * more segments; case is ignored on macOS and Windows, like core.paths.
 */
export function pathMatches(pattern, rel) {
  const pat = normalized(pattern)
  const target = normalized(rel)
  if (!pat || !target) return false
  if (!pat.includes('/')) {
    return segmentMatch(pat, target.split('/').pop(), CASE_INSENSITIVE)
  }
  return segmentsMatch(pat.split('/'), target.split('/'), CASE_INSENSITIVE)
}

/** First protected pattern of the policy that matches `rel`, or null. */
export function protectedMatch(policy, rel) {
  if (!enabled(policy)) return null
  const patterns = Array.isArray(policy?.scope?.protected_paths)
    ? policy.scope.protected_paths
    : DEFAULTS.scope.protected_paths
  for (const pattern of patterns) {
    if (typeof pattern === 'string' && pattern.trim() && pathMatches(pattern, rel)) return pattern
  }
  return null
}

/** First dependency manifest pattern of the policy that matches `rel`, or null. */
export function manifestMatch(policy, rel) {
  if (!enabled(policy)) return null
  const patterns = Array.isArray(policy?.dependencies?.manifests)
    ? policy.dependencies.manifests
    : DEFAULTS.dependencies.manifests
  for (const pattern of patterns) {
    if (typeof pattern === 'string' && pattern.trim() && pathMatches(pattern, rel)) return pattern
  }
  return null
}

/** True when dependency manifests need an approval (default: true). */
export function dependencyApproval(policy) {
  const value = policy?.dependencies?.approval
  return typeof value === 'boolean' ? value : DEFAULTS.dependencies.approval
}

/** The wrapper programs whose options consume the next word (`nice -n 5 git ...`). */
const WRAPPER_VALUE_OPTIONS = {
  sudo: ['-u', '--user', '-g', '--group', '-h', '--host', '-p', '--prompt', '-C', '--close-from',
    '-T', '--command-timeout', '-U', '--other-user', '-D', '--chdir', '-r', '--role', '-t', '--type'],
  doas: ['-u', '-C'],
  env: ['-u', '--unset', '-C', '--chdir', '-S', '--split-string'],
  nice: ['-n', '--adjustment'],
  ionice: ['-c', '--class', '-n', '--classdata', '-p', '--pid', '-P', '--pgid', '-u', '--uid'],
  stdbuf: ['-i', '--input', '-o', '--output', '-e', '--error'],
  timeout: ['-s', '--signal', '-k', '--kill-after'],
}

// ---------------------------------------------------------------------------
// commands: fnmatch globs, shell segments, nested shells, no quoted data
// ---------------------------------------------------------------------------

const WRAPPERS = new Set(['sudo', 'env', 'nohup', 'time', 'command', 'exec', 'nice', 'ionice', 'stdbuf', 'doas'])
const SHELLS = new Set(['sh', 'bash', 'zsh', 'dash', 'ksh'])
const SEPARATORS = new Set(['&&', '||', '|&', ';;', '|', '&', ';', '(', ')'])
const OPS = ['&>>', '<<<', '>>', '>|', '&>', '>&', '<&', '<<', '<>', '&&', '||', '|&', ';;',
  '>', '<', '|', '&', ';', '(', ')']
const HEREDOC = /<<(-?)\s*(['"]?)([A-Za-z_][A-Za-z0-9_]*)\2/g
const ASSIGNMENT = /^[A-Za-z_][A-Za-z0-9_]*=/
const MAX_DEPTH = 4

/** fnmatch-style match of a policy pattern against one command segment (case-insensitive). */
export function globMatch(pattern, text) {
  return segmentMatch(pattern, text, true)
}

/** Drop heredoc bodies; their text is data, not commands. */
function stripHeredocs(command) {
  const out = []
  const pending = [] // [delimiter, tabs]
  for (const line of String(command ?? '').split('\n')) {
    if (pending.length > 0) {
      const [delimiter, tabs] = pending[0]
      if ((tabs ? line.replace(/^\t+/, '') : line) === delimiter) pending.shift()
      continue
    }
    out.push(line)
    for (const match of line.matchAll(HEREDOC)) {
      if (!match[0].includes('<<<')) pending.push([match[2], match[1] === '-'])
    }
  }
  return out.join('\n')
}

/** Split on newlines outside quotes (core.shell._lines). */
function linesOf(command) {
  const lines = []
  let current = ''
  let quote = ''
  let escape = false
  for (const char of command) {
    if (escape) {
      escape = false
    } else if (char === '\\' && quote !== "'") {
      escape = true
    } else if (quote) {
      if (char === quote) quote = ''
    } else if (char === "'" || char === '"') {
      quote = char
    } else if (char === '\n') {
      lines.push(current)
      current = ''
      continue
    }
    current += char
  }
  lines.push(current)
  return lines
}

/** Shell words and punctuation of one line; quoted text stays one word, quotes removed. */
function lexLine(line) {
  const out = []
  let word = ''
  let quote = ''
  let escape = false
  let operator = ''
  const flushWord = () => {
    if (word) out.push(word)
    word = ''
  }
  const flushOperator = () => {
    if (operator) out.push(operator)
    operator = ''
  }
  for (const char of line) {
    if (escape) {
      word += char
      escape = false
      continue
    }
    if (char === '\\' && quote !== "'") {
      escape = true
      continue
    }
    if (quote) {
      if (char === quote) quote = ''
      else word += char
      continue
    }
    if (char === "'" || char === '"') {
      flushOperator()
      quote = char
      continue
    }
    if (char === ' ' || char === '\t') {
      flushWord()
      flushOperator()
      continue
    }
    if ('();<>|&'.includes(char)) {
      flushWord()
      operator += char
      continue
    }
    flushOperator()
    word += char
  }
  flushWord()
  flushOperator()
  return out
}

/** Split a punctuation run into the shell operators it holds. */
function splitOps(operator) {
  const out = []
  let rest = operator
  while (rest) {
    const op = OPS.find((candidate) => rest.startsWith(candidate)) ?? rest[0]
    out.push(op)
    rest = rest.slice(op.length)
  }
  return out
}

/** Tokens of a command line, one `;` appended after every (unquoted) line. */
function tokensOf(command) {
  const out = []
  for (const line of linesOf(stripHeredocs(command))) {
    for (const token of lexLine(line)) {
      if (SEPARATORS.has(token) || token === ';') out.push(token)
      else if (token && token !== ';' && /^[();<>|&]+$/.test(token)) out.push(...splitOps(token))
      else out.push(token)
    }
    out.push(';')
  }
  return out
}

/** Split tokens into simple command segments. */
function segmentsOf(words) {
  const segments = []
  let current = []
  for (const word of words) {
    if (SEPARATORS.has(word)) {
      if (current.length > 0) segments.push(current)
      current = []
      if (word === '(' || word === ')') segments.push([word])
    } else {
      current.push(word)
    }
  }
  if (current.length > 0) segments.push(current)
  return segments
}

/** Drop leading assignments and wrapper programs (`sudo`, `env`, `nohup`, ...). */
function commandPosition(args) {
  let rest = args
  while (rest.length > 0) {
    if (ASSIGNMENT.test(rest[0])) {
      rest = rest.slice(1)
      continue
    }
    const name = path.basename(rest[0])
    if (!WRAPPERS.has(name)) return rest
    rest = rest.slice(1)
    const values = WRAPPER_VALUE_OPTIONS[name] ?? []
    while (rest.length > 0) {
      if (ASSIGNMENT.test(rest[0])) rest = rest.slice(1)
      else if (rest[0] === '--') {
        rest = rest.slice(1)
        break
      } else if (rest[0].startsWith('-')) rest = rest.slice(values.includes(rest[0]) && rest.length > 1 ? 2 : 1)
      else break
    }
  }
  return rest
}

/**
 * The command text of every shell segment, after heredoc/quote stripping,
 * wrapper removal and recursion into `sh -c` and `eval`.
 * @returns {string[]}
 */
export function commandSegments(command, depth = 0) {
  const texts = []
  if (typeof command !== 'string' || !command.trim()) return texts
  for (const segment of segmentsOf(tokensOf(command))) {
    if (segment.length === 1 && (segment[0] === '(' || segment[0] === ')')) continue
    const args = commandPosition(segment)
    if (args.length === 0) continue
    const name = path.basename(args[0])
    if (depth < MAX_DEPTH && SHELLS.has(name) && args.includes('-c')) {
      const index = args.indexOf('-c')
      if (index + 1 < args.length) texts.push(...commandSegments(args[index + 1], depth + 1))
      continue
    }
    if (depth < MAX_DEPTH && name === 'eval') {
      texts.push(...commandSegments(args.slice(1).join(' '), depth + 1))
      continue
    }
    texts.push(args.join(' '))
  }
  return texts
}

/**
 * The policy denial of one command, or null.
 * `deny` denies every role; `lead_only` denies workers and reviewers only.
 * @returns {{ rule: 'deny'|'lead_only', pattern: string, command: string, reason: string }|null}
 */
export function commandDenial(policy, command, role = 'worker') {
  if (!enabled(policy)) return null
  const commands = isObject(policy?.commands) ? policy.commands : DEFAULTS.commands
  if (typeof command !== 'string' || !command.trim()) return null
  const texts = commandSegments(command)
  if (texts.length === 0) return null
  const deny = Array.isArray(commands.deny) ? commands.deny : []
  for (const pattern of deny) {
    if (typeof pattern !== 'string' || !pattern) continue
    const hit = texts.find((text) => globMatch(pattern, text))
    if (hit) {
      return {
        rule: 'deny',
        pattern,
        command: hit,
        reason: `the command matches the deny rule "${pattern}" in policy.json, which no role may run`,
      }
    }
  }
  if (role === 'lead') return null
  const leadOnly = Array.isArray(commands.lead_only) ? commands.lead_only : []
  for (const pattern of leadOnly) {
    if (typeof pattern !== 'string' || !pattern) continue
    const hit = texts.find((text) => globMatch(pattern, text))
    if (hit) {
      return {
        rule: 'lead_only',
        pattern,
        command: hit,
        reason: `the command matches the lead-only rule "${pattern}" in policy.json; only the lead session may run it`,
      }
    }
  }
  return null
}

// ---------------------------------------------------------------------------
// approvals: reviews/approvals/AP-NNN.json
// ---------------------------------------------------------------------------

/** Every readable approval record; a broken file is ignored, like the Python reader. */
export function loadApprovals(root) {
  const folder = path.join(String(root ?? ''), APPROVALS)
  let names
  try {
    names = readdirSync(folder).filter((name) => name.endsWith('.json')).sort()
  } catch {
    return []
  }
  const records = []
  for (const name of names) {
    try {
      const record = JSON.parse(readFileSync(path.join(folder, name), 'utf8'))
      if (isObject(record)) records.push(record)
    } catch { /* best effort: an unreadable record is not an approval */ }
  }
  return records
}

function approvalStamp(record) {
  return `${String(record?.approved_at ?? record?.requested_at ?? '')} ${String(record?.id ?? '')}`
}

/**
 * The newest granted approval for `action`; with a `task` the record must be
 * for that task (a record without a task matches any task). `task` null/undefined
 * matches any record. Returns null when there is no granted approval.
 */
export function hasGrant(root, action, task = null) {
  if (typeof action !== 'string' || !action) return null
  const wanted = task === null || task === undefined ? null : String(task)
  let newest = null
  for (const record of loadApprovals(root)) {
    if (record.status !== 'granted' || record.action !== action) continue
    const owner = record.task === null || record.task === undefined ? null : String(record.task)
    if (wanted !== null && owner !== null && owner !== wanted) continue
    if (!newest || approvalStamp(record) >= approvalStamp(newest)) newest = record
  }
  return newest
}

/** Pending approval records, newest first (for `/pl policy`). */
export function pendingApprovals(root) {
  return loadApprovals(root)
    .filter((record) => record.status === 'pending')
    .sort((a, b) => approvalStamp(b).localeCompare(approvalStamp(a)))
}
