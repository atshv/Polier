// Read-only views of policy.json and the approval records for the live context
// and pl_status. The rules themselves (validation, protected paths, manifests,
// commands, grants) live in core/policy.py and core/guard.py.

import { readdirSync, readFileSync } from 'node:fs'
import path from 'node:path'

const POLICY = 'policy.json'
const APPROVALS = 'reviews/approvals'
const LIMITS = { max_attempts_per_task: 3, max_in_progress: 2, max_review_rounds: 3 }

/** Every approval action core.approvals knows; the policy lists the required ones. */
export const ACTIONS = ['new_dependency', 'scope_change', 'merge_to_base', 'release', 'reopen_done',
  'protected_path', 'state_override']

function isObject(value) {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

/** policy.json of the project root, or { enabled: false } when it is absent or broken. */
export function loadPolicy(root) {
  try {
    const raw = JSON.parse(readFileSync(path.join(String(root ?? ''), POLICY), 'utf8'))
    return isObject(raw) ? { ...raw, enabled: raw.enabled !== false } : { enabled: false }
  } catch {
    return { enabled: false }
  }
}

export function enabled(policy) {
  return isObject(policy) && policy.enabled === true
}

/** The three integer limits with defaults. */
export function limits(policy) {
  const out = { ...LIMITS }
  const raw = isObject(policy?.limits) ? policy.limits : {}
  for (const name of Object.keys(out)) if (Number.isInteger(raw[name])) out[name] = raw[name]
  return out
}

/** Who grants the approvals: `owner` unless the policy says otherwise. */
export function approver(policy) {
  const value = policy?.approvals?.approver
  return typeof value === 'string' && value.trim() ? value.trim() : 'owner'
}

function stamp(record) {
  return `${String(record?.approved_at ?? record?.requested_at ?? '')} ${String(record?.id ?? '')}`
}

/** Pending approval records, newest first. */
export function pendingApprovals(root) {
  const folder = path.join(String(root ?? ''), APPROVALS)
  let names
  try {
    names = readdirSync(folder).filter((name) => name.endsWith('.json'))
  } catch {
    return []
  }
  const records = []
  for (const name of names) {
    try {
      const record = JSON.parse(readFileSync(path.join(folder, name), 'utf8'))
      if (isObject(record) && record.status === 'pending') records.push(record)
    } catch { /* an unreadable record is not an approval */ }
  }
  return records.sort((a, b) => stamp(b).localeCompare(stamp(a)))
}
