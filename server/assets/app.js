/* Polier dashboard 2.0 — one dependency-free ES2020 file.
   No frameworks, no imports, no inline handlers. Every piece of server text is
   rendered with textContent (or the small safe markdown renderer below). */

'use strict';

/* =========================================================================
   1. Constants
   ========================================================================= */

const VERSION = '2.0.0';
const THEME_KEY = 'polier.theme';
const MORE_MARK = '…';

const VIEWS = [
  { key: 'yourwork', label: 'Your Work', feature: 'inbox' },
  { key: 'board', label: 'Board' },
  { key: 'table', label: 'Table' },
  { key: 'timeline', label: 'Timeline', feature: 'timeline' },
  { key: 'cycles', label: 'Cycles', feature: 'cycles' },
  { key: 'modules', label: 'Modules', feature: 'modules' },
  { key: 'coverage', label: 'Coverage', feature: 'coverage' },
  { key: 'graph', label: 'Graph' },
  { key: 'dispatch', label: 'Dispatch' },
  { key: 'approvals', label: 'Approvals' },
  { key: 'activity', label: 'Activity' },
  { key: 'analytics', label: 'Analytics', feature: 'analytics' },
  { key: 'sessions', label: 'Sessions' },
  { key: 'pages', label: 'Pages', feature: 'pages' },
  { key: 'intake', label: 'Intake', feature: 'intake' },
  { key: 'assistant', label: 'Assistant', feature: 'assistant' },
  { key: 'automations', label: 'Automations', feature: 'automations' },
  { key: 'github', label: 'GitHub', feature: 'github' },
  { key: 'plan', label: 'Plan' },
  { key: 'settings', label: 'Settings' }
];

const STATUS = {
  pending: { label: 'Pending', color: 'neutral' },
  claimed: { label: 'Claimed', color: 'blue' },
  in_progress: { label: 'In progress', color: 'blue' },
  verifying: { label: 'Verifying', color: 'violet' },
  review: { label: 'Reviewing', color: 'violet' },
  rework: { label: 'Rework', color: 'amber' },
  blocked: { label: 'Blocked', color: 'orange' },
  failed: { label: 'Failed', color: 'red' },
  done: { label: 'Done', color: 'green' }
};

const COLUMNS = [
  { key: 'pending', label: 'Pending', statuses: ['pending'], color: 'neutral' },
  { key: 'in_progress', label: 'In progress', statuses: ['claimed', 'in_progress'], color: 'blue' },
  { key: 'reviewing', label: 'Reviewing', statuses: ['review', 'verifying'], color: 'violet' },
  { key: 'rework', label: 'Rework', statuses: ['rework'], color: 'amber' },
  { key: 'blocked', label: 'Blocked', statuses: ['blocked'], color: 'orange' },
  { key: 'failed', label: 'Failed', statuses: ['failed'], color: 'red' },
  { key: 'done', label: 'Done', statuses: ['done'], color: 'green' }
];

/* The quick-transition map the drawer renders (superset of the CLI table for
   the claimed state, which behaves like pending). */
const TRANSITIONS = {
  pending: ['claimed', 'in_progress'],
  claimed: ['in_progress', 'pending'],
  in_progress: ['verifying'],
  verifying: ['review'],
  review: ['done', 'rework'],
  rework: ['in_progress'],
  blocked: ['pending', 'in_progress'],
  failed: ['pending', 'in_progress'],
  done: ['rework']
};
const NOTE_TARGETS = new Set(['rework', 'blocked', 'failed']);

const APPROVAL_ACTIONS = [
  'new_dependency', 'scope_change', 'merge_to_base', 'release',
  'reopen_done', 'protected_path', 'state_override'
];
const APPROVAL_FILTERS = [
  { key: 'pending', label: 'Pending' },
  { key: 'granted', label: 'Granted' },
  { key: 'denied', label: 'Denied' },
  { key: 'all', label: 'All' }
];
const SESSION_ROLES = ['worker', 'reviewer', 'lead'];
const SESSION_ACTIVE = new Set(['starting', 'running']);

/* =========================================================================
   2. Tiny DOM helpers (no HTML-string injection anywhere)
   ========================================================================= */

const $ = (selector, root) => (root || document).querySelector(selector);

function h(tag, props, ...children) {
  const node = document.createElement(tag);
  if (props) {
    for (const key of Object.keys(props)) {
      const value = props[key];
      if (value === null || value === undefined || value === false) continue;
      if (key === 'class') node.className = value;
      else if (key === 'text') node.textContent = String(value);
      else if (key === 'dataset') Object.assign(node.dataset, value);
      else if (key === 'on') {
        for (const event of Object.keys(value)) node.addEventListener(event, value[event]);
      } else if (key === 'style' && typeof value === 'object') Object.assign(node.style, value);
      else if (key === 'value' || key === 'checked' || key === 'disabled' || key === 'selected') {
        node[key] = value;
      } else if (key === 'ref' && typeof value === 'function') value(node);
      else node.setAttribute(key, value === true ? '' : String(value));
    }
  }
  append(node, children);
  return node;
}

function append(parent, children) {
  for (const child of children) {
    if (child === null || child === undefined || child === false || child === true) continue;
    if (Array.isArray(child)) append(parent, child);
    else if (child instanceof Node) parent.appendChild(child);
    else parent.appendChild(document.createTextNode(String(child)));
  }
  return parent;
}

function clear(node) {
  while (node && node.firstChild) node.removeChild(node.firstChild);
  return node;
}

function setChildren(node, ...children) {
  clear(node);
  append(node, children);
  return node;
}

function focusSoon(node) {
  if (!node) return;
  window.setTimeout(() => { try { node.focus(); } catch (err) { /* ignore */ } }, 0);
}

/* Focus preservation for views that re-render on input (filters). */
function captureFocus() {
  const active = document.activeElement;
  if (!active) return null;
  const key = active.getAttribute && active.getAttribute('data-fkey');
  if (!key) return null;
  let start = null;
  let end = null;
  try { start = active.selectionStart; end = active.selectionEnd; } catch (err) { /* not a text input */ }
  return { key, start, end };
}

function restoreFocus(snapshot) {
  if (!snapshot) return;
  const node = document.querySelector('[data-fkey="' + snapshot.key.replace(/"/g, '\\"') + '"]');
  if (!node) return;
  try {
    node.focus();
    if (snapshot.start !== null && snapshot.start !== undefined && typeof node.setSelectionRange === 'function') {
      node.setSelectionRange(snapshot.start, snapshot.end);
    }
  } catch (err) { /* ignore */ }
}

/* =========================================================================
   3. Formatting
   ========================================================================= */

function parseDate(value) {
  if (!value) return null;
  if (value instanceof Date) return isNaN(value.getTime()) ? null : value;
  const text = String(value).trim();
  const candidate = /[zZ]$/.test(text) || /[+-]\d\d:?\d\d$/.test(text) ? text : text + 'Z';
  const date = new Date(candidate);
  if (isNaN(date.getTime())) {
    const fallback = new Date(text);
    return isNaN(fallback.getTime()) ? null : fallback;
  }
  return date;
}

function fmtNum(value) {
  const num = Number(value);
  if (!isFinite(num)) return '0';
  return num.toLocaleString('en-US');
}

function fmtTokens(value) {
  const num = Number(value) || 0;
  if (num >= 1000000) return (num / 1000000).toFixed(num >= 10000000 ? 0 : 1).replace(/\.0$/, '') + 'M';
  if (num >= 1000) return (num / 1000).toFixed(num >= 100000 ? 0 : 1).replace(/\.0$/, '') + 'k';
  return String(num);
}

function fmtDuration(seconds) {
  const total = Math.max(0, Math.round(Number(seconds) || 0));
  if (total < 60) return total + 's';
  const minutes = Math.floor(total / 60);
  const rest = total % 60;
  if (minutes < 60) return minutes + 'm ' + String(rest).padStart(2, '0') + 's';
  const hours = Math.floor(minutes / 60);
  return hours + 'h ' + String(minutes % 60).padStart(2, '0') + 'm';
}

function fmtTime(iso) {
  const date = parseDate(iso);
  if (!date) return '—';
  return date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
}

function relTime(iso) {
  const date = parseDate(iso);
  if (!date) return '—';
  const seconds = Math.round((Date.now() - date.getTime()) / 1000);
  if (seconds < 45) return 'now';
  if (seconds < 3600) return Math.round(seconds / 60) + 'm ago';
  if (seconds < 86400) return Math.round(seconds / 3600) + 'h ago';
  if (seconds < 86400 * 7) return Math.round(seconds / 86400) + 'd ago';
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

function dayKey(iso) {
  const date = parseDate(iso);
  if (!date) return 'unknown';
  return date.getFullYear() + '-' + String(date.getMonth() + 1).padStart(2, '0') + '-' + String(date.getDate()).padStart(2, '0');
}

function dayLabel(iso) {
  const date = parseDate(iso);
  if (!date) return 'Unknown';
  const today = new Date();
  const startOfToday = new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime();
  const startOfDate = new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
  const diff = Math.round((startOfToday - startOfDate) / 86400000);
  if (diff === 0) return 'Today';
  if (diff === 1) return 'Yesterday';
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

function truncate(value, max) {
  const text = value === null || value === undefined ? '' : String(value);
  if (text.length <= max) return text;
  return text.slice(0, Math.max(0, max - 1)) + MORE_MARK;
}

function basename(path) {
  if (!path) return '';
  const parts = String(path).replace(/\\/g, '/').split('/').filter(Boolean);
  return parts.length ? parts[parts.length - 1] : String(path);
}

function plural(count, one, many) {
  return count === 1 ? one : (many || one + 's');
}

/* =========================================================================
   4. Status helpers
   ========================================================================= */

function stMeta(status) {
  return STATUS[status] || { label: status ? String(status) : 'Unknown', color: 'neutral' };
}

function statusPill(status, extraClass) {
  const meta = stMeta(status);
  return h('span', {
    class: 'badge bg-' + meta.color + ' st-' + meta.color + (extraClass ? ' ' + extraClass : ''),
    title: 'Status: ' + meta.label
  }, h('span', { class: 'dot' }), meta.label);
}

function statusDot(status) {
  const meta = stMeta(status);
  return h('span', { class: 'column-dot st-' + meta.color, title: meta.label });
}

/* =========================================================================
   5. API helper
   ========================================================================= */

/* The optional dashboard token arrives once in the page URL (?token=...).
   Keep it in memory only: never in localStorage, never in a toast or log. */
const AUTH_TOKEN = (function readToken() {
  try {
    const params = new URLSearchParams(location.search);
    return params.get('token') || '';
  } catch (err) {
    return '';
  }
})();

function withToken(url) {
  if (!AUTH_TOKEN) return url;
  const separator = url.indexOf('?') === -1 ? '?' : '&';
  return url + separator + 'token=' + encodeURIComponent(AUTH_TOKEN);
}


class ApiError extends Error {
  constructor(message, status, details) {
    super(message);
    this.name = 'ApiError';
    this.status = status || 0;
    this.details = details === undefined ? null : details;
  }
}

async function api(path, options) {
  const opts = options || {};
  const method = (opts.method || 'GET').toUpperCase();
  const headers = Object.assign({ Accept: 'application/json' }, opts.headers || {});
  const init = { method, headers, signal: opts.signal };
  if (method !== 'GET' && method !== 'HEAD') headers['X-Polier-Action'] = '1';
  if (opts.body !== undefined) {
    headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(opts.body);
  }
  let response;
  try {
    response = await fetch(withToken(path), init);
  } catch (err) {
    if (err && err.name === 'AbortError') throw err;
    throw new ApiError('Cannot reach the Polier server (' + (err && err.message ? err.message : err) + ')', 0, null);
  }
  const text = await response.text();
  let data = null;
  if (text) {
    try { data = JSON.parse(text); } catch (err) { data = { error: text.slice(0, 500) }; }
  }
  if (!response.ok) {
    const message = data && (data.error || data.message) ? String(data.error || data.message) : 'HTTP ' + response.status;
    throw new ApiError(message, response.status, data ? data.details : null);
  }
  return data;
}

/* A 409 from the state API carries {error, details:{errors, actions, detail}}. */
function describeError(err) {
  if (!err) return 'Unknown error';
  let text = err.message || String(err);
  const details = err.details;
  if (Array.isArray(details) && details.length) {
    text += '\n' + details.join('\n');
  } else if (details && typeof details === 'object') {
    if (Array.isArray(details.errors) && details.errors.length) text += '\n' + details.errors.join('\n');
    if (details.detail && !text.includes(String(details.detail))) text += '\n' + String(details.detail);
  }
  return text;
}

function errorActions(err) {
  const details = err && err.details;
  if (!details || typeof details !== 'object') return [];
  return Array.isArray(details.actions) ? details.actions.filter((item) => item && (item.command || item.reason || item.action)) : [];
}

/* A readable callout for any error; renders 409 actions with copy buttons. */
function errorCallout(err, options) {
  const opts = options || {};
  const box = h('div', { class: 'callout callout-error ' + (opts.class || '') });
  const body = h('div', { class: 'callout-stack grow' });
  body.appendChild(h('div', { text: describeError(err) }));
  const details = err && err.details;
  if (details && Array.isArray(details.errors) && details.errors.length > 1) {
    const list = h('ul');
    for (const item of details.errors) list.appendChild(h('li', { text: String(item) }));
    body.appendChild(list);
  }
  const actions = errorActions(err);
  if (actions.length) {
    const list = h('div', { class: 'col', style: { gap: '4px' } });
    for (const action of actions) {
      const command = action.command || '';
      const row = h('div', { class: 'cmd-row' },
        h('span', { class: 'cmd', text: command || String(action.reason || action.action || '') }));
      if (command) {
        row.appendChild(h('button', {
          class: 'btn btn-sm', type: 'button', title: 'Copy command', text: 'Copy',
          on: { click: () => copyText(command) }
        }));
      }
      list.appendChild(row);
    }
    body.appendChild(list);
  }
  box.appendChild(body);
  return box;
}

/* =========================================================================
   6. Toasts and clipboard
   ========================================================================= */

function toast(message, kind, ttl) {
  const variant = kind || 'info';
  const node = h('div', { class: 'toast toast-' + variant, role: 'status' },
    h('div', { class: 'toast-text', text: String(message) }),
    h('button', {
      class: 'toast-close', type: 'button', 'aria-label': 'Dismiss notification', text: '×',
      on: { click: () => node.remove() }
    }));
  const host = document.getElementById('toasts');
  if (!host) return node;
  host.appendChild(node);
  while (host.children.length > 5) host.removeChild(host.firstChild);
  const seconds = typeof ttl === 'number' ? ttl : (variant === 'error' ? 7000 : 4200);
  window.setTimeout(() => node.remove(), seconds);
  return node;
}

async function copyText(text) {
  const value = String(text === null || text === undefined ? '' : text);
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(value);
    } else {
      const area = h('textarea', { class: 'sr-only' });
      area.value = value;
      document.body.appendChild(area);
      area.select();
      document.execCommand('copy');
      area.remove();
    }
    toast('Copied to clipboard', 'ok', 1800);
  } catch (err) {
    toast('Copy failed: ' + (err && err.message ? err.message : err), 'error');
  }
}

/* =========================================================================
   7. Safe markdown-ish renderer (DOM only, never HTML strings)
   ========================================================================= */

function inlineNodes(text, options) {
  const nodes = [];
  const source = String(text);
  const pattern = /(`[^`]+`|\[[^\]]+\]\([^()\s]+\)|\*\*[^*]+\*\*|\*[^*\s][^*]*\*)/g;
  let last = 0;
  let match = pattern.exec(source);
  while (match) {
    if (match.index > last) nodes.push(document.createTextNode(source.slice(last, match.index)));
    const token = match[0];
    if (token.charAt(0) === '`') {
      nodes.push(h('code', { class: 'md-inline-code', text: token.slice(1, -1) }));
    } else if (token.charAt(0) === '[') {
      const parsed = /^\[([^\]]+)\]\(([^()\s]+)\)$/.exec(token);
      if (parsed) nodes.push(markdownLink(parsed[1], parsed[2], options));
      else nodes.push(document.createTextNode(token));
    } else if (token.startsWith('**')) {
      nodes.push(h('strong', { text: token.slice(2, -2) }));
    } else {
      nodes.push(h('em', { text: token.slice(1, -1) }));
    }
    last = pattern.lastIndex;
    match = pattern.exec(source);
  }
  if (last < source.length) nodes.push(document.createTextNode(source.slice(last)));
  return nodes;
}

function mdFragment(text, options) {
  const opts = options || {};
  const fragment = document.createDocumentFragment();
  if (text === null || text === undefined || String(text) === '') return fragment;
  const lines = String(text).replace(/\r\n?/g, '\n').split('\n');
  let index = 0;
  let paragraph = [];

  const flush = () => {
    if (!paragraph.length) return;
    const node = h('p');
    append(node, inlineNodes(paragraph.join(' '), opts));
    fragment.appendChild(node);
    paragraph = [];
  };

  while (index < lines.length) {
    const line = lines[index];
    if (/^\s*```/.test(line)) {
      flush();
      const buffer = [];
      index += 1;
      while (index < lines.length && !/^\s*```/.test(lines[index])) { buffer.push(lines[index]); index += 1; }
      if (index < lines.length) index += 1;
      fragment.appendChild(h('pre', { class: 'md-code' }, h('code', { text: buffer.join('\n') })));
      continue;
    }
    const heading = /^(#{1,6})\s+(.*)$/.exec(line);
    if (heading) {
      flush();
      const level = Math.min(6, heading[1].length + 1);
      const node = h('h' + level);
      append(node, inlineNodes(heading[2].trim(), opts));
      fragment.appendChild(node);
      index += 1;
      continue;
    }
    if (/^\s*([-*_])\s*\1\s*\1+\s*$/.test(line)) {
      flush();
      fragment.appendChild(h('hr'));
      index += 1;
      continue;
    }
    if (/^\s*[-*+]\s+/.test(line)) {
      flush();
      const list = h('ul');
      while (index < lines.length && /^\s*[-*+]\s+/.test(lines[index])) {
        const item = h('li');
        append(item, inlineNodes(lines[index].replace(/^\s*[-*+]\s+/, ''), opts));
        list.appendChild(item);
        index += 1;
      }
      fragment.appendChild(list);
      continue;
    }
    if (/^\s*\d+[.)]\s+/.test(line)) {
      flush();
      const list = h('ol');
      while (index < lines.length && /^\s*\d+[.)]\s+/.test(lines[index])) {
        const item = h('li');
        append(item, inlineNodes(lines[index].replace(/^\s*\d+[.)]\s+/, ''), opts));
        list.appendChild(item);
        index += 1;
      }
      fragment.appendChild(list);
      continue;
    }
    if (/^\s*>\s?/.test(line)) {
      flush();
      const buffer = [];
      while (index < lines.length && /^\s*>\s?/.test(lines[index])) {
        buffer.push(lines[index].replace(/^\s*>\s?/, ''));
        index += 1;
      }
      const quote = h('blockquote');
      append(quote, inlineNodes(buffer.join(' '), opts));
      fragment.appendChild(quote);
      continue;
    }
    if (/^\s*\|/.test(line)) {
      flush();
      const buffer = [];
      while (index < lines.length && /^\s*\|/.test(lines[index])) { buffer.push(lines[index]); index += 1; }
      fragment.appendChild(h('pre', { class: 'md-table' }, h('code', { text: buffer.join('\n') })));
      continue;
    }
    if (line.trim() === '') { flush(); index += 1; continue; }
    paragraph.push(line.trim());
    index += 1;
  }
  flush();
  return fragment;
}

function mdBlock(text, emptyText) {
  if (text === null || text === undefined || String(text).trim() === '') {
    return h('div', { class: 'hint', text: emptyText || 'Nothing here yet.' });
  }
  return h('div', { class: 'md' }, mdFragment(text));
}

/* =========================================================================
   8. Theme
   ========================================================================= */

function preferredTheme() {
  const root = document.documentElement;
  if (root.dataset.theme === 'light' || root.dataset.theme === 'dark') return root.dataset.theme;
  return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function paintThemeGlyph() {
  const glyph = document.getElementById('theme-glyph');
  if (!glyph) return;
  const theme = preferredTheme();
  glyph.textContent = theme === 'dark' ? '☀' : '☾';
  const button = document.getElementById('btn-theme');
  if (button) button.title = theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme';
}

function applyTheme(theme) {
  if (theme === 'light' || theme === 'dark') document.documentElement.dataset.theme = theme;
  else delete document.documentElement.dataset.theme;
  paintThemeGlyph();
}

function initTheme() {
  const requested = new URLSearchParams(location.search).get('theme');
  let stored = null;
  try { stored = localStorage.getItem(THEME_KEY); } catch (err) { stored = null; }
  if (requested === 'light' || requested === 'dark') {
    try { localStorage.setItem(THEME_KEY, requested); } catch (err) { /* private mode */ }
    applyTheme(requested);
  } else if (stored === 'light' || stored === 'dark') {
    applyTheme(stored);
  } else {
    paintThemeGlyph();
  }
}

function toggleTheme() {
  const next = preferredTheme() === 'dark' ? 'light' : 'dark';
  try { localStorage.setItem(THEME_KEY, next); } catch (err) { /* private mode */ }
  applyTheme(next);
}
/* =========================================================================
   2.1 — Project Cockpit: settings, labels, views, filters, inbox, worklog
   ========================================================================= */

const PREF_VIEW = 'polier.view';
const PREF_DENSITY = 'polier.density';
const FEATURE_NOTES = {
  inbox: 'Your Work, the Inbox panel and the header bell.',
  worklog: 'The Worklog drawer tab and effort columns.',
  views: 'The filter builder, saved views, grouping, sorting and density.',
  labels: 'Task labels on cards, rows, the drawer and in Settings.',
  timeline: 'The plan on a time axis: stage lanes, bars, critical path and today.',
  cycles: 'Stages as cycles with burndown, exit gates and owner decisions.',
  modules: 'The package map with health, docs, contracts and effort.',
  coverage: 'Requirements from docs/quality.md mapped to tasks and evidence.',
  analytics: 'Throughput, cycle time, gate results and effort charts.',
  pages: 'The project Markdown as a browsable wiki with search, history and backlinks.',
  intake: 'Proposals that become tasks after an accept decision.',
  assistant: 'Ask the project questions; conversations are local to this machine.',
  automations: 'Committed rules that suggest actions; dry run only, nothing executes.',
  github: 'Read-only pull request and CI status through the gh CLI.'
};
const FEATURE_LABELS = {
  inbox: 'Your Work and Inbox',
  worklog: 'Worklog',
  views: 'Filter builder and views',
  labels: 'Task labels',
  timeline: 'Timeline',
  cycles: 'Cycles',
  modules: 'Modules',
  coverage: 'Coverage',
  analytics: 'Analytics',
  pages: 'Pages',
  intake: 'Intake',
  assistant: 'Assistant',
  automations: 'Automations',
  github: 'GitHub'
};

const FIELD_LABELS = {
  id: 'ID', title: 'Title', status: 'Status', stage: 'Stage', stage_title: 'Stage title',
  package: 'Package', owner: 'Owner', label: 'Label', complexity: 'Complexity',
  estimate_hours: 'Estimate', tokens: 'Tokens', attempt: 'Attempts',
  gates_missing: 'Missing gates', ready: 'Ready', running: 'Running', claimed: 'Claimed',
  blocked: 'Blocked', review_verdict: 'Review verdict', budget: 'Budget'
};
const OPERATOR_LABELS = {
  is: 'is', is_not: 'is not', contains: 'contains', not_contains: 'does not contain',
  empty: 'is empty', not_empty: 'is not empty', any_of: 'is one of', none_of: 'is none of',
  eq: '=', neq: '≠', gt: '>', gte: '≥', lt: '<', lte: '≤'
};
const NO_VALUE_OPERATORS = ['empty', 'not_empty'];
const PALETTE_FALLBACK = ['neutral', 'blue', 'green', 'amber', 'orange', 'red', 'violet', 'teal'];
const GROUP_FALLBACK = ['type', 'risk', 'origin', 'area', 'theme', 'custom'];

function prefGet(key, fallback) {
  try {
    const value = localStorage.getItem(key);
    return value === null ? fallback : value;
  } catch (err) {
    return fallback;
  }
}

function prefSet(key, value) {
  try { localStorage.setItem(key, String(value)); } catch (err) { /* private mode */ }
}

/* ---------- feature flags and settings ---------- */

function feature(name) {
  const settings = state.settings;
  if (settings && settings.features && typeof settings.features[name] === 'boolean') return settings.features[name];
  const snapshotSettings = state.snapshot && state.snapshot.settings;
  if (snapshotSettings && snapshotSettings.features && typeof snapshotSettings.features[name] === 'boolean') {
    return snapshotSettings.features[name];
  }
  return true;
}

function projectSettings() {
  return state.settings || (state.snapshot && state.snapshot.settings) || {};
}

function settingsLabels() {
  const labels = projectSettings().labels;
  return Array.isArray(labels) ? labels : [];
}

function settingsPalette() {
  const palette = projectSettings().palette;
  return Array.isArray(palette) && palette.length ? palette : PALETTE_FALLBACK;
}

function settingsGroups() {
  const groups = projectSettings().groups;
  return Array.isArray(groups) && groups.length ? groups : GROUP_FALLBACK;
}

function settingsMe() {
  const settings = projectSettings();
  return settings.me || 'owner';
}

function featureDefaults() {
  const settings = state.settings;
  if (settings && settings.feature_defaults) return settings.feature_defaults;
  return { inbox: true, worklog: true, views: true, labels: true, timeline: false, cycles: false,
    modules: false, pages: false, intake: false, analytics: false, assistant: false };
}

function labelById(labelId) {
  return settingsLabels().find((label) => label.id === labelId) || null;
}

function labelChip(label, options) {
  if (!label) return null;
  const opts = options || {};
  const color = settingsPalette().indexOf(label.color) !== -1 ? label.color : 'neutral';
  return h('span', {
    class: 'label-chip lc-' + color + (opts.class ? ' ' + opts.class : ''),
    title: (label.title || label.id) + (label.group ? ' · ' + label.group : '')
  }, h('span', { class: 'dot' }), label.title || label.id);
}

function labelChips(labelIds, max) {
  const labels = (Array.isArray(labelIds) ? labelIds : []).map(labelById).filter(Boolean);
  const row = h('span', { class: 'label-row' });
  const shown = max ? labels.slice(0, max) : labels;
  for (const label of shown) row.appendChild(labelChip(label));
  if (max && labels.length > max) {
    row.appendChild(h('span', { class: 'label-chip lc-neutral', text: '+' + (labels.length - max) }));
  }
  return row;
}

function labelTitle(labelId) {
  const label = labelById(labelId);
  return label ? (label.title || labelId) : labelId;
}

function taskLabelIds(task) {
  return task && Array.isArray(task.labels) ? task.labels : [];
}

function paletteClass(color) {
  return 'lc-' + (settingsPalette().indexOf(color) !== -1 ? color : 'neutral');
}

function slugify(text) {
  return String(text || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 40);
}

function fmtHours(value) {
  const number = Number(value);
  if (!isFinite(number)) return '—';
  const rounded = Math.round(number * 10) / 10;
  return (Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1)) + 'h';
}

/* ---------- task effort (project worklog) ---------- */

function worklogRowFor(taskId) {
  const worklog = state.worklog;
  if (!worklog || !Array.isArray(worklog.tasks)) return null;
  return worklog.tasks.find((row) => row.id === taskId) || null;
}

function estimateOf(task) {
  return typeof task.estimate_hours === 'number' ? task.estimate_hours : null;
}

function actualOf(task) {
  const row = worklogRowFor(task.id);
  return row ? Number(row.actual_hours) || 0 : null;
}

function effortText(task) {
  const estimate = estimateOf(task);
  const actual = actualOf(task);
  const parts = [];
  if (estimate !== null) parts.push('est ' + fmtHours(estimate));
  if (actual !== null) parts.push('act ' + fmtHours(actual));
  return parts.join(' · ');
}

/* ---------- filters: the client mirror of core/filters.py ---------- */

function filterKind(field) {
  const api = state.filterFields;
  if (api && api.fields && api.fields[field]) return api.fields[field];
  return 'text';
}

function filterOperators(field) {
  const api = state.filterFields;
  const kind = filterKind(field);
  if (api && api.operators && Array.isArray(api.operators[kind])) return api.operators[kind];
  if (kind === 'bool' || kind === 'budget') return ['is'];
  if (kind === 'status') return ['is', 'is_not', 'any_of', 'none_of'];
  if (kind === 'label') return ['any_of', 'none_of', 'empty', 'not_empty'];
  if (kind === 'number') return ['eq', 'neq', 'gt', 'gte', 'lt', 'lte', 'empty', 'not_empty'];
  return ['is', 'is_not', 'contains', 'not_contains', 'empty', 'not_empty'];
}

function filterGroupByOptions() {
  const api = state.filterFields;
  return api && Array.isArray(api.group_by) ? api.group_by.filter(Boolean) : ['status', 'stage', 'package', 'owner', 'label'];
}

function filterSortableFields() {
  const api = state.filterFields;
  return api && Array.isArray(api.sortable) ? api.sortable
    : ['id', 'title', 'status', 'stage', 'package', 'owner', 'complexity', 'tokens', 'attempt'];
}

function statusOrder() {
  const api = state.filterFields;
  return api && Array.isArray(api.status_order) ? api.status_order : Object.keys(STATUS);
}

function budgetState(task) {
  const budget = task.budget || {};
  if (budget.over) return 'over';
  if (budget.warn) return 'warn';
  return 'ok';
}

function taskFieldValue(task, field) {
  switch (field) {
    case 'label': return taskLabelIds(task);
    case 'ready': return Boolean(task.ready);
    case 'running': return Boolean(task.running);
    case 'claimed': return Boolean(task.claim);
    case 'blocked': return task.status === 'blocked' || Boolean(task.blocked_reason);
    case 'budget': return budgetState(task);
    case 'review_verdict': return (task.review && task.review.verdict) || '';
    case 'estimate_hours':
      return typeof task.estimate_hours === 'number' ? task.estimate_hours : null;
    case 'complexity':
      return typeof task.complexity === 'number' ? task.complexity : null;
    case 'tokens': return typeof task.tokens === 'number' ? task.tokens : 0;
    case 'attempt': return typeof task.attempt === 'number' ? task.attempt : 0;
    case 'gates_missing':
      if (typeof task.gates_missing === 'number') return task.gates_missing;
      return Array.isArray(task.gates_missing) ? task.gates_missing.length : 0;
    default:
      return typeof task[field] === 'string' ? task[field] : '';
  }
}

function matchCondition(task, condition) {
  const field = condition.field;
  const op = condition.op;
  const expected = condition.value;
  const value = taskFieldValue(task, field);
  const kind = filterKind(field);
  if (op === 'empty') return value === null || value === '' || (Array.isArray(value) && !value.length);
  if (op === 'not_empty') return !(value === null || value === '' || (Array.isArray(value) && !value.length));
  if (kind === 'label') {
    const labels = Array.isArray(value) ? value : [];
    const wanted = Array.isArray(expected) ? expected : [];
    if (op === 'any_of') return wanted.some((item) => labels.indexOf(item) !== -1);
    if (op === 'none_of') return !wanted.some((item) => labels.indexOf(item) !== -1);
    return false;
  }
  if (kind === 'bool') return Boolean(value) === Boolean(expected);
  if (kind === 'number') {
    if (value === null || value === undefined) return false;
    const actual = Number(value);
    const target = Number(expected);
    if (!isFinite(actual) || !isFinite(target)) return false;
    if (op === 'eq') return actual === target;
    if (op === 'neq') return actual !== target;
    if (op === 'gt') return actual > target;
    if (op === 'gte') return actual >= target;
    if (op === 'lt') return actual < target;
    if (op === 'lte') return actual <= target;
    return false;
  }
  if (op === 'any_of' || op === 'none_of') {
    const wanted = (Array.isArray(expected) ? expected : []).map((item) => String(item).toLowerCase());
    const actual = String(value || '').toLowerCase();
    return op === 'any_of' ? wanted.indexOf(actual) !== -1 : wanted.indexOf(actual) === -1;
  }
  const actualText = String(value === null || value === undefined ? '' : value).toLowerCase();
  const wantedText = String(expected === null || expected === undefined ? '' : expected).toLowerCase();
  if (op === 'is') return actualText === wantedText;
  if (op === 'is_not') return actualText !== wantedText;
  if (op === 'contains') return actualText.indexOf(wantedText) !== -1;
  if (op === 'not_contains') return actualText.indexOf(wantedText) === -1;
  return false;
}

function matchAllConditions(task, conditions) {
  return (conditions || []).every((condition) => matchCondition(task, condition));
}

function sortKeyOf(value) {
  if (typeof value === 'number' && isFinite(value)) return [1, value, ''];
  if (value === null || value === undefined || value === '') return [1, 0, ''];
  return [0, 0, String(value).toLowerCase()];
}

function compareKeys(a, b) {
  for (let index = 0; index < 3; index += 1) {
    if (a[index] < b[index]) return -1;
    if (a[index] > b[index]) return 1;
  }
  return 0;
}

function sortTaskList(tasks, field, direction) {
  const sortField = field || 'id';
  const reverse = direction === 'desc';
  const decorated = tasks.map((task, index) => ({ task: task, index: index, key: sortKeyOf(taskFieldValue(task, sortField)) }));
  decorated.sort((left, right) => {
    const compared = compareKeys(left.key, right.key);
    if (compared) return reverse ? -compared : compared;
    return left.index - right.index;
  });
  return decorated.map((entry) => entry.task);
}

function groupTaskList(tasks, field) {
  if (!field) return [{ key: 'all', label: 'All', tasks: tasks }];
  const buckets = new Map();
  const push = (key, task) => {
    if (!buckets.has(key)) buckets.set(key, []);
    buckets.get(key).push(task);
  };
  for (const task of tasks) {
    if (field === 'label') {
      const labels = taskLabelIds(task);
      if (!labels.length) push('(none)', task);
      else for (const label of labels) push(label, task);
    } else {
      const value = taskFieldValue(task, field);
      push(String(value === null || value === undefined || value === '' ? '(none)' : value), task);
    }
  }
  let order;
  if (field === 'status') {
    order = statusOrder().filter((status) => buckets.has(status));
    for (const key of buckets.keys()) if (order.indexOf(key) === -1) order.push(key);
  } else {
    order = Array.from(buckets.keys());
  }
  return order.map((key) => ({
    key: key,
    label: key === '(none)' ? 'No ' + field : (field === 'label' ? (labelTitle(key) || key) : key),
    tasks: buckets.get(key)
  }));
}

function conditionValueText(condition) {
  const kind = filterKind(condition.field);
  const value = condition.value;
  if (NO_VALUE_OPERATORS.indexOf(condition.op) !== -1) return '';
  if (kind === 'status' && Array.isArray(value)) return value.map((status) => stMeta(status).label).join(', ');
  if (kind === 'label') return (Array.isArray(value) ? value : []).map(labelTitle).join(', ');
  if (kind === 'bool') return value ? 'true' : 'false';
  if (kind === 'number') return String(value);
  if (kind === 'budget') return String(value);
  return String(value === null || value === undefined ? '' : value);
}

function conditionText(condition) {
  const field = FIELD_LABELS[condition.field] || condition.field;
  const op = OPERATOR_LABELS[condition.op] || condition.op;
  const value = conditionValueText(condition);
  return field + ' ' + op + (value ? ' ' + value : '');
}

function defaultFilterValue(field, op) {
  if (NO_VALUE_OPERATORS.indexOf(op) !== -1) return undefined;
  const kind = filterKind(field);
  if (kind === 'status') return (op === 'any_of' || op === 'none_of') ? [] : 'pending';
  if (kind === 'label') return [];
  if (kind === 'bool') return true;
  if (kind === 'number') return '';
  if (kind === 'budget') return 'over';
  return '';
}

function defaultFilterDraft() {
  return { field: 'status', op: 'any_of', value: defaultFilterValue('status', 'any_of') };
}

function filterValueLabel(field) {
  const kind = filterKind(field);
  if (kind === 'status') return 'statuses';
  if (kind === 'label') return 'labels';
  return 'value';
}

/* ---------- localStorage-backed view/density preferences ---------- */

function currentView() {
  return (state.views.all || []).find((view) => view.id === state.activeViewId) || null;
}

function markCustomView() {
  if (!state.activeViewId) return;
  state.activeViewId = '';
  prefSet(PREF_VIEW, '');
}

function applyView(viewId) {
  const view = (state.views.all || []).find((item) => item.id === viewId);
  if (!view) {
    state.activeViewId = '';
    prefSet(PREF_VIEW, '');
    renderView();
    return;
  }
  state.activeViewId = view.id;
  prefSet(PREF_VIEW, view.id);
  state.structuredFilters = JSON.parse(JSON.stringify(view.filters || []));
  state.groupBy = view.group_by || 'status';
  state.sort = view.sort
    ? { field: view.sort.field || 'id', dir: view.sort.dir === 'desc' ? 'desc' : 'asc' }
    : { field: 'id', dir: 'asc' };
  state.filterEditorOpen = false;
  state.filterError = null;
  const kind = view.kind === 'table' ? 'table' : 'board';
  if ((state.route.view === 'board' || state.route.view === 'table') && state.route.view !== kind) navigate(kind);
  else renderView();
}

function applySavedViewPreferences() {
  const savedId = prefGet(PREF_VIEW, '');
  if (!savedId) return;
  const view = (state.views.all || []).find((item) => item.id === savedId);
  if (!view) {
    state.activeViewId = '';
    prefSet(PREF_VIEW, '');
    return;
  }
  state.activeViewId = view.id;
  state.structuredFilters = JSON.parse(JSON.stringify(view.filters || []));
  state.groupBy = view.group_by || 'status';
  state.sort = view.sort
    ? { field: view.sort.field || 'id', dir: view.sort.dir === 'desc' ? 'desc' : 'asc' }
    : { field: 'id', dir: 'asc' };
}

function restorePreferences() {
  state.density = prefGet(PREF_DENSITY, 'comfortable') === 'compact' ? 'compact' : 'comfortable';
  state.timelineMode = prefGet(PREF_TIMELINE_MODE, 'days') === 'weeks' ? 'weeks' : 'days';
}

function toggleDensity() {
  state.density = state.density === 'compact' ? 'comfortable' : 'compact';
  prefSet(PREF_DENSITY, state.density);
  renderView();
}

/* ---------- loaders for the 2.1 endpoints ---------- */

function syncFeatureRouting() {
  if (state.route.view === 'yourwork' && !feature('inbox')) navigate('board');
}

async function loadSettings() {
  try {
    state.settings = await api('/api/settings');
    state.settingsLoaded = true;
    state.settingsError = null;
    syncFeatureRouting();
  } catch (err) {
    state.settingsError = err;
  }
  return state.settings;
}

async function loadFilterFields() {
  try {
    state.filterFields = await api('/api/filters/fields');
  } catch (err) {
    state.filterFields = null;
  }
}

async function loadViews() {
  try {
    state.views = await api('/api/views');
    state.viewsLoaded = true;
    state.viewsError = null;
  } catch (err) {
    state.viewsError = err;
    state.views = { builtin: [], saved: [], all: [] };
  }
}

async function loadYourWork() {
  try {
    state.yourWork = await api('/api/me');
    state.yourWorkLoaded = true;
    state.yourWorkError = null;
  } catch (err) {
    state.yourWorkError = err;
  }
}

async function loadInbox(options) {
  const opts = options || {};
  try {
    const data = await api('/api/inbox' + (opts.unread ? '?unread=1' : ''));
    state.inbox = data;
    state.inboxItems = Array.isArray(data.items) ? data.items : [];
    state.inboxCounts = data.counts || { total: 0, unread: 0, high: 0 };
    state.inboxLoaded = true;
    state.inboxError = null;
  } catch (err) {
    state.inboxError = err;
  }
}

async function loadInboxCounts() {
  if (!feature('inbox')) return;
  try {
    const data = await api('/api/inbox?unread=1');
    state.inboxCounts = data.counts || { total: 0, unread: 0, high: 0 };
  } catch (err) {
    /* the bell simply keeps its last count */
  }
  renderBell();
  renderTabs();
}

async function loadWorklog() {
  if (!feature('worklog')) return;
  try {
    state.worklog = await api('/api/worklog');
    state.worklogLoaded = true;
    state.worklogError = null;
  } catch (err) {
    state.worklogError = err;
  }
}

/* ---------- inbox actions ---------- */

async function markInboxRead(ids, read) {
  const list = Array.isArray(ids) ? ids : [ids];
  if (!list.length) return;
  try {
    await api('/api/inbox/read', { method: 'POST', body: { ids: list, read: read !== false } });
    await Promise.all([loadInbox(), loadInboxCounts()]);
    if (state.route.view === 'yourwork') renderView();
  } catch (err) {
    toast('Inbox: ' + describeError(err), 'error');
  }
}

async function markAllInboxRead() {
  if (!feature('inbox')) return;
  try {
    await api('/api/inbox/read', { method: 'POST', body: { all: true } });
    await Promise.all([loadInbox(), loadInboxCounts()]);
    if (state.route.view === 'yourwork') renderView();
    toast('Inbox marked read', 'ok', 2200);
  } catch (err) {
    toast('Inbox: ' + describeError(err), 'error');
  }
}

function openInboxItem(item) {
  if (!item) return;
  if (!item.read && canWrite()) {
    api('/api/inbox/read', { method: 'POST', body: { ids: [item.id] } })
      .then(() => Promise.all([loadInbox(), loadInboxCounts()]))
      .then(() => { if (state.route.view === 'yourwork') renderView(); })
      .catch(() => { /* opening the target still works */ });
  }
  if (item.action === 'Open approvals') navigate('approvals');
  else if (item.action === 'Open sessions') navigate('sessions');
  else if (item.task) openTask(item.task);
}

/* =========================================================================
   2.2 — Planning loaders, dates and shared helpers
   ========================================================================= */

const PREF_TIMELINE_MODE = 'polier.timeline.mode';

/* ---------- date helpers (all dates are ISO YYYY-MM-DD from the API) ---------- */

function dateToUtc(value) {
  if (!value) return null;
  const text = String(value).slice(0, 10);
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(text);
  if (!match) return null;
  return Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
}

function dayIndexOf(date, start) {
  const a = dateToUtc(date);
  const b = dateToUtc(start);
  if (a === null || b === null) return 0;
  return Math.round((a - b) / 86400000);
}

function shortDay(value) {
  const stamp = dateToUtc(value);
  if (stamp === null) return '—';
  const date = new Date(stamp);
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', timeZone: 'UTC' });
}

function fullDay(value) {
  const stamp = dateToUtc(value);
  if (stamp === null) return '—';
  const date = new Date(stamp);
  return date.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' });
}

function monthLabel(value) {
  const stamp = dateToUtc(value);
  if (stamp === null) return '';
  return new Date(stamp).toLocaleDateString(undefined, { month: 'short', year: 'numeric', timeZone: 'UTC' });
}

function weekdayInitial(weekday) {
  return ['M', 'T', 'W', 'T', 'F', 'S', 'S'][Number(weekday) || 0] || '';
}

function timelineMode() {
  return state.timelineMode === 'weeks' ? 'weeks' : 'days';
}

function setTimelineMode(mode) {
  state.timelineMode = mode === 'weeks' ? 'weeks' : 'days';
  prefSet(PREF_TIMELINE_MODE, state.timelineMode);
  renderView();
}

/* ---------- 2.2 data loaders ---------- */

async function loadTimeline() {
  state.timelineLoading = true;
  try {
    state.timeline = await api('/api/timeline');
    state.timelineLoaded = true;
    state.timelineError = null;
  } catch (err) {
    state.timelineError = err;
    if (err.status === 409) state.noBoard = true;
  }
  state.timelineLoading = false;
}

async function loadCycles() {
  state.cyclesLoading = true;
  try {
    state.cycles = await api('/api/cycles');
    state.cyclesLoaded = true;
    state.cyclesError = null;
  } catch (err) {
    state.cyclesError = err;
  }
  state.cyclesLoading = false;
}

async function loadModules() {
  state.modulesLoading = true;
  try {
    state.modules = await api('/api/modules');
    state.modulesLoaded = true;
    state.modulesError = null;
  } catch (err) {
    state.modulesError = err;
  }
  state.modulesLoading = false;
}

async function loadCoverage() {
  state.coverageLoading = true;
  try {
    state.coverage = await api('/api/coverage');
    state.coverageLoaded = true;
    state.coverageError = null;
  } catch (err) {
    state.coverageError = err;
  }
  state.coverageLoading = false;
}

async function loadAnalytics() {
  state.analyticsLoading = true;
  try {
    state.analytics = await api('/api/analytics');
    state.analyticsLoaded = true;
    state.analyticsError = null;
  } catch (err) {
    state.analyticsError = err;
  }
  state.analyticsLoading = false;
}

/* Planning dates (board schema 1.2) come from the snapshot task views (2.2+);
   the read-only board.json endpoint is only a fallback for older payloads. */
async function loadPlanningDates(force) {
  if (state.planningDatesLoaded && !force) return state.planningDates;
  if (state.planningDatesLoading) return state.planningDates;
  if (state.snapshot && Array.isArray(state.snapshot.tasks)) {
    const map = {};
    for (const task of state.snapshot.tasks) {
      if (!task || !task.id) continue;
      map[task.id] = {
        planned_start: typeof task.planned_start === 'string' ? task.planned_start : null,
        target: typeof task.target === 'string' ? task.target : null
      };
    }
    state.planningDates = map;
    state.planningDatesLoaded = true;
    state.planningDatesError = null;
    return state.planningDates;
  }
  state.planningDatesLoading = true;
  try {
    const file = await api('/api/file?path=board.json');
    const board = JSON.parse((file && file.text) || '{}');
    const map = {};
    for (const task of Array.isArray(board.tasks) ? board.tasks : []) {
      if (!task || !task.id) continue;
      map[task.id] = {
        planned_start: typeof task.planned_start === 'string' ? task.planned_start : null,
        target: typeof task.target === 'string' ? task.target : null
      };
    }
    state.planningDates = map;
    state.planningDatesLoaded = true;
    state.planningDatesError = null;
  } catch (err) {
    state.planningDatesError = err;
  } finally {
    state.planningDatesLoading = false;
  }
  return state.planningDates;
}

function planningFor(taskId) {
  const map = state.planningDates || {};
  return map[taskId] || { planned_start: null, target: null };
}

function setPlanningFor(taskId, plannedStart, target) {
  if (!state.planningDates) state.planningDates = {};
  state.planningDates[taskId] = {
    planned_start: typeof plannedStart === 'string' && plannedStart ? plannedStart : null,
    target: typeof target === 'string' && target ? target : null
  };
  state.planningDatesLoaded = true;
}

/* ---------- small view helpers ---------- */

function tileValue(label, value, options) {
  const opts = options || {};
  const tile = h('div', { class: 'kpi-tile' },
    h('div', { class: 'kpi-label', text: label }),
    h('div', { class: 'kpi-value ' + (opts.tone || ''), text: String(value) }),
    opts.sub ? h('div', { class: 'kpi-sub', text: opts.sub }) : null);
  return tile;
}

function statTile(label, value, options) {
  const opts = options || {};
  return h('button', {
    class: 'tile ' + (opts.tone || ''),
    type: 'button',
    title: opts.title || label + ': ' + value,
    on: { click: opts.onClick || (() => {}) }
  }, h('span', { class: 'tile-value', text: String(value) }),
    h('span', { class: 'tile-label', text: label }),
    opts.sub ? h('span', { class: 'tile-sub', text: opts.sub }) : null);
}

function percentText(value) {
  const number = Number(value);
  if (!isFinite(number)) return '—';
  return Math.round(number * 1000) / 10 + '%';
}

function countText(value) {
  const number = Number(value);
  return isFinite(number) ? String(number) : '—';
}

function viewLoadingOrError(container, loaded, error, label) {
  if (!loaded && !error) {
    container.appendChild(loadingRow(label || 'Loading…'));
    return true;
  }
  if (!loaded && error) {
    container.appendChild(errorCallout(error));
    container.appendChild(h('div', { style: { marginTop: '10px' } },
      h('button', {
        class: 'btn', type: 'button', text: 'Retry',
        on: { click: () => { loadCurrentPlanningView(); } }
      })));
    return true;
  }
  return false;
}

function loadCurrentPlanningView() {
  const view = state.route.view;
  if (view === 'timeline') loadTimeline().then(renderView);
  else if (view === 'cycles') loadCycles().then(renderView);
  else if (view === 'modules') loadModules().then(renderView);
  else if (view === 'coverage') loadCoverage().then(renderView);
  else if (view === 'analytics') loadAnalytics().then(renderView);
  else renderView();
}

/* =========================================================================
   2.3 — Pages, Intake and task-template loaders and helpers
   ========================================================================= */

/* ---------- safe markdown links (internal .md links open the Pages viewer) ---------- */

function resolvePageLink(target, base) {
  if (!target) return null;
  let value = String(target).trim();
  if (!value) return null;
  if (/^[a-z][a-z0-9+.-]*:/i.test(value)) return null; /* external or unknown scheme */
  value = value.split('#')[0].split('?')[0];
  if (!value) return null;
  if (value.startsWith('/')) value = value.replace(/^\/+/, '');
  else {
    const baseParts = base ? String(base).split('/').slice(0, -1) : [];
    value = baseParts.concat([value]).join('/');
  }
  const parts = [];
  for (const part of value.split('/')) {
    if (!part || part === '.') continue;
    if (part === '..') { if (parts.length) parts.pop(); continue; }
    parts.push(part);
  }
  const resolved = parts.join('/');
  if (!resolved || !/\.md$/i.test(resolved)) return null;
  return resolved;
}

function markdownLink(label, url, options) {
  const opts = options || {};
  const inner = inlineNodes(label, opts);
  if (/^https?:\/\//i.test(url) || /^mailto:/i.test(url)) {
    return h('a', { href: url, rel: 'noopener noreferrer' }, inner);
  }
  if (url.startsWith('#')) return h('a', { href: url }, inner);
  const resolved = resolvePageLink(url, opts.linkBase);
  if (!resolved) return document.createTextNode(label);
  return h('a', {
    href: '#/pages/' + encodeURIComponent(resolved),
    dataset: { pageLink: resolved },
    title: 'Open ' + resolved
  }, inner);
}



/* ---------- Pages data ---------- */

async function loadPages() {
  state.pagesLoading = true;
  try {
    const results = await Promise.all([api('/api/pages'), api('/api/pages/favorites')]);
    state.pages = results[0];
    state.pageFavorites = Array.isArray(results[1].favorites) ? results[1].favorites : [];
    state.pagesLoaded = true;
    state.pagesError = null;
  } catch (err) {
    state.pagesError = err;
  }
  state.pagesLoading = false;
  ensurePagesSelection();
  return state.pages;
}

function pageExistsInIndex(path) {
  return Boolean(state.pages && (state.pages.pages || []).some((page) => page.path === path));
}

function pageByPath(path) {
  return (state.pages && (state.pages.pages || []).find((page) => page.path === path)) || null;
}

function ensurePagesSelection() {
  if (!state.pages) return null;
  if (state.pagesSelected && pageExistsInIndex(state.pagesSelected)) return state.pagesSelected;
  const favorites = (state.pageFavorites || []).filter((path) => pageExistsInIndex(path));
  const first = favorites[0] || (state.pages.pages && state.pages.pages[0] ? state.pages.pages[0].path : null);
  state.pagesSelected = first;
  state.pagesRef = null;
  return first;
}

async function loadPage(path, ref) {
  if (!path) { state.pageDetail = null; return; }
  state.pageLoading = true;
  try {
    const query = '/api/page?path=' + encodeURIComponent(path) + (ref ? '&ref=' + encodeURIComponent(ref) : '');
    state.pageDetail = await api(query);
    state.pageError = null;
  } catch (err) {
    state.pageError = err;
    state.pageDetail = null;
  }
  state.pageLoading = false;
}

function schedulePagesSearch(value) {
  state.pagesSearch = value;
  if (state.pagesSearchTimer) window.clearTimeout(state.pagesSearchTimer);
  const query = String(value || '').trim();
  if (query.length < 2) {
    state.pagesResults = [];
    state.pagesSearchError = null;
    state.pagesSearching = false;
    renderView();
    return;
  }
  state.pagesSearching = true;
  state.pagesSearchError = null;
  renderView();
  state.pagesSearchTimer = window.setTimeout(() => { runPagesSearch(query); }, 280);
}

async function runPagesSearch(query) {
  state.pagesSearchTimer = null;
  if (state.route.view !== 'pages') return;
  if (String(state.pagesSearch || '').trim() !== query) return;
  try {
    const result = await api('/api/pages/search?q=' + encodeURIComponent(query) + '&limit=30');
    state.pagesResults = result.results || [];
    state.pagesSearchError = null;
  } catch (err) {
    state.pagesResults = [];
    state.pagesSearchError = err;
  }
  state.pagesSearching = false;
  renderView();
}

async function togglePageFavorite(path) {
  if (!canWrite() || !path) return;
  const favorites = (state.pageFavorites || []).slice();
  const index = favorites.indexOf(path);
  if (index >= 0) favorites.splice(index, 1);
  else favorites.push(path);
  try {
    await api('/api/pages/favorites', { method: 'PUT', body: { favorites: favorites } });
    await loadPages();
    if (state.pagesSelected) await loadPage(state.pagesSelected, state.pagesRef);
    toast(index >= 0 ? 'Removed from favorites' : 'Added to favorites', 'ok', 1800);
    renderView();
  } catch (err) {
    toast('Favorites: ' + describeError(err), 'error');
  }
}

function pageKindLabel(kind) {
  return { root: 'root', doc: 'doc', task: 'brief', review: 'review', package: 'package' }[kind] || kind;
}

function pageKindChip(kind) {
  const tone = { root: 'blue', doc: 'violet', task: 'green', review: 'amber', package: 'neutral' }[kind] || 'neutral';
  return h('span', { class: 'chip bg-' + tone + ' st-' + tone, text: pageKindLabel(kind) });
}

/* ---------- Intake data ---------- */

async function loadIntake() {
  state.intakeLoading = true;
  try {
    state.intake = await api('/api/intake');
    state.intakeLoaded = true;
    state.intakeError = null;
  } catch (err) {
    state.intakeError = err;
  }
  state.intakeLoading = false;
}

function intakeEntries() {
  return (state.intake && Array.isArray(state.intake.entries)) ? state.intake.entries : [];
}

function intakeCounts() {
  return (state.intake && state.intake.counts) || { proposed: 0, accepted: 0, rejected: 0 };
}

function intakeKindChip(kind) {
  const value = kind || 'idea';
  return h('span', { class: 'chip kind-' + value, text: value });
}

function intakePriorityChip(priority) {
  const value = priority || 'medium';
  return h('span', { class: 'chip prio-' + value, text: value + ' priority' });
}

function intakeStatusTone(status) {
  return { proposed: 'amber', accepted: 'green', rejected: 'red' }[status] || 'neutral';
}

function intakeStatusPill(status) {
  const tone = intakeStatusTone(status);
  return h('span', { class: 'badge bg-' + tone + ' st-' + tone }, h('span', { class: 'dot' }), status);
}

/* ---------- Task templates ---------- */

async function loadTaskTemplates() {
  try {
    const result = await api('/api/task-templates');
    state.templates = Array.isArray(result.templates) ? result.templates : [];
    state.templatesLoaded = true;
    state.templatesError = null;
  } catch (err) {
    state.templatesError = err;
  }
}

function templateById(templateId) {
  return (state.templates || []).find((template) => template.id === templateId) || null;
}

function templateChips(template) {
  const chips = h('div', { class: 'template-chips' });
  if (template.estimate_hours !== null && template.estimate_hours !== undefined) {
    chips.appendChild(h('span', { class: 'chip', text: 'est ' + fmtHours(template.estimate_hours) }));
  }
  if (template.complexity !== null && template.complexity !== undefined) {
    chips.appendChild(h('span', { class: 'chip', text: 'complexity ' + template.complexity }));
  }
  for (const gate of template.gates || []) chips.appendChild(h('span', { class: 'chip', text: gate }));
  for (const labelId of template.labels || []) {
    const label = labelById(labelId);
    if (label) chips.appendChild(labelChip(label));
    else chips.appendChild(h('span', { class: 'chip mono', text: labelId }));
  }
  return chips;
}

/* =========================================================================
   2.4 — Assistant, Automations, GitHub: loaders and helpers
   ========================================================================= */

/* ---------- assistant ---------- */

function assistantConversations() {
  return state.assistantConversations || [];
}

function assistantConversationById(conversationId) {
  return assistantConversations().find((conversation) => conversation.id === conversationId) || null;
}

function activeAssistantDetail() {
  return state.assistantDetail || null;
}

async function loadAssistantList() {
  try {
    const result = await api('/api/assistant');
    state.assistantConversations = Array.isArray(result.conversations) ? result.conversations : [];
    state.assistantLoaded = true;
    state.assistantError = null;
  } catch (err) {
    state.assistantError = err;
  }
}

async function loadAssistantConversation(conversationId, quiet) {
  if (!conversationId) { state.assistantDetail = null; return; }
  if (!quiet) state.assistantLoading = true;
  try {
    const conversation = await api('/api/assistant/' + encodeURIComponent(conversationId));
    if (state.assistantActive !== conversationId) return;
    state.assistantDetail = conversation;
    state.assistantError = null;
  } catch (err) {
    if (state.assistantActive !== conversationId) return;
    state.assistantError = err;
    state.assistantDetail = null;
  }
  state.assistantLoading = false;
}

function ensureAssistantActive() {
  const conversations = assistantConversations();
  if (state.assistantActive && conversations.some((conversation) => conversation.id === state.assistantActive)) {
    return state.assistantActive;
  }
  state.assistantActive = conversations.length ? conversations[0].id : null;
  state.assistantDetail = null;
  return state.assistantActive;
}

async function openAssistantConversation(conversationId) {
  state.assistantActive = conversationId;
  state.assistantError = null;
  await loadAssistantConversation(conversationId, false);
  renderView();
}

function assistantDraft() {
  return state.assistantDraft || '';
}

async function sendAssistantMessage(text) {
  const message = String(text === null || text === undefined ? state.assistantDraft : text).trim();
  if (message.length < 2) {
    state.assistantError = new ApiError('Write a question first (at least 2 characters).', 400, null);
    renderView();
    return;
  }
  state.assistantSending = true;
  state.assistantError = null;
  state.assistantDraft = '';
  renderView();
  try {
    const conversation = await api('/api/assistant/chat', {
      method: 'POST',
      body: { message: message, conversation_id: state.assistantActive || undefined }
    });
    state.assistantActive = conversation.id;
    state.assistantDetail = conversation;
    await loadAssistantList();
    renderView();
    if (state.route.view === 'assistant') startViewTimers();
  } catch (err) {
    state.assistantError = err;
    state.assistantDraft = message;
    renderView();
  } finally {
    state.assistantSending = false;
  }
}

async function pollAssistantConversation() {
  const detail = state.assistantDetail;
  if (!detail || !detail.id || !detail.pending) return;
  if (state.assistantPolling) return;
  state.assistantPolling = true;
  try {
    const conversation = await api('/api/assistant/' + encodeURIComponent(detail.id));
    if (state.assistantActive !== conversation.id) return;
    const previousMessages = (detail.messages || []).length;
    state.assistantDetail = conversation;
    if (!conversation.pending) await loadAssistantList();
    if (!conversation.pending || (conversation.messages || []).length !== previousMessages) renderView();
  } catch (err) {
    state.assistantError = err;
  } finally {
    state.assistantPolling = false;
  }
}

async function cancelAssistantAnswer() {
  const detail = state.assistantDetail;
  if (!detail) return;
  try {
    const conversation = await api('/api/assistant/' + encodeURIComponent(detail.id) + '/cancel', { method: 'POST', body: {} });
    state.assistantDetail = conversation;
    await loadAssistantList();
    renderView();
    toast('Answer cancelled', 'ok', 2000);
  } catch (err) {
    toast('Cancel failed: ' + describeError(err), 'error');
  }
}

async function deleteAssistantConversation(conversationId) {
  const conversation = assistantConversationById(conversationId);
  const confirmed = await confirmDialog({
    title: 'Delete conversation?',
    message: 'The conversation "' + ((conversation && conversation.title) || conversationId) + '" is removed from the local runtime folder.',
    confirmLabel: 'Delete conversation'
  });
  if (!confirmed) return;
  try {
    await api('/api/assistant/' + encodeURIComponent(conversationId), { method: 'DELETE' });
    if (state.assistantActive === conversationId) {
      state.assistantActive = null;
      state.assistantDetail = null;
    }
    await loadAssistantList();
    ensureAssistantActive();
    if (state.assistantActive) await loadAssistantConversation(state.assistantActive, true);
    renderView();
    toast('Conversation deleted', 'ok');
  } catch (err) {
    toast('Delete failed: ' + describeError(err), 'error');
  }
}

function assistantProposalKey(messageIndex, proposalIndex) {
  return (state.assistantActive || 'none') + ':' + messageIndex + ':' + proposalIndex;
}

function proposalDismissed(messageIndex, proposalIndex) {
  return Boolean(state.assistantDismissed && state.assistantDismissed[assistantProposalKey(messageIndex, proposalIndex)]);
}

function dismissAssistantProposal(messageIndex, proposalIndex) {
  if (!state.assistantDismissed) state.assistantDismissed = {};
  state.assistantDismissed[assistantProposalKey(messageIndex, proposalIndex)] = true;
  renderView();
}

function assistantProposalKindTone(kind) {
  return {
    state: 'blue', plan_task: 'violet', gate: 'green', session: 'amber', note: 'neutral'
  }[kind] || 'neutral';
}

async function applyAssistantProposal(proposal, messageIndex, proposalIndex) {
  if (!proposal || !canWrite()) return;
  const confirmed = await confirmDialog({
    title: 'Apply proposal?',
    message: (proposal.title || proposal.kind) + (proposal.reason ? '\n\n' + proposal.reason : '') + '\n\nThis runs the normal validated action. You can revert it through the usual tools.',
    confirmLabel: 'Apply proposal'
  });
  if (!confirmed) return;
  state.assistantApplying = assistantProposalKey(messageIndex, proposalIndex);
  state.assistantApplyResult = null;
  state.assistantError = null;
  renderView();
  try {
    const result = await api('/api/assistant/apply', {
      method: 'POST',
      body: { conversation_id: state.assistantActive || undefined, proposal: proposal }
    });
    state.assistantApplyResult = {
      proposal: proposal,
      result: result && result.result ? result.result : result,
      at: new Date().toISOString()
    };
    if (state.assistantActive) await loadAssistantConversation(state.assistantActive, true);
    await Promise.all([loadAssistantList(), loadSnapshot()]);
    renderHeader();
    renderView();
    toast('Applied: ' + (proposal.title || proposal.kind), 'ok');
  } catch (err) {
    state.assistantError = err;
    renderView();
  } finally {
    state.assistantApplying = null;
  }
}

/* ---------- automations ---------- */

function loadExampleAutomations() {
  return {
    version: 1,
    rules: [
      {
        id: 'gate-failed', name: 'A failed gate needs attention', enabled: true,
        when: { kind: 'gate_failed' },
        actions: [
          { type: 'state', status: 'blocked', note: 'A gate failed; fix it before continuing.' },
          { type: 'open' }
        ]
      },
      {
        id: 'review-waiting', name: 'A task waits for review', enabled: true,
        when: { kind: 'review_ready' },
        actions: [{ type: 'session', role: 'reviewer', note: 'Review the diff, acceptance criteria and gate records.' }]
      },
      {
        id: 'stage-decision', name: 'A stage is ready for the owner decision', enabled: true,
        when: { kind: 'stage_decision_pending' },
        actions: [{ type: 'open' }]
      }
    ]
  };
}

async function loadAutomations() {
  state.automationsLoading = true;
  try {
    const result = await api('/api/automations');
    state.automations = result;
    state.automationsLoaded = true;
    state.automationsEditor = JSON.stringify(result.automations || { version: 1, rules: [] }, null, 2);
    state.automationsError = null;
  } catch (err) {
    state.automationsError = err;
  }
  state.automationsLoading = false;
}

async function saveAutomations(value) {
  try {
    const result = await api('/api/automations', { method: 'PUT', body: value });
    state.automations = Object.assign({}, state.automations || {}, {
      automations: result.automations,
      errors: result.errors || []
    });
    state.automationsEditor = JSON.stringify(result.automations || value, null, 2);
    state.automationsEditorError = null;
    state.automationsError = null;
    await loadSnapshot();
    renderView();
    toast('Automations saved', 'ok');
    return true;
  } catch (err) {
    state.automationsError = err;
    renderView();
    return false;
  }
}

function automationRuleList() {
  return (state.automations && state.automations.automations && state.automations.automations.rules) || [];
}

function automationKinds() {
  return (state.automations && state.automations.kinds) || [];
}

async function toggleAutomationRule(ruleId, enabled) {
  const current = state.automations && state.automations.automations;
  if (!current) return;
  const value = JSON.parse(JSON.stringify(current));
  const rule = (value.rules || []).find((entry) => entry.id === ruleId);
  if (!rule) return;
  rule.enabled = Boolean(enabled);
  await saveAutomations(value);
}

async function runAutomations() {
  state.automationsRunning = true;
  state.automationsError = null;
  renderView();
  try {
    const run = canWrite()
      ? await api('/api/automations/run', { method: 'POST', body: {} })
      : await api('/api/automations/run');
    state.automationsRun = run;
  } catch (err) {
    state.automationsError = err;
  }
  state.automationsRunning = false;
  renderView();
}

async function saveAutomationsEditor(text) {
  let parsed;
  try {
    parsed = JSON.parse(text);
  } catch (err) {
    state.automationsEditorError = new ApiError('automations.json is not valid JSON: ' + err.message, 400, null);
    state.automationsEditor = text;
    renderView();
    return;
  }
  state.automationsEditor = text;
  await saveAutomations(parsed);
}

function automationEventText(event) {
  if (!event) return 'event';
  const parts = [event.kind];
  if (event.task) parts.push('task ' + event.task);
  if (event.gate) parts.push('gate ' + event.gate);
  if (event.stage) parts.push('stage ' + event.stage);
  if (event.intake) parts.push('intake ' + event.intake);
  if (event.session) parts.push('session ' + event.session);
  if (event.days !== null && event.days !== undefined) parts.push(event.days + ' day(s)');
  if (event.detail) parts.push('— ' + event.detail);
  return parts.join(' · ');
}

function automationOpenTarget(match) {
  const event = (match && match.event) || {};
  if (event.task) { openTask(event.task); return; }
  if (event.intake) { navigate('intake'); return; }
  if (event.stage) { navigate('plan'); return; }
  if (event.session) { navigate('sessions'); return; }
  navigate('board');
}

async function applyAutomationAction(match, action) {
  if (!canWrite() || !action) return;
  if (action.type === 'open') { automationOpenTarget(match); return; }
  if (action.type === 'note') {
    copyText(action.text || (match && match.name) || '');
    return;
  }
  const taskId = match && match.event ? match.event.task : null;
  if (!taskId) { toast('This match has no task to act on', 'warn'); return; }
  if (action.type === 'state') {
    const confirmed = await confirmDialog({
      title: 'Set ' + taskId + ' to ' + (action.status || '?') + '?',
      message: 'Suggested by rule "' + (match.name || match.rule) + '". This runs POST /api/tasks/' + taskId + '/state.',
      confirmLabel: 'Apply transition'
    });
    if (!confirmed) return;
    try {
      await api('/api/tasks/' + encodeURIComponent(taskId) + '/state', {
        method: 'POST',
        body: { status: action.status, note: action.note || 'automation: ' + (match.rule || '') }
      });
      await Promise.all([loadSnapshot(), runAutomations()]);
      renderHeader();
      renderView();
      toast(taskId + ' → ' + action.status, 'ok');
    } catch (err) {
      toast('Automation action failed: ' + describeError(err), 'error');
    }
    return;
  }
  if (action.type === 'session') {
    const confirmed = await confirmDialog({
      title: 'Start a ' + (action.role || 'worker') + ' session for ' + taskId + '?',
      message: 'Suggested by rule "' + (match.name || match.rule) + '". This starts a headless session through POST /api/sessions.',
      confirmLabel: 'Start session'
    });
    if (!confirmed) return;
    try {
      await api('/api/sessions', {
        method: 'POST',
        body: { task: taskId, role: action.role || 'worker', note: action.note || '' }
      });
      await Promise.all([loadSessions({ quiet: true })]);
      renderView();
      toast('Session started', 'ok');
    } catch (err) {
      toast('Session failed: ' + describeError(err), 'error');
    }
  }
}

/* ---------- GitHub ---------- */

async function loadGithub(force) {
  state.githubLoading = true;
  state.githubError = null;
  renderView();
  try {
    state.github = await api('/api/github' + (force ? '?force=1' : ''));
    state.githubLoaded = true;
  } catch (err) {
    state.githubError = err;
  }
  state.githubLoading = false;
  renderView();
}

function githubCheckBadge(checks) {
  const value = checks || 'none';
  const label = { pass: 'checks pass', fail: 'checks fail', pending: 'checks pending', none: 'no checks' }[value] || value;
  return h('span', { class: 'ci-badge ci-' + value, text: label });
}

function githubRunTone(run) {
  if (!run) return 'none';
  if (String(run.status) !== 'completed') return 'pending';
  const conclusion = String(run.conclusion || '').toLowerCase();
  if (conclusion === 'success') return 'pass';
  if (conclusion) return 'fail';
  return 'none';
}

/* =========================================================================
   9. Application state
   ========================================================================= */

const state = {
  config: null,
  snapshot: null,
  snapshotError: null,
  noBoard: false,

  route: { view: 'board', taskId: null },

  filters: { text: '', stage: '', package: '', owner: '' },
  boardDoneOpen: false,

  drawer: {
    id: null,
    tab: 'brief',
    detail: null,
    loading: false,
    error: null,
    note: '',
    gate: { name: '', command: '', timeout: '1800' },
    actionError: null,
    busy: null,
    evidenceLog: null,
    watch: null
  },

  dispatch: null,
  dispatchLoading: false,

  approvals: [],
  approvalsLoaded: false,
  approvalFilter: 'pending',
  approvalFormOpen: false,
  approvalBusy: null,

  activity: [],
  activityTask: '',
  activityLoaded: false,

  sessions: [],
  sessionsLoaded: false,
  sessionSelected: null,
  viewWatch: null,

  jobs: [],
  jobsLoaded: false,
  jobsOpen: false,

  plan: null,
  planLoaded: false,
  planError: null,
  planBusy: null,
  interviewOpen: false,
  generator: null,

  graph: { zoom: 1 },
  packageOptions: null,

  /* 2.1 cockpit state */
  settings: null,
  settingsLoaded: false,
  settingsError: null,
  settingsUI: null,
  health: null,
  filterFields: null,
  views: { builtin: [], saved: [], all: [] },
  viewsLoaded: false,
  viewsError: null,
  activeViewId: '',
  structuredFilters: [],
  groupBy: 'status',
  sort: { field: 'id', dir: 'asc' },
  density: 'comfortable',
  filterEditorOpen: false,
  filterDraft: null,
  filterError: null,
  yourWork: null,
  yourWorkLoaded: false,
  yourWorkError: null,
  inbox: null,
  inboxItems: [],
  inboxCounts: { total: 0, unread: 0, high: 0 },
  inboxLoaded: false,
  inboxError: null,
  worklog: null,
  worklogLoaded: false,
  worklogError: null,

  /* 2.2 planning views */
  timeline: null,
  timelineLoaded: false,
  timelineLoading: false,
  timelineError: null,
  timelineMode: 'days',
  cycles: null,
  cyclesLoaded: false,
  cyclesLoading: false,
  cyclesError: null,
  cyclesBusy: null,
  modules: null,
  modulesLoaded: false,
  modulesLoading: false,
  modulesError: null,
  coverage: null,
  coverageLoaded: false,
  coverageLoading: false,
  coverageError: null,
  coverageFilter: 'all',
  analytics: null,
  analyticsLoaded: false,
  analyticsLoading: false,
  analyticsError: null,
  planningDates: {},
  planningDatesLoaded: false,
  planningDatesLoading: false,
  planningDatesError: null,

  /* 2.3 pages, intake and task templates */
  pages: null,
  pagesLoaded: false,
  pagesLoading: false,
  pagesError: null,
  pagesSelected: null,
  pagesRef: null,
  pagesCollapsed: {},
  pagesSearch: '',
  pagesResults: [],
  pagesSearching: false,
  pagesSearchError: null,
  pagesSearchTimer: null,
  pageFavorites: [],
  pageDetail: null,
  pageLoading: false,
  pageError: null,
  intake: null,
  intakeLoaded: false,
  intakeLoading: false,
  intakeError: null,
  intakeFilter: 'proposed',
  intakeBusy: null,
  templates: null,
  templatesLoaded: false,
  templatesError: null,

  /* 2.4 assistant, automations, GitHub, bulk and palette */
  assistantConversations: [],
  assistantLoaded: false,
  assistantActive: null,
  assistantDetail: null,
  assistantLoading: false,
  assistantSending: false,
  assistantPolling: false,
  assistantApplying: null,
  assistantDraft: '',
  assistantDismissed: {},
  assistantApplyResult: null,
  assistantError: null,
  assistantApplyError: null,
  focusAssistantInput: false,
  automations: null,
  automationsLoaded: false,
  automationsLoading: false,
  automationsError: null,
  automationsEditor: '',
  automationsEditorError: null,
  automationsRunning: false,
  automationsRun: null,
  github: null,
  githubLoaded: false,
  githubLoading: false,
  githubError: null,
  bulk: { selected: [], status: 'blocked', note: '', labels: [], estimate: '', labelsOpen: false, busy: false }
};

const dom = {
  view: document.getElementById('view'),
  tabs: document.getElementById('tabs'),
  headerMeta: document.getElementById('header-meta'),
  projectName: document.getElementById('project-name'),
  search: document.getElementById('global-search'),
  live: document.getElementById('live-indicator'),
  liveLabel: document.getElementById('live-label'),
  themeButton: document.getElementById('btn-theme'),
  inboxButton: document.getElementById('btn-inbox'),
  bellCount: document.getElementById('bell-count'),
  checkButton: document.getElementById('btn-check'),
  auditButton: document.getElementById('btn-audit'),
  drawer: document.getElementById('drawer'),
  drawerBackdrop: document.getElementById('drawer-backdrop'),
  modalBackdrop: document.getElementById('modal-backdrop'),
  modal: document.getElementById('modal'),
  toasts: document.getElementById('toasts'),
  jobs: document.getElementById('jobs'),
  jobsBody: document.getElementById('jobs-body'),
  jobsSummary: document.getElementById('jobs-summary'),
  jobsDot: document.getElementById('jobs-dot'),
  jobsToggle: document.getElementById('jobs-toggle'),
  jobsChevron: document.getElementById('jobs-chevron')
};

/* Timers: view timers are cleared on every route change; drawer timers when the
   drawer closes. */
let viewTimers = [];
let drawerTimers = [];
let jobsPollTimer = null;
let refreshTimer = null;
let searchTimer = null;
let searchFocusTimer = null;

function setViewInterval(fn, ms) {
  const id = window.setInterval(fn, ms);
  viewTimers.push(id);
  return id;
}

function clearViewTimers() {
  for (const id of viewTimers) window.clearInterval(id);
  viewTimers = [];
  state.viewWatch = null;
}

function setDrawerInterval(fn, ms) {
  const id = window.setInterval(fn, ms);
  drawerTimers.push(id);
  return id;
}

function clearDrawerTimers() {
  for (const id of drawerTimers) window.clearInterval(id);
  drawerTimers = [];
  if (state.drawer.watch) state.drawer.watch.timer = null;
}

/* =========================================================================
   10. Small shared UI builders
   ========================================================================= */

function pill(label, extraClass, title) {
  return h('span', { class: 'pill ' + (extraClass || ''), title: title || '' }, h('span', { class: 'truncate', text: label }));
}

function mono(text, extraClass) {
  return h('span', { class: 'mono ' + (extraClass || ''), text: text });
}

function emptyState(title, body, actions) {
  return h('div', { class: 'empty' },
    h('div', { class: 'empty-icon', text: '◇' }),
    h('div', { class: 'empty-title', text: title }),
    body ? h('div', { class: 'empty-body', text: body }) : null,
    actions ? h('div', { class: 'row', style: { marginTop: '4px' } }, actions) : null);
}

function loadingRow(label) {
  return h('div', { class: 'loading-row' }, h('span', { class: 'spinner' }), h('span', { text: label || 'Loading…' }));
}

function progressBar(done, total, extraClass) {
  const pct = total > 0 ? Math.max(0, Math.min(100, (done / total) * 100)) : 0;
  return h('div', { class: 'bar ' + (extraClass || '') },
    h('span', { style: { width: pct.toFixed(1) + '%' } }));
}

function tokenBar(task) {
  const budget = task.budget || {};
  const used = Number(task.tokens) || 0;
  const max = Number(budget.max) || 0;
  const classes = max ? (budget.over ? 'is-over' : (budget.warn ? 'is-warn' : '')) : '';
  if (!max) {
    return h('div', { class: 'task-card-line' },
      h('span', { text: 'tokens' }),
      h('span', { class: 'mono', text: fmtTokens(used) }));
  }
  return h('div', { class: 'task-card-foot' },
    h('div', { class: 'task-card-line' },
      h('span', { text: 'tokens' }),
      h('span', { class: 'mono', text: fmtTokens(used) + ' / ' + fmtTokens(max) })),
    progressBar(used, max, classes));
}

function statusCounts(tasks) {
  const counts = {};
  for (const task of tasks || []) counts[task.status || '?'] = (counts[task.status || '?'] || 0) + 1;
  return counts;
}

function taskById(taskId) {
  if (!state.snapshot) return null;
  return (state.snapshot.tasks || []).find((task) => task.id === taskId) || null;
}

function openTask(taskId) {
  if (!taskId) return;
  if (state.route.view === 'pages') {
    const base = state.pagesSelected ? '#/pages/' + encodeURIComponent(state.pagesSelected) : '#/pages';
    const target = base + '?task=' + encodeURIComponent(taskId);
    if (location.hash === target) applyRoute();
    else location.hash = target;
    return;
  }
  const route = state.route.view === 'plan' ? 'board' : state.route.view;
  navigate(route, taskId);
}

function taskChip(taskId, title) {
  if (!taskId) return h('span', { class: 'chip', text: '—' });
  const task = taskById(taskId);
  return h('button', {
    class: 'chip chip-link', type: 'button',
    title: title || (task ? task.title : taskId),
    on: { click: (event) => { event.stopPropagation(); openTask(taskId); } }
  }, h('span', { class: 'mono', text: taskId }));
}

/* =========================================================================
   11. Routing
   ========================================================================= */

function parseHash() {
  const raw = location.hash || '';
  if (!raw.startsWith('#/')) return { view: 'board', taskId: null, drawer: null };
  let body = raw.slice(2);
  let drawer = null;
  const queryAt = body.indexOf('?');
  if (queryAt !== -1) {
    try {
      const query = new URLSearchParams(body.slice(queryAt + 1));
      drawer = query.get('task') || null;
    } catch (err) {
      drawer = null;
    }
    body = body.slice(0, queryAt);
  }
  const parts = body.split('/').filter(Boolean);
  const known = VIEWS.some((view) => view.key === parts[0]);
  const view = known ? parts[0] : 'board';
  let taskId = null;
  if (parts[1]) {
    try { taskId = decodeURIComponent(parts[1]); } catch (err) { taskId = parts[1]; }
  }
  return { view: view, taskId: taskId, drawer: drawer };
}

function navigate(view, taskId) {
  const target = '#/' + view + (taskId ? '/' + encodeURIComponent(taskId) : '');
  if (location.hash === target) {
    applyRoute();
    return;
  }
  location.hash = target;
}

function applyRoute() {
  const parsed = parseHash();
  const changedView = state.route.view !== parsed.view;
  state.route = { view: parsed.view, taskId: parsed.taskId };
  if (changedView) {
    clearViewTimers();
    closeAllModals();
  }
  renderTabs();
  renderHeader();
  syncSearchInput();

  if (parsed.view === 'pages') {
    if (parsed.taskId && state.pagesSelected !== parsed.taskId) {
      state.pagesSelected = parsed.taskId;
      state.pagesRef = null;
    }
    if (parsed.drawer) ensureDrawer(parsed.drawer);
    else closeDrawer(false);
    renderView();
    loadViewData('pages');
    startViewTimers();
    return;
  }

  renderView();
  if (parsed.drawer) ensureDrawer(parsed.drawer);
  else if (parsed.taskId) ensureDrawer(parsed.taskId);
  else closeDrawer(false);

  loadViewData(parsed.view);
  startViewTimers();
}

function startViewTimers() {
  clearViewTimers();
  if (state.route.view === 'sessions') {
    setViewInterval(() => loadSessions({ quiet: true }), 2600);
    if (state.sessionSelected) startViewSessionWatch(state.sessionSelected);
  }
  if (state.route.view === 'yourwork') {
    setViewInterval(async () => {
      await Promise.all([loadYourWork(), loadInboxCounts(), loadInbox()]);
      if (state.route.view === 'yourwork') renderView();
    }, 30000);
  }
  if (state.route.view === 'assistant') {
    setViewInterval(() => pollAssistantConversation(), 1000);
  }
}

/* =========================================================================
   12. Header, tabs, live indicator
   ========================================================================= */

/* =========================================================================
   2.1 — boot, routing, header, tabs, SSE and refresh
   ========================================================================= */

async function loadHealth() {
  try {
    state.health = await api('/api/health');
  } catch (err) {
    state.health = null;
  }
}

function renderBell() {
  const bell = document.getElementById('btn-inbox');
  const count = document.getElementById('bell-count');
  if (!bell || !count) return;
  if (!feature('inbox')) {
    bell.hidden = true;
    return;
  }
  bell.hidden = false;
  const unread = Number(state.inboxCounts && state.inboxCounts.unread) || 0;
  const high = Number(state.inboxCounts && state.inboxCounts.high) || 0;
  count.hidden = unread <= 0;
  count.textContent = unread > 99 ? '99+' : String(unread);
  count.className = 'bell-count' + (high ? ' is-high' : '');
  bell.title = unread
    ? unread + ' unread inbox item' + (unread === 1 ? '' : 's') + (high ? ' · ' + high + ' high' : '')
    : 'Inbox is empty';
  bell.setAttribute('aria-label', unread ? 'Open your inbox (' + unread + ' unread)' : 'Open your inbox');
}

function renderHeader() {
  const snapshot = state.snapshot;
  const config = state.config;
  const project = (snapshot && snapshot.project) || {};
  const git = (snapshot && snapshot.git) || {};
  const readOnly = Boolean((config && config.read_only) || (snapshot && snapshot.dashboard && snapshot.dashboard.read_only));

  const name = project.name || (config && config.project_root ? basename(config.project_root) : '') || 'dashboard';
  dom.projectName.textContent = name;
  document.title = name + ' — Polier';

  clear(dom.headerMeta);
  if (project.profile) dom.headerMeta.appendChild(pill('profile ' + project.profile, '', 'Board profile'));
  if (project.stage !== null && project.stage !== undefined && project.stage !== '') {
    dom.headerMeta.appendChild(pill('stage ' + project.stage, '', 'Current board stage'));
  }
  if (git.branch) {
    const dirty = Boolean(git.dirty);
    const changedCount = Array.isArray(git.changed) ? git.changed.length : 0;
    const branch = h('span', {
      class: 'pill',
      title: dirty
        ? 'Working tree has uncommitted changes' + (changedCount ? ' (' + changedCount + ' file' + (changedCount === 1 ? '' : 's') + ')' : '')
        : 'Working tree is clean'
    },
      h('span', { class: 'truncate', text: git.branch }),
      dirty ? h('span', { class: 'dirty-dot', 'aria-label': 'dirty' }) : null);
    dom.headerMeta.appendChild(branch);
  }
  if (readOnly) {
    dom.headerMeta.appendChild(pill('read-only', 'pill-readonly', 'The dashboard refuses every write'));
  } else if (config && config.role && config.role !== 'lead') {
    dom.headerMeta.appendChild(pill(config.role, '', 'Dashboard role'));
  }
  if (config && config.token_required) {
    dom.headerMeta.appendChild(pill('token', '', 'This dashboard requires a bearer token'));
  }
  if (state.settingsLoaded || (snapshot && snapshot.settings)) {
    dom.headerMeta.appendChild(pill('me ' + settingsMe(), '', 'Your handle in Settings → General'));
  }
  if (config && config.version) dom.projectName.title = 'Polier dashboard ' + config.version;
  const writable = canWrite();
  dom.checkButton.disabled = !writable;
  dom.auditButton.disabled = !writable;
  dom.checkButton.title = writable ? 'Run the board check job (POST /api/jobs/check)' : 'The dashboard is read-only';
  dom.auditButton.title = writable ? 'Run the project audit job (POST /api/jobs/audit)' : 'The dashboard is read-only';
  paintJobsButtonState();
  renderBell();
}

function renderTabs() {
  clear(dom.tabs);
  const snapshot = state.snapshot;
  const counts = {
    approvals: snapshot && snapshot.approvals && snapshot.approvals.pending ? snapshot.approvals.pending.length : 0,
    yourwork: Number(state.inboxCounts && state.inboxCounts.unread) || 0
  };
  for (const view of VIEWS) {
    if (view.feature && !feature(view.feature)) continue;
    const tab = h('a', {
      class: 'tab',
      href: '#/' + view.key,
      'aria-current': state.route.view === view.key ? 'page' : null,
      dataset: { view: view.key }
    }, h('span', { text: view.label }));
    if (counts[view.key]) tab.appendChild(h('span', { class: 'tab-count', text: String(counts[view.key]) }));
    dom.tabs.appendChild(tab);
  }
}

function setLive(status, label) {
  dom.live.dataset.live = status;
  if (dom.liveLabel) dom.liveLabel.textContent = label;
  dom.live.title = status === 'live' ? 'Connected to /api/events' : (label || 'Server-Sent Events connection');
}

/* =========================================================================
   13. Server-Sent Events with exponential backoff
   ========================================================================= */

let eventSource = null;
let eventRetry = 0;
let eventReconnectTimer = null;

function connectEvents() {
  if (new URLSearchParams(location.search).get('noevents') === '1') {
    setLive('static', 'Static');
    return;
  }
  if (eventSource) {
    try { eventSource.close(); } catch (err) { /* ignore */ }
    eventSource = null;
  }
  setLive('connecting', eventRetry > 0 ? 'Reconnecting' : 'Connecting');
  let source;
  try {
    source = new EventSource(withToken('/api/events'));
  } catch (err) {
    scheduleReconnect();
    return;
  }
  eventSource = source;

  source.addEventListener('ready', () => {
    eventRetry = 0;
    setLive('live', 'Live');
  });
  source.addEventListener('state', () => scheduleRefresh());
  source.addEventListener('approval', () => scheduleRefresh());
  source.addEventListener('claim', () => scheduleRefresh());
  source.addEventListener('plan', () => { scheduleRefresh(); if (state.route.view === 'plan') loadPlan(); });
  source.addEventListener('settings', () => {
    loadSettings().then(() => {
      renderHeader();
      renderTabs();
      renderView();
    });
  });
  source.addEventListener('views', () => {
    loadViews().then(() => {
      if (state.route.view === 'board' || state.route.view === 'table') renderView();
    });
  });
  source.addEventListener('inbox', () => {
    loadInboxCounts();
    if (state.route.view === 'yourwork') loadInbox().then(() => { if (state.route.view === 'yourwork') renderView(); });
  });
  source.addEventListener('intake', () => {
    if (state.route.view === 'intake') loadIntake().then(() => { if (state.route.view === 'intake') renderView(); });
  });
  source.addEventListener('templates', () => {
    loadTaskTemplates().then(() => {
      if (state.route.view === 'settings' || state.route.view === 'plan' || state.route.view === 'intake') renderView();
    });
  });
  source.addEventListener('automations', () => {
    if (state.route.view === 'automations') loadAutomations().then(() => { if (state.route.view === 'automations') renderView(); });
  });
  source.addEventListener('assistant', () => {
    if (state.route.view !== 'assistant') return;
    loadAssistantList().then(() => {
      ensureAssistantActive();
      if (state.assistantActive) loadAssistantConversation(state.assistantActive, true).then(() => {
        if (state.route.view === 'assistant') renderView();
      });
    });
  });
  source.addEventListener('job', () => { loadJobs(); });
  source.addEventListener('session', (event) => {
    const payload = ssePayload(event);
    if (payload && payload.id && state.sessionsLoaded) {
      const index = state.sessions.findIndex((session) => session.id === payload.id);
      if (index >= 0) state.sessions[index] = payload;
      else state.sessions.unshift(payload);
      if (state.route.view === 'sessions') renderView();
    }
    if (state.sessionsLoaded) loadSessions({ quiet: true });
  });

  source.onerror = () => {
    if (eventSource !== source) return;
    setLive('offline', 'Reconnecting');
    try { source.close(); } catch (err) { /* ignore */ }
    eventSource = null;
    scheduleReconnect();
  };
}

function ssePayload(event) {
  if (!event || !event.data) return null;
  try {
    const parsed = JSON.parse(event.data);
    if (parsed && typeof parsed === 'object' && 'data' in parsed) return parsed.data;
    return parsed;
  } catch (err) {
    return null;
  }
}

function scheduleReconnect() {
  if (eventReconnectTimer) return;
  const delay = Math.min(30000, Math.round(800 * Math.pow(1.7, eventRetry)));
  eventRetry = Math.min(eventRetry + 1, 8);
  setLive(eventRetry > 2 ? 'offline' : 'connecting', eventRetry > 2 ? 'Offline' : 'Reconnecting');
  eventReconnectTimer = window.setTimeout(() => {
    eventReconnectTimer = null;
    connectEvents();
  }, delay);
}

/* =========================================================================
   14. Data loading
   ========================================================================= */

async function loadConfig() {
  try {
    state.config = await api('/api/config');
  } catch (err) {
    toast(describeError(err), 'error');
  }
  return state.config;
}

async function loadSnapshot(options) {
  const opts = options || {};
  try {
    const snapshot = await api('/api/snapshot' + (opts.fresh ? '?fresh=1' : ''));
    state.snapshot = snapshot;
    state.snapshotError = null;
    state.noBoard = false;
    if (snapshot && snapshot.dashboard && snapshot.dashboard.config && !state.config) state.config = snapshot.dashboard.config;
    return snapshot;
  } catch (err) {
    if (err.status === 409) {
      state.noBoard = true;
      state.snapshot = null;
      state.snapshotError = null;
    } else if (err.status === 401 || err.status === 403) {
      state.snapshotError = err;
    } else {
      state.snapshotError = err;
    }
    return null;
  }
}

async function loadDispatch() {
  state.dispatchLoading = true;
  try {
    state.dispatch = await api('/api/dispatch');
    state.snapshotError = null;
  } catch (err) {
    if (err.status === 409) state.noBoard = true;
    else toast('Dispatch: ' + describeError(err), 'error');
  }
  state.dispatchLoading = false;
}

async function loadPackageOptions() {
  if (state.packageOptions) return state.packageOptions;
  const tasks = (state.snapshot && state.snapshot.tasks) || [];
  const values = [];
  for (const task of tasks) {
    if (task.package && values.indexOf(task.package) === -1) values.push(task.package);
  }
  if (!values.length) {
    try {
      const entries = await api('/api/files?prefix=packages');
      for (const entry of Array.isArray(entries) ? entries : []) {
        if (entry && entry.dir && entry.path && values.indexOf(entry.path) === -1) values.push(entry.path);
      }
    } catch (err) { /* the package filter simply stays hidden */ }
  }
  values.sort();
  state.packageOptions = values;
  return values;
}

async function loadApprovals() {
  try {
    const records = await api('/api/approvals');
    state.approvals = Array.isArray(records) ? records : [];
    state.approvalsLoaded = true;
  } catch (err) {
    toast('Approvals: ' + describeError(err), 'error');
  }
}

async function loadActivity() {
  try {
    const items = await api('/api/activity?limit=200');
    state.activity = Array.isArray(items) ? items : [];
    state.activityLoaded = true;
  } catch (err) {
    toast('Activity: ' + describeError(err), 'error');
  }
}

async function loadSessions(options) {
  const opts = options || {};
  try {
    const sessions = await api('/api/sessions');
    state.sessions = Array.isArray(sessions) ? sessions : [];
    state.sessionsLoaded = true;
    if (!state.sessionSelected && state.sessions.length) state.sessionSelected = state.sessions[0].id;
    if (state.sessionSelected && !state.sessions.some((session) => session.id === state.sessionSelected)) {
      state.sessionSelected = state.sessions.length ? state.sessions[0].id : null;
    }
    if (!opts.quiet && state.route.view === 'sessions') renderView();
    else if (state.route.view === 'sessions') renderSessionConsoleOnly();
    if (state.route.view === 'sessions' && !state.viewWatch) {
      const running = state.sessions.find((session) => SESSION_ACTIVE.has(session.status));
      if (running) {
        state.sessionSelected = running.id;
        startViewSessionWatch(running.id);
      }
    }
    if (state.drawer.id && state.drawer.tab === 'session') {
      const signature = state.sessions.map((session) => session.id + ':' + session.status).join(',');
      if (signature !== state.sessionSignature) {
        state.sessionSignature = signature;
        renderDrawer();
      }
    }
  } catch (err) {
    if (!opts.quiet) toast('Sessions: ' + describeError(err), 'error');
  }
}

async function loadJobs() {
  try {
    const jobs = await api('/api/jobs');
    state.jobs = Array.isArray(jobs) ? jobs : [];
    state.jobsLoaded = true;
    state.jobsError = null;
  } catch (err) {
    if (!state.jobsError) {
      state.jobsError = err;
      toast('Jobs: ' + describeError(err), 'error');
    }
  }
  renderJobsTray();
  syncJobsPolling();
}

async function loadPlan() {
  try {
    state.plan = await api('/api/plan');
    state.planLoaded = true;
    state.planError = null;
  } catch (err) {
    state.planError = err;
  }
  return state.plan;
}

function scheduleRefresh() {
  if (refreshTimer) return;
  refreshTimer = window.setTimeout(() => {
    refreshTimer = null;
    refreshAll();
  }, 180);
}

async function refreshAll() {
  await loadConfig();
  await loadSnapshot();
  state.planningDatesLoaded = false;
  if (!state.packageOptions && !state.noBoard) await loadPackageOptions();
  await loadSettings();
  if (!state.viewsLoaded) await loadViews();
  loadInboxCounts();
  renderHeader();
  renderTabs();
  if (state.drawer.id) loadDrawer(state.drawer.id, true);
  const view = state.route.view;
  if (view === 'dispatch') await loadDispatch();
  else if (view === 'approvals') await loadApprovals();
  else if (view === 'activity') await loadActivity();
  else if (view === 'plan') await Promise.all([loadPlan(), loadTaskTemplates()]);
  else if (view === 'sessions') await loadSessions({ quiet: true });
  else if (view === 'yourwork') await Promise.all([loadYourWork(), loadInbox()]);
  else if (view === 'settings') await Promise.all([loadHealth(), loadTaskTemplates()]);
  else if (view === 'timeline') await loadTimeline();
  else if (view === 'cycles') await loadCycles();
  else if (view === 'modules') await loadModules();
  else if (view === 'coverage') await loadCoverage();
  else if (view === 'analytics') await loadAnalytics();
  else if (view === 'pages') {
    await loadPages();
    ensurePagesSelection();
    if (state.pagesSelected) await loadPage(state.pagesSelected, state.pagesRef);
  } else if (view === 'intake') await Promise.all([loadIntake(), loadTaskTemplates()]);
  else if (view === 'assistant') {
    await loadAssistantList();
    ensureAssistantActive();
    if (state.assistantActive) await loadAssistantConversation(state.assistantActive, true);
  } else if (view === 'automations') await loadAutomations();
  if ((view === 'board' || view === 'table') && feature('worklog')) await loadWorklog();
  renderView();
  renderJobsTray();
  if (state.jobsOpen) loadJobs();
}

async function loadViewData(view) {
  const startedView = view;
  const rerender = () => { if (state.route.view === startedView) renderView(); };
  const viewDef = VIEWS.find((entry) => entry.key === view);
  if (viewDef && viewDef.feature && !feature(viewDef.feature)) {
    if (!state.snapshot && !state.noBoard && !state.snapshotError) await loadSnapshot();
    return renderView();
  }

  if (view === 'dispatch') { await loadDispatch(); return rerender(); }
  if (view === 'approvals') {
    await Promise.all([(!state.snapshot && !state.noBoard && !state.snapshotError) ? loadSnapshot() : Promise.resolve(), loadApprovals()]);
    return rerender();
  }
  if (view === 'activity') { await loadActivity(); return rerender(); }
  if (view === 'sessions') { await loadSessions(); return rerender(); }
  if (view === 'plan') { await Promise.all([loadPlan(), loadSnapshot(), loadTaskTemplates()]); return rerender(); }
  if (view === 'yourwork') {
    await Promise.all([loadSnapshot(), loadYourWork(), loadInboxCounts(), loadInbox()]);
    return rerender();
  }
  if (view === 'settings') {
    await Promise.all([loadSettings(), loadConfig(), loadSnapshot(), loadViews(), loadHealth(), loadFilterFields(), loadTaskTemplates()]);
    return rerender();
  }
  if (view === 'timeline') { await Promise.all([loadSnapshot(), loadTimeline()]); return rerender(); }
  if (view === 'cycles') { await Promise.all([loadSnapshot(), loadCycles()]); return rerender(); }
  if (view === 'modules') { await Promise.all([loadSnapshot(), loadModules()]); return rerender(); }
  if (view === 'coverage') { await Promise.all([loadSnapshot(), loadCoverage()]); return rerender(); }
  if (view === 'analytics') { await Promise.all([loadSnapshot(), loadAnalytics()]); return rerender(); }
  if (view === 'pages') {
    await loadPages();
    ensurePagesSelection();
    if (state.pagesSelected) await loadPage(state.pagesSelected, state.pagesRef);
    return rerender();
  }
  if (view === 'intake') {
    await Promise.all([loadSnapshot(), loadIntake(), loadTaskTemplates()]);
    return rerender();
  }
  if (view === 'assistant') {
    await loadSnapshot();
    await loadAssistantList();
    ensureAssistantActive();
    if (state.assistantActive) await loadAssistantConversation(state.assistantActive, true);
    return rerender();
  }
  if (view === 'automations') {
    await Promise.all([loadSnapshot(), loadAutomations()]);
    return rerender();
  }
  if (view === 'github') {
    await Promise.all([loadSnapshot(), loadGithub(false)]);
    return rerender();
  }

  if (!state.snapshot && !state.noBoard && !state.snapshotError) await loadSnapshot();
  if (!state.packageOptions && !state.noBoard) await loadPackageOptions();
  if (!state.filterFields) await loadFilterFields();
  if (!state.viewsLoaded) await loadViews();
  if ((view === 'board' || view === 'table') && feature('worklog') && !state.worklogLoaded) {
    await loadWorklog();
  }
  return rerender();
}

/* =========================================================================
   15. View dispatch
   ========================================================================= */

function renderView() {
  if (!dom.view) return;
  const focus = captureFocus();
  clear(dom.view);
  const view = state.route.view;
  const viewDef = VIEWS.find((entry) => entry.key === view);

  if (viewDef && viewDef.feature && !feature(viewDef.feature)) {
    state.route = { view: 'board', taskId: null };
    try { history.replaceState(null, '', '#/board'); } catch (err) { location.hash = '#/board'; }
    renderView();
    return;
  }
  if (view === 'settings') {
    renderSettings();
    restoreFocus(focus);
    return;
  }
  if (view === 'plan') {
    renderPlanView();
    restoreFocus(focus);
    return;
  }
  if (state.noBoard) {
    renderNoBoardNotice();
    restoreFocus(focus);
    return;
  }
  if (state.snapshotError) {
    dom.view.appendChild(h('div', { class: 'card-panel panel-pad' },
      h('div', { class: 'view-title', text: 'Cannot load the dashboard' }),
      h('div', { class: 'view-sub', text: 'The snapshot request failed.' }),
      h('div', { style: { marginTop: '12px' } }, errorCallout(state.snapshotError)),
      h('div', { style: { marginTop: '12px' } },
        h('button', {
          class: 'btn btn-primary', type: 'button', text: 'Retry',
          on: { click: async () => { await loadSnapshot(); renderHeader(); renderView(); } }
        }))));
    restoreFocus(focus);
    return;
  }
  if (!state.snapshot) {
    dom.view.appendChild(loadingRow('Loading the board…'));
    restoreFocus(focus);
    return;
  }

  switch (view) {
    case 'yourwork': renderYourWork(); break;
    case 'board': renderBoard(); break;
    case 'table': renderTable(); break;
    case 'timeline': renderTimeline(); break;
    case 'cycles': renderCycles(); break;
    case 'modules': renderModules(); break;
    case 'coverage': renderCoverage(); break;
    case 'graph': renderGraph(); break;
    case 'dispatch': renderDispatch(); break;
    case 'approvals': renderApprovals(); break;
    case 'activity': renderActivity(); break;
    case 'analytics': renderAnalytics(); break;
    case 'sessions': renderSessions(); break;
    case 'pages': renderPages(); break;
    case 'intake': renderIntake(); break;
    case 'assistant': renderAssistant(); break;
    case 'automations': renderAutomations(); break;
    case 'github': renderGithub(); break;
    default: renderBoard();
  }
  restoreFocus(focus);
}

function renderNoBoardNotice() {
  dom.view.appendChild(h('div', { class: 'wizard' },
    emptyState('No board.json yet',
      'Start the planning interview: answer a few questions, let a headless generator write the board, then approve the plan.',
      h('button', {
        class: 'btn btn-primary', type: 'button', text: 'Open the planner',
        on: { click: () => navigate('plan') }
      }))));
}

/* =========================================================================
   16. View helpers: filters and search
   ========================================================================= */

function syncSearchInput() {
  if (dom.search && dom.search.value !== state.filters.text) dom.search.value = state.filters.text;
}

function filterValues(key) {
  const tasks = (state.snapshot && state.snapshot.tasks) || [];
  const seen = new Map();
  for (const task of tasks) {
    if (key === 'stage') {
      const value = task.stage === null || task.stage === undefined ? '' : String(task.stage);
      if (!seen.has(value)) seen.set(value, task.stage_title || value || '—');
    } else if (key === 'package') {
      continue;
    } else if (key === 'owner') {
      const value = task.owner || '';
      if (!seen.has(value)) seen.set(value, value || 'Unassigned');
    }
  }
  if (key === 'package') {
    return (state.packageOptions || []).map((path) => [path, path]);
  }
  return Array.from(seen.entries()).sort((a, b) => String(a[1]).localeCompare(String(b[1])));
}

function applyFilters(tasks) {
  const filters = state.filters;
  const text = String(filters.text || '').trim().toLowerCase();
  return (tasks || []).filter((task) => {
    if (filters.stage && String(task.stage) !== filters.stage) return false;
    if (filters.package && !packageMatches(task, filters.package)) return false;
    if (filters.owner && (task.owner || '') !== filters.owner) return false;
    if (!text) return true;
    const haystack = [
      task.id, task.title, task.goal, task.why, task.owner, task.stage_title,
      task.stage, task.package, task.parallel_group, task.branch,
      (task.depends_on || []).join(' '), (task.gates || []).join(' '),
      (task.scope_write || []).join(' ')
    ].filter(Boolean).join(' ').toLowerCase();
    return haystack.indexOf(text) !== -1;
  });
}

function packageMatches(task, packagePath) {
  if (!packagePath) return true;
  if (task.package === packagePath) return true;
  const scope = [].concat(task.scope_write || [], task.scope_read || []);
  const base = String(packagePath).replace(/\/$/, '');
  return scope.some((entry) => {
    const value = String(entry).replace(/\/$/, '');
    return value === base || value.indexOf(base + '/') === 0 || base.indexOf(value + '/') === 0;
  });
}

function visibleTasks() {
  const tasks = (state.snapshot && state.snapshot.tasks) || [];
  const text = String(state.filters.text || '').trim().toLowerCase();
  let out = tasks;
  if (text) {
    out = out.filter((task) => {
      const haystack = [
        task.id, task.title, task.goal, task.why, task.owner, task.stage_title,
        task.stage, task.package, task.parallel_group, task.branch,
        (task.labels || []).join(' '), (task.depends_on || []).join(' '),
        (task.gates || []).join(' '), (task.scope_write || []).join(' ')
      ].filter(Boolean).join(' ').toLowerCase();
      return haystack.indexOf(text) !== -1;
    });
  }
  if (feature('views') && Array.isArray(state.structuredFilters) && state.structuredFilters.length) {
    out = out.filter((task) => matchAllConditions(task, state.structuredFilters));
  }
  return out;
}

/* =========================================================================
   2.1 — structured filter builder, views bar and saved views
   ========================================================================= */

function viewField(label, control) {
  return h('label', { class: 'view-field' }, h('span', { text: label }), control);
}

function capitalize(text) {
  const value = String(text || '');
  return value ? value.charAt(0).toUpperCase() + value.slice(1).replace(/_/g, ' ') : value;
}

function renderViewBar() {
  const bar = h('div', { class: 'view-bar' });
  const views = (state.views && state.views.all) || [];

  const select = h('select', {
    class: 'select', 'aria-label': 'Active view',
    on: { change: (event) => applyView(event.target.value) }
  });
  const custom = h('option', { value: '', text: 'Custom view' });
  select.appendChild(custom);
  if (views.length) {
    const builtinGroup = h('optgroup', { label: 'Built-in' });
    const savedGroup = h('optgroup', { label: 'Saved' });
    for (const view of views) {
      const option = h('option', { value: view.id, text: view.name || view.id });
      if (view.builtin) builtinGroup.appendChild(option);
      else savedGroup.appendChild(option);
    }
    if (builtinGroup.children.length) select.appendChild(builtinGroup);
    if (savedGroup.children.length) select.appendChild(savedGroup);
  }
  select.value = state.activeViewId || '';
  bar.appendChild(viewField('View', select));

  const active = currentView();
  bar.appendChild(h('button', {
    class: 'btn btn-sm', type: 'button', text: 'Save view',
    disabled: !canWrite(),
    title: canWrite() ? 'Save the current filters, grouping and sorting as a view' : 'The dashboard is read-only',
    on: { click: () => openSaveViewModal() }
  }));
  if (active && !active.builtin) {
    bar.appendChild(h('button', {
      class: 'btn btn-sm btn-danger', type: 'button', text: 'Delete', disabled: !canWrite(),
      title: canWrite() ? 'Delete this saved view' : 'The dashboard is read-only',
      on: { click: () => deleteCurrentView() }
    }));
  }

  const groupSelect = h('select', {
    class: 'select', 'aria-label': 'Group by',
    on: {
      change: (event) => {
        state.groupBy = event.target.value || 'status';
        markCustomView();
        rerenderWithFocus();
      }
    }
  });
  const groupOptions = ['status'].concat(filterGroupByOptions().filter((option) => option !== 'status'));
  for (const option of groupOptions) {
    const node = h('option', { value: option, text: option === 'status' ? 'Status' : capitalize(option) });
    if ((state.groupBy || 'status') === option) node.selected = true;
    groupSelect.appendChild(node);
  }
  groupSelect.value = state.groupBy || 'status';
  bar.appendChild(viewField('Group', groupSelect));

  const sortSelect = h('select', {
    class: 'select', 'aria-label': 'Sort by',
    on: {
      change: (event) => {
        state.sort = { field: event.target.value, dir: (state.sort && state.sort.dir) || 'asc' };
        markCustomView();
        rerenderWithFocus();
      }
    }
  });
  for (const field of filterSortableFields()) {
    const node = h('option', { value: field, text: FIELD_LABELS[field] || capitalize(field) });
    if ((state.sort && state.sort.field) === field) node.selected = true;
    sortSelect.appendChild(node);
  }
  sortSelect.value = (state.sort && state.sort.field) || 'id';
  bar.appendChild(viewField('Sort', sortSelect));

  const descending = state.sort && state.sort.dir === 'desc';
  bar.appendChild(h('button', {
    class: 'btn btn-sm btn-icon', type: 'button',
    text: descending ? '↓' : '↑',
    'aria-label': descending ? 'Sorted descending, switch to ascending' : 'Sorted ascending, switch to descending',
    title: descending ? 'Descending' : 'Ascending',
    on: {
      click: () => {
        state.sort = { field: (state.sort && state.sort.field) || 'id', dir: descending ? 'asc' : 'desc' };
        markCustomView();
        rerenderWithFocus();
      }
    }
  }));

  bar.appendChild(h('button', {
    class: 'btn btn-sm btn-ghost', type: 'button',
    text: state.density === 'compact' ? 'Compact' : 'Comfortable',
    title: 'Toggle display density',
    on: { click: () => toggleDensity() }
  }));

  const hint = h('span', { class: 'view-hint' });
  if (active) {
    append(hint, ['View ', h('strong', { text: active.name || active.id }), active.builtin ? ' · built-in' : ' · saved']);
  } else {
    hint.textContent = 'Custom filters · not saved';
  }
  bar.appendChild(hint);
  return bar;
}

function renderFilterBuilder() {
  const wrap = h('div', { class: 'filter-builder' });
  const chips = h('div', { class: 'filter-chips' });
  const conditions = state.structuredFilters || [];

  if (!conditions.length) {
    chips.appendChild(h('span', { class: 'hint', text: 'No filters — every task is shown.' }));
  }
  conditions.forEach((condition, index) => {
    chips.appendChild(h('span', { class: 'filter-chip' },
      h('span', { text: conditionText(condition) }),
      h('button', {
        class: 'filter-chip-x', type: 'button', 'aria-label': 'Remove filter', title: 'Remove filter', text: '×',
        on: {
          click: () => {
            state.structuredFilters.splice(index, 1);
            markCustomView();
            rerenderWithFocus();
          }
        }
      })));
  });
  if (conditions.length) {
    chips.appendChild(h('button', {
      class: 'btn btn-sm btn-ghost', type: 'button', text: 'Clear all',
      on: {
        click: () => {
          state.structuredFilters = [];
          markCustomView();
          rerenderWithFocus();
        }
      }
    }));
    if (conditions.length > 1) chips.appendChild(h('span', { class: 'hint', style: { fontSize: '10.5px' }, text: 'All conditions must match (AND)' }));
  }

  const total = (state.snapshot && state.snapshot.tasks ? state.snapshot.tasks.length : 0);
  const shown = visibleTasks().length;
  chips.appendChild(h('span', {
    class: 'filter-count',
    text: conditions.length ? shown + ' of ' + total + ' tasks' : total + ' ' + plural(total, 'task')
  }));
  wrap.appendChild(chips);

  if (state.filterEditorOpen) wrap.appendChild(renderFilterEditor());
  else {
    wrap.appendChild(h('button', {
      class: 'btn btn-sm', type: 'button', text: '+ Add filter',
      on: {
        click: () => {
          state.filterEditorOpen = true;
          state.filterDraft = defaultFilterDraft();
          state.filterError = null;
          renderView();
        }
      }
    }));
  }
  return wrap;
}

function filterFieldOptions() {
  const api = state.filterFields;
  if (api && api.fields) return Object.keys(api.fields);
  return Object.keys(FIELD_LABELS);
}

function filterTextSuggestions(field) {
  const tasks = (state.snapshot && state.snapshot.tasks) || [];
  const values = [];
  for (const task of tasks) {
    const value = field === 'stage' ? (task.stage_title || task.stage) : task[field];
    if (value !== null && value !== undefined && value !== '' && values.indexOf(String(value)) === -1) {
      values.push(String(value));
    }
  }
  return values.slice(0, 40);
}

function renderFilterValueControl(draft) {
  const kind = filterKind(draft.field);
  const op = draft.op;
  const control = h('div', { class: 'filter-values' });

  if (NO_VALUE_OPERATORS.indexOf(op) !== -1) {
    control.appendChild(h('span', { class: 'hint', text: 'This operator takes no value.' }));
    return control;
  }

  if (kind === 'status') {
    const statuses = statusOrder();
    if (op === 'any_of' || op === 'none_of') {
      const selected = Array.isArray(draft.value) ? draft.value : [];
      for (const status of statuses) {
        const meta = stMeta(status);
        const box = h('label', { class: 'filter-value-option' },
          h('input', {
            type: 'checkbox', value: status, checked: selected.indexOf(status) !== -1,
            on: {
              change: (event) => {
                const list = Array.isArray(state.filterDraft.value) ? state.filterDraft.value.slice() : [];
                const index = list.indexOf(status);
                if (event.target.checked && index === -1) list.push(status);
                if (!event.target.checked && index !== -1) list.splice(index, 1);
                state.filterDraft.value = list;
              }
            }
          }),
          h('span', { class: 'dot st-' + meta.color }), meta.label);
        control.appendChild(box);
      }
    } else {
      const select = h('select', { class: 'select', 'aria-label': 'Status value', on: { change: (event) => { state.filterDraft.value = event.target.value; } } });
      for (const status of statuses) {
        const option = h('option', { value: status, text: stMeta(status).label });
        if (draft.value === status) option.selected = true;
        select.appendChild(option);
      }
      select.value = draft.value || 'pending';
      control.appendChild(select);
    }
    return control;
  }

  if (kind === 'label') {
    const selected = Array.isArray(draft.value) ? draft.value : [];
    const groups = settingsGroups();
    const labels = settingsLabels();
    const byGroup = new Map();
    for (const label of labels) {
      const group = groups.indexOf(label.group) !== -1 ? label.group : 'custom';
      if (!byGroup.has(group)) byGroup.set(group, []);
      byGroup.get(group).push(label);
    }
    for (const group of groups) {
      if (!byGroup.has(group)) continue;
      control.appendChild(h('span', { class: 'props-label-group', text: group }));
      for (const label of byGroup.get(group)) {
        control.appendChild(h('label', { class: 'filter-value-option' },
          h('input', {
            type: 'checkbox', value: label.id, checked: selected.indexOf(label.id) !== -1,
            on: {
              change: (event) => {
                const list = Array.isArray(state.filterDraft.value) ? state.filterDraft.value.slice() : [];
                const index = list.indexOf(label.id);
                if (event.target.checked && index === -1) list.push(label.id);
                if (!event.target.checked && index !== -1) list.splice(index, 1);
                state.filterDraft.value = list;
              }
            }
          }),
          labelChip(label)));
      }
    }
    return control;
  }

  if (kind === 'bool') {
    const select = h('select', { class: 'select', 'aria-label': 'Boolean value', on: { change: (event) => { state.filterDraft.value = event.target.value === 'true'; } } });
    for (const [value, label] of [['true', 'true'], ['false', 'false']]) {
      const option = h('option', { value: value, text: label });
      if (Boolean(draft.value) === (value === 'true')) option.selected = true;
      select.appendChild(option);
    }
    select.value = draft.value ? 'true' : 'false';
    control.appendChild(select);
    return control;
  }

  if (kind === 'budget') {
    const select = h('select', { class: 'select', 'aria-label': 'Budget state', on: { change: (event) => { state.filterDraft.value = event.target.value; } } });
    for (const value of ['over', 'warn', 'ok']) {
      const option = h('option', { value: value, text: value });
      if (draft.value === value) option.selected = true;
      select.appendChild(option);
    }
    select.value = draft.value || 'over';
    control.appendChild(select);
    return control;
  }

  if (kind === 'number') {
    const input = h('input', {
      class: 'input', type: 'number', value: draft.value === undefined || draft.value === null ? '' : String(draft.value),
      'aria-label': 'Filter value', step: 'any', style: { width: '110px' },
      on: { input: (event) => { state.filterDraft.value = event.target.value; } }
    });
    control.appendChild(input);
    return control;
  }

  const listId = 'filter-suggestions-' + (state.filterDraft.field || 'text');
  const input = h('input', {
    class: 'input', type: 'text', value: draft.value === undefined || draft.value === null ? '' : String(draft.value),
    placeholder: 'value', 'aria-label': 'Filter value', list: listId,
    on: { input: (event) => { state.filterDraft.value = event.target.value; } }
  });
  control.appendChild(input);
  const suggestions = filterTextSuggestions(draft.field);
  if (suggestions.length) {
    const datalist = h('datalist', { id: listId });
    for (const suggestion of suggestions) datalist.appendChild(h('option', { value: suggestion }));
    control.appendChild(datalist);
  }
  return control;
}

function renderFilterEditor() {
  const draft = state.filterDraft || defaultFilterDraft();
  const editor = h('div', { class: 'filter-editor' });

  const fieldSelect = h('select', {
    class: 'select', 'aria-label': 'Filter field',
    on: {
      change: (event) => {
        const field = event.target.value;
        const operators = filterOperators(field);
        state.filterDraft = { field: field, op: operators[0], value: defaultFilterValue(field, operators[0]) };
        state.filterError = null;
        renderView();
      }
    }
  });
  for (const field of filterFieldOptions()) {
    const option = h('option', { value: field, text: FIELD_LABELS[field] || field });
    if (draft.field === field) option.selected = true;
    fieldSelect.appendChild(option);
  }
  fieldSelect.value = draft.field;
  editor.appendChild(viewField('Field', fieldSelect));

  const operators = filterOperators(draft.field);
  const opSelect = h('select', {
    class: 'select', 'aria-label': 'Filter operator',
    on: {
      change: (event) => {
        const op = event.target.value;
        state.filterDraft = {
          field: draft.field,
          op: op,
          value: NO_VALUE_OPERATORS.indexOf(op) !== -1 ? undefined : (
            op === 'any_of' || op === 'none_of'
              ? (Array.isArray(draft.value) ? draft.value.slice() : [])
              : defaultFilterValue(draft.field, op)
          )
        };
        state.filterError = null;
        renderView();
      }
    }
  });
  for (const op of operators) {
    const option = h('option', { value: op, text: OPERATOR_LABELS[op] || op });
    if (draft.op === op) option.selected = true;
    opSelect.appendChild(option);
  }
  opSelect.value = draft.op;
  editor.appendChild(viewField('Operator', opSelect));

  editor.appendChild(viewField(filterValueLabel(draft.field), renderFilterValueControl(draft)));

  editor.appendChild(h('div', { class: 'row', style: { gap: '6px' } },
    h('button', {
      class: 'btn btn-primary btn-sm', type: 'button', text: 'Add',
      on: { click: () => addFilterFromEditor() }
    }),
    h('button', {
      class: 'btn btn-ghost btn-sm', type: 'button', text: 'Cancel',
      on: {
        click: () => {
          state.filterEditorOpen = false;
          state.filterError = null;
          renderView();
        }
      }
    })));
  if (state.filterError) editor.appendChild(h('div', { class: 'filter-error', text: state.filterError }));
  return editor;
}

function addFilterFromEditor() {
  const draft = state.filterDraft;
  if (!draft || !draft.field) {
    state.filterError = 'Choose a field first.';
    renderView();
    return;
  }
  const kind = filterKind(draft.field);
  let value = draft.value;
  if (NO_VALUE_OPERATORS.indexOf(draft.op) === -1) {
    if (kind === 'number') {
      const number = Number(value);
      if (value === '' || value === null || value === undefined || !isFinite(number)) {
        state.filterError = 'Enter a number for this filter.';
        renderView();
        return;
      }
      value = number;
    } else if (kind === 'status' || kind === 'label') {
      if ((draft.op === 'any_of' || draft.op === 'none_of')) {
        if (!Array.isArray(value) || !value.length) {
          state.filterError = 'Select at least one ' + (kind === 'status' ? 'status' : 'label') + '.';
          renderView();
          return;
        }
        value = value.slice();
      }
    } else if (kind === 'bool') {
      value = Boolean(value);
    } else if (kind === 'budget') {
      if (['over', 'warn', 'ok'].indexOf(value) === -1) value = 'over';
    } else if (String(value === null || value === undefined ? '' : value).trim() === '') {
      state.filterError = 'Enter a value, or use an empty/not-empty operator.';
      renderView();
      return;
    } else {
      value = String(value).trim();
    }
  } else {
    value = undefined;
  }
  const condition = { field: draft.field, op: draft.op };
  if (value !== undefined) condition.value = value;
  state.structuredFilters = (state.structuredFilters || []).concat([condition]);
  state.filterEditorOpen = false;
  state.filterError = null;
  markCustomView();
  renderView();
}

function openSaveViewModal() {
  const active = currentView();
  const nameInput = h('input', {
    class: 'input', type: 'text', placeholder: 'Review queue',
    value: active && !active.builtin ? (active.name || '') : ''
  });
  const idInput = h('input', {
    class: 'input', type: 'text', placeholder: 'review-queue',
    value: active && !active.builtin ? (active.id || '') : ''
  });
  let idTouched = Boolean(active && !active.builtin);
  nameInput.addEventListener('input', () => {
    if (!idTouched) idInput.value = slugify(nameInput.value);
  });
  idInput.addEventListener('input', () => { idTouched = true; });

  const kindSelect = h('select', { class: 'select', 'aria-label': 'View kind' },
    h('option', { value: 'board', text: 'Board' }),
    h('option', { value: 'table', text: 'Table' }));
  kindSelect.value = state.route.view === 'table' ? 'table' : 'board';

  const errorBox = h('div');
  const body = h('div', { class: 'plan-editor' },
    errorBox,
    h('div', { class: 'form-grid' },
      h('label', { class: 'field' }, h('span', { class: 'field-label', text: 'Name' }), nameInput),
      h('label', { class: 'field' },
        h('span', { class: 'field-label', text: 'View id' }), idInput,
        h('span', { class: 'field-help', text: 'Lowercase letters, digits and dashes (a-z, 0-9, -).' })),
      h('label', { class: 'field' },
        h('span', { class: 'field-label', text: 'Default kind' }), kindSelect)),
    h('p', { class: 'hint', text: 'Saves the current filters, grouping and sorting into views/<id>.json.' }));

  openModal({
    title: 'Save view',
    body: body,
    footer: [
      h('button', { class: 'btn', type: 'button', text: 'Cancel', on: { click: () => closeModal() } }),
      h('button', {
        class: 'btn btn-primary', type: 'button', text: 'Save view',
        on: {
          click: () => saveViewFromModal({
            nameInput, idInput, kindSelect, errorBox,
            saveButton: null
          })
        }
      })
    ]
  });
  focusSoon(nameInput);
}

async function saveViewFromModal(context) {
  const name = context.nameInput.value.trim();
  const id = context.idInput.value.trim();
  const errorBox = context.errorBox;
  if (!name) {
    errorBox.replaceChildren(errorCallout(new ApiError('A view name is required.', 400, null)));
    return;
  }
  if (!/^[a-z][a-z0-9-]{0,40}$/.test(id)) {
    errorBox.replaceChildren(errorCallout(new ApiError('View id must start with a lowercase letter and use only a-z, 0-9 and dashes.', 400, null)));
    return;
  }
  const active = currentView();
  const payload = {
    name: name,
    kind: context.kindSelect.value === 'table' ? 'table' : 'board',
    filters: JSON.parse(JSON.stringify(state.structuredFilters || [])),
    group_by: state.groupBy || 'status',
    sort: { field: (state.sort && state.sort.field) || 'id', dir: (state.sort && state.sort.dir) || 'asc' }
  };
  if (active && Array.isArray(active.columns) && active.columns.length) payload.columns = active.columns.slice();
  try {
    const saved = await api('/api/views/' + encodeURIComponent(id), { method: 'PUT', body: payload });
    closeModal();
    await loadViews();
    if (!(state.views.all || []).some((view) => view.id === id)) {
      const local = Object.assign({ version: 1, id: id, builtin: false }, payload, saved && saved.id ? saved : {});
      state.views.saved = (state.views.saved || []).concat([local]);
      state.views.all = (state.views.all || []).concat([local]);
    }
    state.activeViewId = id;
    prefSet(PREF_VIEW, id);
    toast('View saved', 'ok');
    applyView(id);
  } catch (err) {
    errorBox.replaceChildren(errorCallout(err));
  }
}

async function deleteCurrentView() {
  const view = currentView();
  if (!view || view.builtin) return;
  const confirmed = await confirmDialog({
    title: 'Delete view "' + (view.name || view.id) + '"?',
    message: 'The saved view file is removed from views/. Tasks and board data are untouched.',
    confirmLabel: 'Delete view'
  });
  if (!confirmed) return;
  try {
    await api('/api/views/' + encodeURIComponent(view.id), { method: 'DELETE' });
    await loadViews();
    state.activeViewId = '';
    prefSet(PREF_VIEW, '');
    toast('View deleted', 'ok');
    renderView();
  } catch (err) {
    toast('Delete failed: ' + describeError(err), 'error');
  }
}

function renderGraphFilterNote() {
  if (!feature('views')) return null;
  const conditions = state.structuredFilters || [];
  if (!conditions.length) return null;
  const row = h('div', { class: 'row-wrap', style: { marginBottom: '10px' } },
    h('span', { class: 'hint', text: 'Board/Table filters apply here:' }));
  for (const condition of conditions) row.appendChild(h('span', { class: 'filter-chip', text: conditionText(condition) }));
  row.appendChild(h('button', {
    class: 'btn btn-sm btn-ghost', type: 'button', text: 'Clear',
    on: {
      click: () => {
        state.structuredFilters = [];
        markCustomView();
        renderView();
      }
    }
  }));
  return row;
}

function renderFilters(options) {
  const opts = options || {};
  const wrap = h('div', { class: 'filters-block' });
  if (!feature('views')) {
    const total = (state.snapshot && state.snapshot.tasks ? state.snapshot.tasks.length : 0);
    wrap.appendChild(h('div', { class: 'row-wrap' },
      h('span', { class: 'hint', text: 'Filtering is disabled (feature "views" is off) — search in the header still works.' }),
      h('span', { class: 'filter-count', text: total + ' ' + plural(total, 'task') })));
    return wrap;
  }
  wrap.appendChild(renderViewBar());
  wrap.appendChild(renderFilterBuilder());
  if (opts.note) wrap.appendChild(h('p', { class: 'hint', text: opts.note }));
  return wrap;
}

function filterSelect(key, allLabel, entries, onChange) {
  if (!entries.length) return null;
  const select = h('select', {
    class: 'select', 'aria-label': 'Filter by ' + key,
    on: { change: (event) => onChange(event.target.value) }
  }, h('option', { value: '', text: allLabel }));
  for (const entry of entries) {
    const option = h('option', { value: entry[0], text: entry[1] });
    if (state.filters[key] === entry[0]) option.selected = true;
    select.appendChild(option);
  }
  select.value = state.filters[key] || '';
  return select;
}

function rerenderWithFocus() {
  renderView();
}

function scheduleFilterRender() {
  if (searchTimer) window.clearTimeout(searchTimer);
  searchTimer = window.setTimeout(() => {
    searchTimer = null;
    rerenderWithFocus();
  }, 120);
}

/* =========================================================================
   17. Modal system
   ========================================================================= */

let modalCleanup = null;

function openModal(options) {
  const opts = options || {};
  if (!dom.modalBackdrop.hidden) closeModal();
  state.modal = opts;
  clear(dom.modal);
  const title = opts.title || 'Dialog';
  dom.modal.setAttribute('aria-labelledby', 'modal-title');
  dom.modal.appendChild(h('div', { class: 'modal-head' },
    h('h2', { class: 'modal-title', id: 'modal-title', text: title }),
    h('button', {
      class: 'modal-close', type: 'button', 'aria-label': 'Close dialog', text: '×',
      on: { click: () => closeModal() }
    })));
  const body = h('div', { class: 'modal-body' });
  if (opts.body) append(body, [opts.body]);
  dom.modal.appendChild(body);
  if (opts.footer) dom.modal.appendChild(h('div', { class: 'modal-foot' }, opts.footer));
  dom.modalBackdrop.hidden = false;
  modalCleanup = typeof opts.onClose === 'function' ? opts.onClose : null;
  const focusTarget = dom.modal.querySelector('[data-autofocus]') || dom.modal.querySelector('input, textarea, select, button');
  focusSoon(focusTarget);
}

function closeModal() {
  if (modalCleanup) {
    try { modalCleanup(); } catch (err) { /* ignore */ }
    modalCleanup = null;
  }
  dom.modalBackdrop.hidden = true;
  clear(dom.modal);
  state.modal = null;
}

function closeAllModals() {
  if (!dom.modalBackdrop.hidden) closeModal();
}

function confirmDialog(options) {
  const opts = options || {};
  return new Promise((resolve) => {
    let settled = false;
    const finish = (value) => {
      if (settled) return;
      settled = true;
      closeModal();
      resolve(value);
    };
    openModal({
      title: opts.title || 'Are you sure?',
      body: h('p', { class: 'hint', text: opts.message || '' }),
      footer: [
        h('button', { class: 'btn', type: 'button', text: 'Cancel', on: { click: () => finish(false) } }),
        h('button', {
          class: opts.danger === false ? 'btn btn-primary' : 'btn btn-primary',
          type: 'button', text: opts.confirmLabel || 'Confirm',
          on: { click: () => finish(true) }
        })
      ],
      onClose: () => finish(false)
    });
  });
}

/* =========================================================================
   18. Jobs tray
   ========================================================================= */

function jobStatusMeta(status) {
  switch (status) {
    case 'running': return { label: 'Running', color: 'blue' };
    case 'pass': return { label: 'Passed', color: 'green' };
    case 'fail': return { label: 'Failed', color: 'red' };
    case 'error': return { label: 'Error', color: 'red' };
    default: return { label: status || 'Unknown', color: 'neutral' };
  }
}

function syncJobsPolling() {
  const active = state.jobsOpen || state.jobs.some((job) => job.status === 'running');
  if (active && !jobsPollTimer) {
    jobsPollTimer = window.setInterval(() => loadJobs(), 2600);
  } else if (!active && jobsPollTimer) {
    window.clearInterval(jobsPollTimer);
    jobsPollTimer = null;
  }
}

function paintJobsButtonState() {
  const running = state.jobs.filter((job) => job.status === 'running').length;
  dom.jobsDot.className = 'jobs-dot' + (running ? ' is-running' : '');
  if (running) {
    dom.jobsSummary.textContent = running + ' ' + plural(running, 'job') + ' running';
    return;
  }
  const latest = state.jobs[0];
  if (!latest) {
    dom.jobsSummary.textContent = 'no jobs yet';
    dom.jobsDot.className = 'jobs-dot';
    return;
  }
  dom.jobsSummary.textContent = latest.label + ' · ' + (latest.status || 'unknown');
  dom.jobsDot.className = 'jobs-dot' + (latest.status === 'pass' ? ' is-pass' : (latest.status === 'fail' || latest.status === 'error' ? ' is-fail' : ''));
}

function jobDuration(job) {
  const start = parseDate(job.started || job.created);
  if (!start) return '—';
  const end = parseDate(job.ended);
  const seconds = ((end || new Date()).getTime() - start.getTime()) / 1000;
  return fmtDuration(seconds);
}

function renderJobsTray() {
  paintJobsButtonState();
  const open = state.jobsOpen;
  dom.jobs.dataset.open = open ? 'true' : 'false';
  dom.jobsToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
  dom.jobsBody.hidden = !open;
  if (!open) return;

  clear(dom.jobsBody);
  if (!state.jobs.length) {
    dom.jobsBody.appendChild(h('div', { class: 'jobs-empty', text: 'No jobs yet. Run the board check or a gate from a task drawer.' }));
    return;
  }
  for (const job of state.jobs.slice(0, 30)) {
    const meta = jobStatusMeta(job.status);
    const row = h('div', { class: 'job-row' },
      h('span', { class: 'badge bg-' + meta.color + ' st-' + meta.color },
        h('span', { class: 'dot' }), meta.label),
      h('span', { class: 'job-label', text: job.label || job.kind || 'job' }),
      h('span', { class: 'job-cmd', title: job.command || '', text: job.command || '' }),
      h('span', { class: 'job-meta', text: jobStatusDetail(job) }),
      h('div', { class: 'job-actions' },
        h('button', {
          class: 'btn btn-sm', type: 'button', text: 'Log',
          on: { click: () => openJobLog(job.id) }
        }),
        job.status === 'running' ? h('button', {
          class: 'btn btn-sm btn-danger', type: 'button', text: 'Stop',
          on: { click: () => stopJob(job.id) }
        }) : null));
    dom.jobsBody.appendChild(row);
    if (job.status === 'running' && Array.isArray(job.tail) && job.tail.length) {
      dom.jobsBody.appendChild(h('pre', {
        class: 'job-tail',
        'aria-label': 'Live log tail',
        text: job.tail.slice(-5).join('\n')
      }));
    }
  }
}

function jobStatusDetail(job) {
  const parts = [];
  if (job.status === 'running') parts.push('running');
  else if (job.exit_code !== null && job.exit_code !== undefined) parts.push('exit ' + job.exit_code);
  parts.push(jobDuration(job));
  if (job.ended) parts.push(relTime(job.ended));
  return parts.join(' · ');
}

function toggleJobs(open) {
  state.jobsOpen = typeof open === 'boolean' ? open : !state.jobsOpen;
  renderJobsTray();
  syncJobsPolling();
  if (state.jobsOpen) loadJobs();
}

async function startJob(kind) {
  const path = kind === 'audit' ? '/api/jobs/audit' : '/api/jobs/check';
  const label = kind === 'audit' ? 'Audit' : 'Board check';
  try {
    await api(path, { method: 'POST', body: {} });
    toast(label + ' started', 'ok', 2500);
    state.jobsOpen = true;
    renderJobsTray();
    await loadJobs();
  } catch (err) {
    toast(label + ': ' + describeError(err), 'error');
  }
}

async function stopJob(jobId) {
  try {
    await api('/api/jobs/' + encodeURIComponent(jobId) + '/stop', { method: 'POST', body: {} });
    toast('Stop requested', 'ok', 2200);
    await loadJobs();
  } catch (err) {
    toast('Stop failed: ' + describeError(err), 'error');
  }
}

function openJobLog(jobId) {
  const job = state.jobs.find((item) => item.id === jobId) || null;
  const logNode = h('pre', { class: 'log-pre', 'aria-live': 'polite', text: '' });
  const statusLine = h('div', { class: 'row text-sm muted' });
  let offset = 0;
  let timer = null;
  let stopped = false;

  const paintStatus = (current) => {
    clear(statusLine);
    const meta = jobStatusMeta(current ? current.status : (job && job.status));
    append(statusLine, [
      h('span', { class: 'badge bg-' + meta.color + ' st-' + meta.color }, h('span', { class: 'dot' }), meta.label),
      h('span', { class: 'mono', text: current && current.command ? current.command : (job && job.command) || '' })
    ]);
  };

  const tick = async () => {
    if (stopped) return;
    try {
      const chunk = await api('/api/jobs/' + encodeURIComponent(jobId) + '/log?offset=' + offset);
      if (chunk && typeof chunk.text === 'string' && chunk.text) {
        logNode.textContent += chunk.text;
        logNode.scrollTop = logNode.scrollHeight;
      }
      if (chunk && typeof chunk.next === 'number') offset = chunk.next;
      const jobs = await api('/api/jobs');
      const current = jobs.find((item) => item.id === jobId);
      paintStatus(current);
      if (!current || current.status !== 'running') {
        stopped = true;
        if (timer) window.clearInterval(timer);
        timer = null;
      }
    } catch (err) {
      stopped = true;
      if (timer) window.clearInterval(timer);
      timer = null;
      logNode.textContent += '\n[dashboard] ' + describeError(err) + '\n';
    }
  };

  paintStatus(job);
  openModal({
    title: 'Job log · ' + (job ? (job.label || job.kind) : jobId),
    body: [statusLine, logNode],
    footer: [
      h('button', {
        class: 'btn', type: 'button', text: 'Copy log',
        on: { click: () => copyText(logNode.textContent) }
      }),
      h('button', { class: 'btn btn-primary', type: 'button', text: 'Close', on: { click: () => closeModal() } })
    ],
    onClose: () => {
      stopped = true;
      if (timer) window.clearInterval(timer);
      timer = null;
    }
  });
  tick();
  timer = window.setInterval(tick, 900);
}

/* =========================================================================
   19. Static bindings and keyboard
   ========================================================================= */

function bindStatic() {
  dom.themeButton.addEventListener('click', toggleTheme);
  if (dom.inboxButton) {
    dom.inboxButton.addEventListener('click', () => {
      if (feature('inbox')) navigate('yourwork');
      else toast('The inbox feature is disabled in Settings', 'warn');
    });
  }
  dom.checkButton.addEventListener('click', () => startJob('check'));
  dom.auditButton.addEventListener('click', () => startJob('audit'));
  dom.jobsToggle.addEventListener('click', () => toggleJobs());
  dom.search.addEventListener('input', (event) => {
    const value = event.target.value;
    state.filters.text = value;
    const view = state.route.view;
    if (view !== 'board' && view !== 'table' && view !== 'graph') {
      if (searchFocusTimer) window.clearTimeout(searchFocusTimer);
      searchFocusTimer = window.setTimeout(() => {
        searchFocusTimer = null;
        navigate('board');
        const input = dom.search;
        if (input) { input.focus(); try { input.setSelectionRange(input.value.length, input.value.length); } catch (err) { /* ignore */ } }
      }, 60);
      return;
    }
    scheduleFilterRender();
  });
  dom.search.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      if (state.route.view !== 'board') navigate('board');
      renderView();
    }
  });

  dom.drawerBackdrop.addEventListener('click', () => closeDrawer(true));
  dom.modalBackdrop.addEventListener('mousedown', (event) => {
    if (event.target === dom.modalBackdrop) closeModal();
  });

  window.addEventListener('hashchange', applyRoute);

  document.addEventListener('keydown', (event) => {
    if (event.defaultPrevented) return;
    const target = event.target;
    const tag = target && target.tagName ? target.tagName : '';
    const typing = tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || (target && target.isContentEditable);

    if (event.key === 'Escape') {
      if (!dom.modalBackdrop.hidden) { closeModal(); event.preventDefault(); return; }
      if (state.drawer.id) { closeDrawer(true); event.preventDefault(); return; }
      if (typing && target === dom.search) {
        dom.search.value = '';
        state.filters.text = '';
        rerenderWithFocus();
      }
      return;
    }
    if (!dom.modalBackdrop.hidden) return;
    if (typing || event.metaKey || event.ctrlKey || event.altKey) return;
    if (event.key === '/') {
      event.preventDefault();
      dom.search.focus();
      try { dom.search.select(); } catch (err) { /* ignore */ }
      return;
    }
    if (event.key === 'g' || event.key === 'G') {
      event.preventDefault();
      navigate('graph');
      return;
    }
    if (event.key === '?') {
      event.preventDefault();
      openModal({
        title: 'Keyboard shortcuts',
        body: h('div', { class: 'col' },
          shortcutRow('/', 'Focus the search field'),
          shortcutRow('g', 'Open the dependency graph'),
          shortcutRow('Esc', 'Close the drawer or a dialog')),
        footer: [h('button', { class: 'btn btn-primary', type: 'button', text: 'Close', on: { click: () => closeModal() } })]
      });
    }
  });

  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
    if (!document.documentElement.dataset.theme) paintThemeGlyph();
  });
}

function shortcutRow(key, label) {
  return h('div', { class: 'between', style: { padding: '4px 0' } },
    h('span', { text: label }), h('kbd', { class: 'kbd', text: key }));
}

/* =========================================================================
   20. Boot
   ========================================================================= */

async function boot() {
  initTheme();
  restorePreferences();
  bindStatic();
  bindPaletteShortcut();
  renderTabs();
  renderHeader();

  await loadConfig();
  await loadSnapshot();
  await loadSettings();
  await loadFilterFields();
  await loadViews();
  await loadInboxCounts();
  await loadHealth();

  if (!state.noBoard) {
    await loadPackageOptions();
    applySavedViewPreferences();
  }

  const known = location.hash && location.hash.startsWith('#/');
  if (!known) {
    const active = currentView();
    let startView = 'board';
    if (!state.config || state.config.board_present === false || state.noBoard) startView = 'plan';
    else if (active && active.kind === 'table') startView = 'table';
    try { history.replaceState(null, '', '#/' + startView); } catch (err) { location.hash = '#/' + startView; }
  }
  await loadJobs();
  applyRoute();
  connectEvents();
}

/* =========================================================================
   21. Board view
   ========================================================================= */

function renderBoard() {
  const snapshot = state.snapshot;
  const tasks = snapshot.tasks || [];
  const stages = snapshot.stages || [];
  const project = snapshot.project || {};
  const view = h('div', { class: 'board-view' + (state.density === 'compact' ? ' density-compact' : '') });
  dom.view.appendChild(view);

  view.appendChild(h('div', { class: 'view-head' },
    h('div', {},
      h('h1', { class: 'view-title', text: 'Board' }),
      h('p', {
        class: 'view-sub',
        text: [
          tasks.length + ' ' + plural(tasks.length, 'task'),
          stages.length + ' ' + plural(stages.length, 'stage'),
          project.profile ? 'profile ' + project.profile : '',
          project.base_branch ? 'base ' + project.base_branch : ''
        ].filter(Boolean).join(' · ')
      })),
    h('div', { class: 'view-actions' },
      h('button', {
        class: 'btn btn-sm', type: 'button', title: 'Refetch the snapshot',
        on: { click: () => refreshSnapshotButton() }
      }, 'Refresh'),
      h('button', {
        class: 'btn btn-sm', type: 'button', text: 'Plan',
        on: { click: () => navigate('plan') }
      }))));

  view.appendChild(renderFilters());
  if (canWrite()) view.appendChild(renderBulkBar());

  if (!tasks.length) {
    view.appendChild(emptyState('No tasks on the board',
      'The board exists but has no tasks yet. Add tasks in the Plan view.',
      h('button', { class: 'btn btn-primary', type: 'button', text: 'Open plan', on: { click: () => navigate('plan') } })));
    return;
  }

  const filtered = visibleTasks();
  if (!filtered.length) {
    view.appendChild(emptyState('No matching tasks', 'Adjust the filters or clear them to see the whole board.',
      h('button', {
        class: 'btn', type: 'button', text: 'Clear filters',
        on: {
          click: () => {
            state.structuredFilters = [];
            state.filters = { text: '', stage: '', package: '', owner: '' };
            markCustomView();
            syncSearchInput();
            renderView();
          }
        }
      })));
    return;
  }

  const sortableFilters = feature('views');
  const sorted = sortableFilters
    ? sortTaskList(filtered, (state.sort && state.sort.field) || 'id', (state.sort && state.sort.dir) || 'asc')
    : filtered;
  const groupBy = sortableFilters ? (state.groupBy || 'status') : 'status';

  const wrap = h('div', { class: 'board-wrap' });
  const board = h('div', { class: 'board' });
  if (groupBy === 'status') {
    for (const column of COLUMNS) board.appendChild(renderColumn(column, sorted));
  } else {
    for (const group of groupTaskList(sorted, groupBy)) board.appendChild(renderGroupColumn(group));
  }
  wrap.appendChild(board);
  wrap.appendChild(renderStagePanel());
  view.appendChild(wrap);
}

async function refreshSnapshotButton() {
  await loadSnapshot({ fresh: true });
  if (feature('worklog')) await loadWorklog();
  renderHeader();
  renderView();
}

function renderColumn(column, tasks) {
  const members = tasks.filter((task) => column.statuses.indexOf(task.status) !== -1);
  const collapsed = column.key === 'done' ? !state.boardDoneOpen : false;
  const node = h('section', {
    class: 'column',
    dataset: { collapsed: collapsed ? 'true' : 'false', column: column.key },
    'aria-label': column.label + ' column'
  });

  node.appendChild(h('header', { class: 'column-head' },
    statusDot(column.statuses[0]),
    h('span', { class: 'column-name', text: column.label }),
    h('span', { class: 'column-count', text: String(members.length) })));

  if (collapsed) {
    node.style.cursor = 'pointer';
    node.appendChild(h('button', {
      class: 'btn btn-ghost btn-sm column-expand', type: 'button',
      title: 'Expand the done column', text: '»',
      'aria-label': 'Expand the done column',
      on: { click: () => { state.boardDoneOpen = true; renderView(); } }
    }));
    node.addEventListener('click', () => { state.boardDoneOpen = true; renderView(); });
    return node;
  }

  const list = h('div', { class: 'column-list' });
  if (!members.length) list.appendChild(h('div', { class: 'column-empty', text: '—' }));
  else for (const task of members) list.appendChild(renderTaskCard(task));
  node.appendChild(list);
  if (column.key === 'done') {
    node.appendChild(h('button', {
      class: 'btn btn-ghost btn-sm column-expand', type: 'button',
      title: 'Collapse the done column', text: '« Collapse',
      on: { click: () => { state.boardDoneOpen = false; renderView(); } }
    }));
  }
  return node;
}

function renderGroupColumn(group) {
  const node = h('section', {
    class: 'column', dataset: { group: group.key },
    'aria-label': group.label + ' group'
  });
  node.appendChild(h('header', { class: 'column-head' },
    h('span', { class: 'column-dot st-neutral' }),
    h('span', { class: 'column-name', text: group.label }),
    h('span', { class: 'column-count', text: String(group.tasks.length) })));
  const list = h('div', { class: 'column-list' });
  if (!group.tasks.length) list.appendChild(h('div', { class: 'column-empty', text: '—' }));
  else for (const task of group.tasks) list.appendChild(renderTaskCard(task));
  node.appendChild(list);
  return node;
}

function renderTaskCard(task) {
  const meta = stMeta(task.status);
  const gates = task.gates || [];
  const passed = (task.gates_passed || []).length;
  const claim = task.claim;
  const ownerText = task.owner || 'unassigned';
  const labels = taskLabelIds(task);

  const card = h('article', {
    class: 'task-card status-' + meta.color,
    role: 'button',
    tabindex: '0',
    dataset: { taskId: task.id, status: task.status },
    title: (task.title || '(untitled)') + ' · ' + task.id + ' · ' + meta.label,
    on: {
      click: () => openTask(task.id),
      keydown: (event) => {
        if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); openTask(task.id); }
      }
    }
  });

  const topRow = h('div', { class: 'task-card-top' },
    h('span', { class: 'task-card-id', text: task.id }),
    h('span', { class: 'badge bg-' + meta.color + ' st-' + meta.color }, h('span', { class: 'dot' }), meta.label),
    claim ? h('span', {
      class: 'claim-badge',
      title: 'Claimed by ' + (claim.harness || 'session') + (claim.session ? ' · ' + claim.session : '')
    }, h('span', { class: 'dot' }), 'claimed') : null);
  const selector = bulkCheckbox(task);
  if (selector) topRow.appendChild(selector);
  card.appendChild(topRow);

  card.appendChild(h('div', { class: 'task-card-title', text: task.title || '(untitled)' }));
  if (labels.length) card.appendChild(labelChips(labels, 3));

  card.appendChild(h('div', { class: 'task-card-meta' },
    h('span', { text: task.stage_title || String(task.stage || '—') }),
    h('span', { class: 'sep', text: '·' }),
    h('span', { text: ownerText }),
    task.wave !== null && task.wave !== undefined ? h('span', { class: 'sep', text: '·' }) : null,
    task.wave !== null && task.wave !== undefined ? h('span', { text: 'wave ' + (task.wave + 1) }) : null));

  const effort = effortText(task);
  if (effort) {
    card.appendChild(h('div', { class: 'effort-line' },
      h('span', { text: effort }),
      estimateOf(task) !== null && actualOf(task) !== null
        ? h('span', {
          class: (actualOf(task) - estimateOf(task)) > 0 ? 'delta-over' : 'delta-under',
          title: 'Actual minus estimate',
          text: (actualOf(task) - estimateOf(task) > 0 ? '+' : '') + fmtHours(Number(actualOf(task)) - Number(estimateOf(task)))
        })
        : null));
  }

  const foot = h('div', { class: 'task-card-foot' });
  if (gates.length) {
    foot.appendChild(h('div', { class: 'task-card-line' },
      h('span', { text: 'gates' }),
      h('span', { class: 'mono', text: passed + '/' + gates.length })));
    foot.appendChild(progressBar(passed, gates.length, passed === gates.length ? 'is-ok' : ''));
  } else {
    foot.appendChild(h('div', { class: 'task-card-line' },
      h('span', { text: 'gates' }), h('span', { class: 'mono', text: '—' })));
  }
  foot.appendChild(tokenBar(task));
  card.appendChild(foot);
  return card;
}

function renderStagePanel() {
  const stages = state.snapshot.stages || [];
  const panel = h('aside', { class: 'stage-panel card-panel panel-pad', 'aria-label': 'Stage progress' });
  panel.appendChild(h('div', { class: 'between', style: { marginBottom: '4px' } },
    h('span', { class: 'section-title', text: 'Stages' }),
    h('span', { class: 'faint text-sm', text: 'done / total' })));

  if (!stages.length) {
    panel.appendChild(h('div', { class: 'hint', text: 'This board declares no stages.' }));
    return panel;
  }

  const list = h('div', { class: 'stage-list' });
  for (const stage of stages) {
    const total = Array.isArray(stage.tasks) ? stage.tasks.length : 0;
    const open = Array.isArray(stage.tasks_open) ? stage.tasks_open.length : 0;
    const done = Math.max(0, total - open);
    const color = stage.complete ? 'green' : (stage.stopped ? 'red' : (stage.owner_pending ? 'amber' : 'blue'));
    const flags = [];
    if (stage.complete) flags.push({ text: 'complete', cls: '' });
    if (stage.stopped) flags.push({ text: 'stopped', cls: 'is-stop' });
    if (stage.owner_pending) flags.push({ text: 'owner pending', cls: 'is-pending' });
    if (!stage.complete && Array.isArray(stage.missing_gates) && stage.missing_gates.length) {
      flags.push({ text: 'missing: ' + stage.missing_gates.join(', '), cls: '' });
    }

    const item = h('div', { class: 'stage-item', title: stage.goal || stage.title || stage.id },
      h('div', { class: 'stage-item-top' },
        h('span', { class: 'column-dot st-' + color }),
        h('span', { class: 'stage-name', text: stage.title || stage.id }),
        h('span', { class: 'stage-count', text: done + '/' + total })),
      progressBar(done, total, stage.complete ? 'is-ok' : (stage.stopped ? 'is-over' : '')));
    if (flags.length) {
      const flagsRow = h('div', { class: 'stage-flags' });
      for (const flag of flags) flagsRow.appendChild(h('span', { class: 'stage-flag ' + flag.cls, text: flag.text }));
      item.appendChild(flagsRow);
    }
    list.appendChild(item);
  }
  panel.appendChild(list);
  return panel;
}

/* =========================================================================
   22. Table view
   ========================================================================= */

function renderTable() {
  const snapshot = state.snapshot;
  const tasks = snapshot.tasks || [];
  const project = snapshot.project || {};
  const view = h('div', { class: 'table-view' + (state.density === 'compact' ? ' density-compact' : '') });
  dom.view.appendChild(view);

  view.appendChild(h('div', { class: 'view-head' },
    h('div', {},
      h('h1', { class: 'view-title', text: 'Table' }),
      h('p', {
        class: 'view-sub',
        text: [tasks.length + ' ' + plural(tasks.length, 'task'),
          project.profile ? 'profile ' + project.profile : ''].filter(Boolean).join(' · ')
      })),
    h('div', { class: 'view-actions' },
      h('button', { class: 'btn btn-sm', type: 'button', text: 'Refresh', on: { click: () => refreshSnapshotButton() } }))));

  view.appendChild(renderFilters());
  if (canWrite()) view.appendChild(renderBulkBar());

  if (!tasks.length) {
    view.appendChild(emptyState('No tasks on the board', 'Add tasks in the Plan view.', null));
    return;
  }

  const filtered = visibleTasks();
  if (!filtered.length) {
    view.appendChild(emptyState('No matching tasks', 'Adjust the filters or clear them.', null));
    return;
  }

  const withViews = feature('views');
  const sorted = withViews
    ? sortTaskList(filtered, (state.sort && state.sort.field) || 'id', (state.sort && state.sort.dir) || 'asc')
    : filtered;
  const groupBy = withViews ? (state.groupBy || 'status') : 'status';
  const groups = withViews
    ? groupTaskList(sorted, groupBy)
    : [{ key: 'all', label: null, tasks: sorted }];

  const columns = [
    { key: 'task', label: 'Task' },
    { key: 'labels', label: 'Labels' },
    { key: 'status', label: 'Status' },
    { key: 'stage', label: 'Stage' },
    { key: 'owner', label: 'Owner' },
    { key: 'gates', label: 'Gates' },
    { key: 'effort', label: 'Effort' },
    { key: 'tokens', label: 'Tokens' },
    { key: 'attempt', label: 'Attempts' },
    { key: 'deps', label: 'Depends on' },
    { key: 'package', label: 'Package' }
  ];
  const withSelection = canWrite();
  const columnCount = columns.length + (withSelection ? 1 : 0);
  const visibleIds = filtered.map((task) => task.id);
  const allSelected = visibleIds.length > 0 && visibleIds.every((taskId) => bulkIsSelected(taskId));

  const table = h('table', { class: 'table' });
  const thead = h('thead');
  const headRow = h('tr');
  if (withSelection) {
    headRow.appendChild(h('th', { class: 'cell-check' },
      h('input', {
        class: 'bulk-check', type: 'checkbox', checked: allSelected,
        'aria-label': 'Select all visible tasks',
        on: { change: (event) => selectAllVisibleBulk(event.target.checked) }
      })));
  }
  for (const column of columns) headRow.appendChild(h('th', { text: column.label }));
  thead.appendChild(headRow);
  table.appendChild(thead);

  const tbody = h('tbody');
  const showGroups = withViews && groups.length > 1;
  for (const group of groups) {
    if (showGroups) {
      tbody.appendChild(h('tr', { class: 'group-row' },
        h('td', { colspan: String(columnCount) },
          h('span', { text: group.label }),
          h('span', { class: 'group-count', text: String(group.tasks.length) }))));
    }
    for (const task of group.tasks) tbody.appendChild(renderTableRow(task, columnCount));
  }
  table.appendChild(tbody);

  view.appendChild(h('div', { class: 'table-wrap' }, table));
  view.appendChild(h('p', {
    class: 'hint', style: { marginTop: '8px' },
    text: 'Click a row to open the task drawer. Tick rows for bulk actions; Ctrl/Cmd+K opens the command palette.'
  }));
}

function renderTableRow(task, columnCount) {
  const meta = stMeta(task.status);
  const gates = task.gates || [];
  const passed = (task.gates_passed || []).length;
  const maxTokens = task.budget && task.budget.max ? Number(task.budget.max) : 0;
  const used = Number(task.tokens) || 0;
  const labels = taskLabelIds(task);
  const row = h('tr', {
    dataset: { taskId: task.id },
    tabindex: '0',
    'aria-label': 'Open task ' + task.id,
    on: {
      click: () => openTask(task.id),
      keydown: (event) => {
        if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); openTask(task.id); }
      }
    }
  });

  if (canWrite()) row.appendChild(h('td', { class: 'cell-check' }, bulkCheckbox(task)));

  row.appendChild(h('td', { class: 'cell-task' },
    h('div', { class: 'cell-task-title', text: task.title || '(untitled)' }),
    h('div', { class: 'cell-mono', text: task.id })));

  row.appendChild(h('td', {}, labels.length ? labelChips(labels, 2) : h('span', { class: 'faint', text: '—' })));
  row.appendChild(h('td', {}, statusPill(task.status)));
  row.appendChild(h('td', { class: 'nowrap', text: task.stage_title || String(task.stage || '—') }));
  row.appendChild(h('td', { class: 'nowrap', text: task.owner || '—' }));

  row.appendChild(h('td', { class: 'cell-gates' },
    gates.length
      ? h('div', { class: 'gate-mini' },
        h('span', { class: 'mini-num', text: passed + '/' + gates.length }),
        progressBar(passed, gates.length, passed === gates.length ? 'is-ok' : ''))
      : h('span', { class: 'faint', text: '—' })));

  row.appendChild(effortCell(task));

  row.appendChild(h('td', {},
    h('span', { class: 'cell-mono', text: maxTokens ? fmtTokens(used) + ' / ' + fmtTokens(maxTokens) : fmtTokens(used) }),
    maxTokens
      ? progressBar(used, maxTokens, task.budget && task.budget.over ? 'is-over' : (task.budget && task.budget.warn ? 'is-warn' : ''))
      : null));

  row.appendChild(h('td', { class: 'cell-mono', text: String(task.attempt || 0) + (task.max_attempts ? ' / ' + task.max_attempts : '') }));

  const deps = task.depends_on || [];
  row.appendChild(h('td', { class: 'cell-dep' },
    deps.length
      ? h('div', { class: 'row-wrap', style: { gap: '3px' } }, deps.map((dep) => taskChip(dep)))
      : h('span', { class: 'faint', text: '—' })));
  row.appendChild(h('td', { class: 'nowrap', text: task.package || '—' }));
  return row;
}

function effortCell(task) {
  const estimate = estimateOf(task);
  const actual = actualOf(task);
  if (estimate === null && actual === null) return h('td', { class: 'effort-cell faint', text: '—' });
  const delta = estimate !== null && actual !== null ? Number(actual) - Number(estimate) : null;
  return h('td', { class: 'effort-cell' },
    h('div', { text: [
      estimate !== null ? 'est ' + fmtHours(estimate) : '',
      actual !== null ? 'act ' + fmtHours(actual) : ''
    ].filter(Boolean).join(' · ') }),
    delta !== null
      ? h('div', {
        class: delta > 0 ? 'delta-over' : 'delta-under',
        title: 'Actual minus estimate',
        text: (delta > 0 ? '+' : '') + fmtHours(delta)
      })
      : null);
}
/* =========================================================================
   23. Task detail drawer
   ========================================================================= */

const BASE_DRAWER_TABS = [
  { key: 'brief', label: 'Brief' },
  { key: 'gates', label: 'Gates' },
  { key: 'run', label: 'Run' },
  { key: 'review', label: 'Review' },
  { key: 'evidence', label: 'Evidence' },
  { key: 'handoff', label: 'Handoff' },
  { key: 'session', label: 'Session' }
];

function drawerTabs() {
  const tabs = BASE_DRAWER_TABS.slice();
  if (feature('worklog')) tabs.push({ key: 'worklog', label: 'Worklog' });
  return tabs;
}

function canWrite() {
  const config = state.config;
  const snapshot = state.snapshot;
  const readOnlyConfig = Boolean(config && config.read_only);
  const readOnlySnapshot = Boolean(snapshot && snapshot.dashboard && snapshot.dashboard.read_only);
  return !readOnlyConfig && !readOnlySnapshot;
}

function ensureDrawer(taskId) {
  if (state.drawer.id === taskId) return;
  state.drawer.id = taskId;
  state.drawer.detail = null;
  state.drawer.error = null;
  state.drawer.loading = true;
  state.drawer.tab = 'brief';
  state.drawer.note = '';
  state.drawer.actionError = null;
  state.drawer.busy = null;
  state.drawer.evidenceLog = null;
  state.drawer.watch = null;
  state.drawer.gate = { name: '', command: '', timeout: '1800' };
  state.drawer.sessionForm = { role: 'worker', worktree: false, note: '' };
  state.drawer.props = null;
  clearDrawerTimers();
  state.drawer.sessionPoll = null;
  dom.drawer.hidden = false;
  dom.drawer.setAttribute('aria-hidden', 'false');
  dom.drawerBackdrop.hidden = false;
  document.body.style.overflow = 'hidden';
  renderDrawer();
  loadDrawer(taskId);
}

function closeDrawer(updateHash) {
  if (!state.drawer.id && dom.drawer.hidden) return;
  state.drawer.id = null;
  state.drawer.detail = null;
  state.drawer.watch = null;
  clearDrawerTimers();
  state.drawer.sessionPoll = null;
  dom.drawer.hidden = true;
  dom.drawer.setAttribute('aria-hidden', 'true');
  dom.drawerBackdrop.hidden = true;
  document.body.style.overflow = '';
  clear(dom.drawer);
  if (!updateHash) return;
  if (state.route.view === 'pages') {
    const base = state.pagesSelected ? '#/pages/' + encodeURIComponent(state.pagesSelected) : '#/pages';
    try { history.replaceState(null, '', base); } catch (err) { location.hash = base; }
    applyRoute();
  } else {
    navigate(state.route.view, null);
  }
}

async function loadDrawer(taskId, quiet) {
  if (!quiet) {
    state.drawer.loading = true;
    renderDrawer();
  }
  try {
    const detail = await api('/api/tasks/' + encodeURIComponent(taskId));
    if (state.drawer.id !== taskId) return;
    state.drawer.detail = detail;
    state.drawer.error = null;
    const gates = (detail.task && detail.task.gates) || [];
    if (!state.drawer.gate.name && gates.length) {
      state.drawer.gate.name = gates[0];
      state.drawer.gate.command = gateCommandFor(gates[0], detail);
    }
  } catch (err) {
    if (state.drawer.id !== taskId) return;
    state.drawer.error = err;
  }
  state.drawer.loading = false;
  renderDrawer();
  if (!state.sessionsLoaded) loadSessions({ quiet: true });
}

function gateCommandFor(name, detail) {
  const configured = state.config && state.config.gate_commands ? state.config.gate_commands[name] : '';
  if (configured) return configured;
  if (detail && Array.isArray(detail.gate_records)) {
    const record = detail.gate_records.find((entry) => entry.gate === name && entry.command);
    if (record) return record.command;
  }
  return '';
}

function currentDrawerTask() {
  const detail = state.drawer.detail;
  if (detail && detail.task) return detail.task;
  return taskById(state.drawer.id) || { id: state.drawer.id, title: 'Task ' + state.drawer.id, status: 'pending', stage: null, owner: null };
}

function renderDrawer() {
  if (!state.drawer.id) {
    dom.drawer.hidden = true;
    dom.drawerBackdrop.hidden = true;
    return;
  }
  dom.drawer.hidden = false;
  dom.drawerBackdrop.hidden = false;
  if (state.drawer.tab === 'worklog' && !feature('worklog')) state.drawer.tab = 'brief';
  const focusSnapshot = captureFocus();
  const task = currentDrawerTask();
  const detail = state.drawer.detail;
  clear(dom.drawer);

  const head = h('div', { class: 'drawer-head' });

  const top = h('div', { class: 'drawer-top' },
    h('span', { class: 'task-id', text: task.id || '' }),
    statusPill(task.status),
    task.claim ? h('span', { class: 'claim-badge', title: 'Live claim' }, h('span', { class: 'dot' }), 'claimed') : null,
    h('button', {
      class: 'drawer-close', type: 'button', 'aria-label': 'Close task detail', text: '×',
      on: { click: () => closeDrawer(true) }
    }));
  head.appendChild(top);
  head.appendChild(h('h2', { class: 'drawer-title', text: task.title || '(untitled)' }));

  const metaRow = h('div', { class: 'drawer-meta' });
  if (task.stage_title || task.stage) metaRow.appendChild(pill(task.stage_title || String(task.stage), '', 'Stage'));
  if (task.owner) metaRow.appendChild(pill('owner ' + task.owner, '', 'Owner'));
  if (task.package) metaRow.appendChild(pill('package ' + task.package, '', 'Package'));
  if (task.parallel_group) metaRow.appendChild(pill('group ' + task.parallel_group, '', 'Parallel group'));
  if (task.complexity !== null && task.complexity !== undefined) metaRow.appendChild(pill('complexity ' + task.complexity, '', 'Complexity'));
  if (task.round !== null && task.round !== undefined) {
    metaRow.appendChild(pill('round ' + task.round + (task.max_rounds ? '/' + task.max_rounds : ''), '', 'Review round'));
  }
  if (task.attempt || task.max_attempts) {
    metaRow.appendChild(pill('attempt ' + (task.attempt || 0) + (task.max_attempts ? '/' + task.max_attempts : ''), '', 'Attempts'));
  }
  if (task.running) metaRow.appendChild(pill('running', 'pill-accent', 'A dispatch plan lists this task as running'));
  if (task.conflicted) metaRow.appendChild(pill('conflict', 'pill-danger', 'Scope overlaps with another task'));
  if (task.ready && task.wave !== null && task.wave !== undefined) metaRow.appendChild(pill('wave ' + (task.wave + 1), '', 'Ready in this wave'));
  if (taskLabelIds(task).length) metaRow.appendChild(labelChips(taskLabelIds(task)));
  head.appendChild(metaRow);

  head.appendChild(renderDrawerActions(task, detail));
  head.appendChild(renderDrawerTabs(task));
  dom.drawer.appendChild(head);

  const body = h('div', { class: 'drawer-body' });
  if (state.drawer.loading && !detail) {
    body.appendChild(loadingRow('Loading task…'));
  } else if (state.drawer.error && !detail) {
    body.appendChild(errorCallout(state.drawer.error));
    body.appendChild(h('div', { style: { marginTop: '10px' } },
      h('button', {
        class: 'btn', type: 'button', text: 'Retry',
        on: { click: () => loadDrawer(state.drawer.id) }
      })));
  } else {
    append(body, [renderDrawerTab(task, detail)]);
  }
  dom.drawer.appendChild(body);
  restoreFocus(focusSnapshot);
}

function renderDrawerActions(task, detail) {
  const wrap = h('div', { class: 'drawer-actions' });
  const readOnly = !canWrite();
  const quick = h('div', { class: 'quick-actions' });

  /* status transitions */
  const targets = TRANSITIONS[task.status] || [];
  const next = task.next_status;
  const row = h('div', { class: 'quick-row' },
    h('span', { class: 'quick-label', text: 'Status' }));
  if (!targets.length) {
    row.appendChild(h('span', { class: 'hint', text: 'No quick transitions from ' + stMeta(task.status).label + '.' }));
  }
  for (const target of targets) {
    const label = stMeta(target).label;
    const needsNote = NOTE_TARGETS.has(target);
    row.appendChild(h('button', {
      class: 'btn btn-sm transition-btn ' + (target === next ? 'btn-primary' : ''),
      type: 'button',
      disabled: readOnly || state.drawer.busy === 'transition',
      title: readOnly ? 'The dashboard is read-only' : ('Set status to ' + label + (needsNote ? ' (a note is required)' : '')),
      text: target === next ? '→ ' + label : '→ ' + label,
      on: { click: () => doTransition(target) }
    }));
  }
  quick.appendChild(row);

  /* transition note */
  const noteInput = h('input', {
    class: 'input',
    type: 'text',
    placeholder: 'Transition note (required for rework, blocked, failed)',
    value: state.drawer.note,
    'data-fkey': 'transition-note',
    'aria-label': 'Transition note',
    on: { input: (event) => { state.drawer.note = event.target.value; } }
  });
  quick.appendChild(h('div', { class: 'quick-row' },
    h('span', { class: 'quick-label', text: 'Note' }), noteInput));

  /* claim / release */
  const claimRow = h('div', { class: 'quick-row' },
    h('span', { class: 'quick-label', text: 'Claim' }));
  if (task.claim) {
    const claim = task.claim;
    claimRow.appendChild(h('span', {
      class: 'chip',
      title: 'Claimed by ' + (claim.harness || 'session') + ' since ' + (claim.started || '')
    }, h('span', { class: 'dot st-blue' }),
      'held by ' + (claim.harness || 'session') + (claim.session ? ' · ' + claim.session : '')));
    claimRow.appendChild(h('button', {
      class: 'btn btn-sm', type: 'button', text: 'Release', disabled: readOnly || state.drawer.busy === 'claim',
      title: 'DELETE /api/tasks/<id>/claim',
      on: { click: () => doReleaseClaim() }
    }));
  } else {
    claimRow.appendChild(h('button', {
      class: 'btn btn-sm', type: 'button', text: 'Claim task', disabled: readOnly || state.drawer.busy === 'claim',
      title: 'POST /api/tasks/<id>/claim',
      on: { click: () => doClaimTask() }
    }));
  }
  quick.appendChild(claimRow);

  /* copyable CLI helpers */
  const stateCommand = 'python3 tools/state.py set ' + task.id + ' ' + (next || task.status || 'in_progress');
  const gateName = state.drawer.gate.name || ((task.gates || [])[0] || '');
  const gateCommand = gateName && detail ? gateCommandFor(gateName, detail) : '';
  const gateCommandFull = 'python3 tools/gate.py --task ' + task.id + ' --name ' + (gateName || '<gate>') +
    ' --shell ' + JSON.stringify(gateCommand || '<command>');
  const cliRow = h('div', { class: 'quick-row' },
    h('span', { class: 'quick-label', text: 'CLI' }));
  cliRow.appendChild(cliButton('Copy state', stateCommand));
  cliRow.appendChild(cliButton('Copy gate', gateCommandFull));
  quick.appendChild(cliRow);

  if (state.drawer.actionError) {
    quick.appendChild(errorCallout(state.drawer.actionError, { class: 'inline-error' }));
  }
  wrap.appendChild(quick);
  return wrap;
}

function cliButton(label, command) {
  return h('button', {
    class: 'btn btn-sm', type: 'button', text: label, title: command,
    on: { click: () => copyText(command) }
  });
}

function renderDrawerTabs(task) {
  const tabs = h('div', { class: 'drawer-tabs', role: 'tablist', 'aria-label': 'Task detail sections' });
  for (const tab of drawerTabs()) {
    tabs.appendChild(h('button', {
      class: 'drawer-tab',
      type: 'button',
      role: 'tab',
      'aria-selected': state.drawer.tab === tab.key ? 'true' : 'false',
      'data-fkey': 'drawer-tab-' + tab.key,
      on: { click: () => setDrawerTab(tab.key) }
    }, tab.label));
  }
  return tabs;
}

function setDrawerTab(tab) {
  if (state.drawer.tab === tab) return;
  state.drawer.tab = tab;
  state.drawer.actionError = null;
  renderDrawer();
  if (tab === 'session') {
    loadSessions({ quiet: true });
    ensureDrawerSessionPolling();
    const active = (state.sessions || []).find((session) => session.task === state.drawer.id && SESSION_ACTIVE.has(session.status));
    if (active && !state.drawer.watch) startDrawerWatch(active.id);
  }
}

function ensureDrawerSessionPolling() {
  if (state.drawer.sessionPoll) return;
  state.drawer.sessionPoll = setDrawerInterval(() => loadSessions({ quiet: true }), 2500);
}

/* ---------- drawer actions ---------- */

async function doTransition(target) {
  const task = currentDrawerTask();
  const note = String(state.drawer.note || '').trim();
  if (NOTE_TARGETS.has(target) && !note) {
    state.drawer.actionError = new ApiError('A note is required to move a task to "' + target + '".', 400, null);
    renderDrawer();
    const input = document.querySelector('[data-fkey="transition-note"]');
    focusSoon(input);
    return;
  }
  state.drawer.actionError = null;
  state.drawer.busy = 'transition';
  renderDrawer();
  try {
    await api('/api/tasks/' + encodeURIComponent(task.id) + '/state', {
      method: 'POST',
      body: { status: target, note: note || undefined, actor: 'dashboard' }
    });
    state.drawer.note = '';
    toast(task.id + ' → ' + stMeta(target).label, 'ok');
    state.drawer.detail = null;
    await loadSnapshot();
    renderHeader();
    renderTabs();
    renderView();
    if (state.drawer.id) await loadDrawer(state.drawer.id, true);
  } catch (err) {
    state.drawer.actionError = err;
    toast(err.status === 409 ? 'Transition refused (409) — see the drawer' : 'State change failed: ' + describeError(err), 'error');
  } finally {
    state.drawer.busy = null;
    renderDrawer();
  }
}

async function doClaimTask() {
  const task = currentDrawerTask();
  state.drawer.busy = 'claim';
  state.drawer.actionError = null;
  renderDrawer();
  try {
    await api('/api/tasks/' + encodeURIComponent(task.id) + '/claim', {
      method: 'POST',
      body: { harness: 'dashboard' }
    });
    toast('Claimed ' + task.id, 'ok');
    await loadSnapshot();
    renderView();
    if (state.drawer.id) await loadDrawer(state.drawer.id, true);
  } catch (err) {
    state.drawer.actionError = err;
    toast('Claim failed: ' + describeError(err), 'error');
  } finally {
    state.drawer.busy = null;
    renderDrawer();
  }
}

async function doReleaseClaim() {
  const task = currentDrawerTask();
  state.drawer.busy = 'claim';
  state.drawer.actionError = null;
  renderDrawer();
  try {
    await api('/api/tasks/' + encodeURIComponent(task.id) + '/claim', { method: 'DELETE' });
    toast('Released ' + task.id, 'ok');
    await loadSnapshot();
    renderView();
    if (state.drawer.id) await loadDrawer(state.drawer.id, true);
  } catch (err) {
    state.drawer.actionError = err;
    toast('Release failed: ' + describeError(err), 'error');
  } finally {
    state.drawer.busy = null;
    renderDrawer();
  }
}

/* ---------- drawer tab bodies ---------- */

function renderDrawerTab(task, detail) {
  if (state.drawer.tab === 'worklog' && !feature('worklog')) state.drawer.tab = 'brief';
  switch (state.drawer.tab) {
    case 'gates': return drawerGatesTab(task, detail);
    case 'run': return drawerRunTab(task, detail);
    case 'review': return drawerReviewTab(task, detail);
    case 'evidence': return drawerEvidenceTab(task, detail);
    case 'handoff': return drawerHandoffTab(task, detail);
    case 'session': return drawerSessionTab(task, detail);
    case 'worklog': return drawerWorklogTab(task, detail);
    default: return drawerBriefTab(task, detail);
  }
}

function drawerBriefTab(task, detail) {
  const body = h('div');
  body.appendChild(renderTaskProperties(task, detail));

  const goal = h('section', { class: 'drawer-section' },
    h('div', { class: 'drawer-label', text: 'Goal' }),
    h('div', { class: 'md' }, mdFragment(task.goal || '(no goal recorded)')));
  body.appendChild(goal);
  if (task.why) {
    body.appendChild(h('section', { class: 'drawer-section' },
      h('div', { class: 'drawer-label', text: 'Why' }),
      h('div', { class: 'md' }, mdFragment(task.why))));
  }
  if (task.acceptance && task.acceptance.length) {
    body.appendChild(h('section', { class: 'drawer-section' },
      h('div', { class: 'drawer-label', text: 'Acceptance' }),
      h('div', { class: 'row-wrap' }, task.acceptance.map((item) => h('span', { class: 'chip', text: String(item) })))));
  }
  body.appendChild(h('section', { class: 'drawer-section' },
    h('div', { class: 'drawer-label', text: 'Brief' }),
    detail ? mdBlock(detail.brief && detail.brief.text, 'No brief at tasks/' + task.id + '.md yet.')
      : loadingRow('Loading brief…')));
  if (detail && detail.brief) {
    body.appendChild(h('p', { class: 'hint', style: { marginTop: '8px' },
      text: (detail.brief.path || 'tasks/' + task.id + '.md') + ' · ' + relTime(detail.brief.updated) }));
  }
  return body;
}
function drawerPropsState(task) {
  if (!state.drawer.props || !state.drawer.props.init || state.drawer.props.taskId !== task.id) {
    const planning = planningFor(task.id);
    state.drawer.props = {
      init: true,
      taskId: task.id,
      labels: taskLabelIds(task).slice(),
      estimate: estimateOf(task) === null ? '' : String(estimateOf(task)),
      planned_start: planning.planned_start || '',
      target: planning.target || '',
      datesReady: Boolean(state.planningDatesLoaded),
      open: false
    };
  }
  const props = state.drawer.props;
  if (!props.datesReady && state.planningDatesLoaded) {
    const planning = planningFor(task.id);
    props.planned_start = planning.planned_start || '';
    props.target = planning.target || '';
    props.datesReady = true;
  }
  return props;
}

function planningSummaryText(plannedStart, target) {
  if (!plannedStart && !target) return 'no planning dates';
  return (plannedStart || '—') + ' → ' + (target || '—');
}

function renderTaskProperties(task, detail) {
  const readOnly = !canWrite() || task.status === 'done';
  const props = drawerPropsState(task);
  const section = h('section', { class: 'drawer-section' });
  section.appendChild(h('div', { class: 'drawer-label', text: 'Properties' }));

  /* planning dates come from board.json (schema 1.2) via /api/file */
  if (!state.planningDatesLoaded && !state.planningDatesLoading) {
    loadPlanningDates().then(() => { if (state.drawer.id === task.id) renderDrawer(); });
  }
  const planningReady = state.planningDatesLoaded;
  const planningText = planningSummaryText(props.planned_start, props.target);
  const timelineLink = feature('timeline') && (props.planned_start || props.target)
    ? h('button', {
      class: 'btn btn-sm btn-ghost', type: 'button', text: 'Show in timeline',
      title: 'Open the timeline view',
      on: { click: () => navigate('timeline') }
    })
    : null;

  if (readOnly) {
    section.appendChild(h('div', { class: 'props' },
      h('div', { class: 'props-current' },
        taskLabelIds(task).length
          ? taskLabelIds(task).map((id) => labelById(id) ? labelChip(labelById(id)) : h('span', { class: 'chip mono', text: id }))
          : h('span', { class: 'hint', text: 'No labels' })),
      h('div', { class: 'hint', text: 'Estimate: ' + (estimateOf(task) === null ? 'none' : fmtHours(estimateOf(task))) }),
      h('div', { class: 'hint', text: 'Timeline: ' + (planningReady ? planningText : 'loading…') }),
      h('div', { class: 'hint', text: task.status === 'done'
        ? 'A done task is reopened through the state machine before its plan is edited.'
        : 'The dashboard is read-only.' })));
    return section;
  }

  const labelGrid = h('div', { class: 'props-labels' });
  const labels = settingsLabels();
  const groups = settingsGroups();
  let anyGroup = false;
  for (const group of groups) {
    const inGroup = labels.filter((label) => (groups.indexOf(label.group) !== -1 ? label.group : 'custom') === group);
    if (!inGroup.length) continue;
    anyGroup = true;
    labelGrid.appendChild(h('span', { class: 'props-label-group', text: group }));
    for (const label of inGroup) {
      labelGrid.appendChild(h('label', { class: 'checkbox' },
        h('input', {
          type: 'checkbox', value: label.id, checked: props.labels.indexOf(label.id) !== -1,
          on: {
            change: (event) => {
              const current = state.drawer.props.labels.slice();
              const index = current.indexOf(label.id);
              if (event.target.checked && index === -1) current.push(label.id);
              if (!event.target.checked && index !== -1) current.splice(index, 1);
              state.drawer.props.labels = current;
            }
          }
        }),
        labelChip(label)));
    }
  }
  if (!anyGroup) labelGrid.appendChild(h('span', { class: 'hint', text: 'No labels defined in Settings.' }));

  const estimateInput = h('input', {
    class: 'input', type: 'number', min: '0', max: '10000', step: '0.5',
    value: props.estimate, placeholder: 'none',
    on: { input: (event) => { state.drawer.props.estimate = event.target.value; } }
  });
  const startInput = h('input', {
    class: 'input', type: 'date', value: props.planned_start,
    'aria-label': 'Planned start', disabled: !planningReady,
    title: planningReady ? '' : 'Loading the planning dates from board.json…',
    on: { input: (event) => { state.drawer.props.planned_start = event.target.value; } }
  });
  const targetInput = h('input', {
    class: 'input', type: 'date', value: props.target,
    'aria-label': 'Target date', disabled: !planningReady,
    title: planningReady ? '' : 'Loading the planning dates from board.json…',
    on: { input: (event) => { state.drawer.props.target = event.target.value; } }
  });

  const details = h('details', {
    open: props.open,
    on: { toggle: (event) => { state.drawer.props.open = event.target.open; } }
  });
  details.appendChild(h('summary', {
    class: 'hint',
    style: { cursor: 'pointer', marginBottom: '6px' },
    text: 'Labels (' + (props.labels.length || 0) + ' selected)'
  }));
  details.appendChild(labelGrid);

  section.appendChild(h('div', { class: 'props' },
    details,
    h('div', { class: 'hint', text: 'Timeline: ' + (planningReady ? planningText : 'loading planning dates…') }),
    h('div', { class: 'props-row' },
      h('label', { class: 'field' },
        h('span', { class: 'field-label', text: 'Estimate (hours)' }), estimateInput,
        h('span', { class: 'field-help', text: 'Empty clears the estimate.' })),
      h('label', { class: 'field' },
        h('span', { class: 'field-label', text: 'Planned start' }), startInput,
        h('span', { class: 'field-help', text: 'Empty clears the date.' })),
      h('label', { class: 'field' },
        h('span', { class: 'field-label', text: 'Target' }), targetInput,
        h('span', { class: 'field-help', text: 'Must not be before the planned start.' }))),
    h('div', { class: 'form-actions' },
      h('button', {
        class: 'btn btn-sm btn-primary', type: 'button', text: 'Save properties',
        disabled: state.drawer.busy === 'properties',
        on: { click: () => saveTaskProperties() }
      }),
      timelineLink,
      state.planningDatesError ? h('span', { class: 'hint st-amber', text: 'planning dates unavailable: ' + describeError(state.planningDatesError) }) : null)));
  if (state.drawer.actionError) section.appendChild(errorCallout(state.drawer.actionError, { class: 'inline-error' }));
  return section;
}

async function saveTaskProperties() {
  const task = currentDrawerTask();
  const props = state.drawer.props || {};
  if (!task || !canWrite()) return;
  if (task.status === 'done') { toast('Done tasks are reopened before their plan is edited', 'warn'); return; }
  const payload = { labels: (props.labels || []).slice() };
  const estimateText = String(props.estimate === undefined || props.estimate === null ? '' : props.estimate).trim();
  if (estimateText === '') {
    payload.estimate_hours = null;
  } else {
    const number = Number(estimateText);
    if (!isFinite(number) || number < 0 || number > 10000) {
      state.drawer.actionError = new ApiError('Estimate must be a number between 0 and 10000.', 400, null);
      renderDrawer();
      return;
    }
    payload.estimate_hours = number;
  }
  /* Only touch planning dates once board.json was read; otherwise a
     label-only save would silently clear dates the snapshot does not expose. */
  const datesReady = props.datesReady === true || state.planningDatesLoaded === true;
  const plannedStart = datesReady ? (String(props.planned_start || '').trim() || null) : undefined;
  const target = datesReady ? (String(props.target || '').trim() || null) : undefined;
  if (plannedStart && !/^\d{4}-\d{2}-\d{2}$/.test(plannedStart)) {
    state.drawer.actionError = new ApiError('Planned start must be an ISO date (YYYY-MM-DD).', 400, null);
    renderDrawer();
    return;
  }
  if (target && !/^\d{4}-\d{2}-\d{2}$/.test(target)) {
    state.drawer.actionError = new ApiError('Target must be an ISO date (YYYY-MM-DD).', 400, null);
    renderDrawer();
    return;
  }
  if (plannedStart && target && target < plannedStart) {
    state.drawer.actionError = new ApiError('Target must not be before the planned start.', 400, null);
    renderDrawer();
    return;
  }
  if (datesReady) {
    payload.planned_start = plannedStart;
    payload.target = target;
  }

  state.drawer.busy = 'properties';
  state.drawer.actionError = null;
  renderDrawer();
  try {
    const saved = await api('/api/plan/tasks/' + encodeURIComponent(task.id), { method: 'PATCH', body: payload });
    setPlanningFor(task.id, saved && saved.planned_start, saved && saved.target);
    if (saved && Object.prototype.hasOwnProperty.call(saved, 'planned_start') && !saved.planned_start) {
      setPlanningFor(task.id, null, saved.target);
    }
    toast('Properties saved', 'ok');
    state.drawer.props = null;
    await loadSnapshot();
    renderHeader();
    renderView();
    if (state.route.view === 'timeline') await loadTimeline();
    if (state.route.view === 'timeline') renderView();
    if (state.drawer.id) await loadDrawer(state.drawer.id, true);
    if (feature('worklog')) loadWorklog();
  } catch (err) {
    state.drawer.actionError = err;
    toast('Properties: ' + describeError(err), 'error');
  } finally {
    state.drawer.busy = null;
    renderDrawer();
  }
}

function worklogKpi(label, value, className) {
  return h('div', { class: 'wl-kpi' },
    h('div', { class: 'wl-kpi-label', text: label }),
    h('div', { class: 'wl-kpi-value ' + (className || ''), text: value }));
}

function drawerWorklogTab(task, detail) {
  const body = h('div');
  const worklog = detail && detail.worklog;
  if (!worklog) {
    body.appendChild(loadingRow('Loading worklog…'));
    return body;
  }
  const totals = worklog.totals || {};
  const estimate = worklog.estimate_hours;
  const actual = worklog.actual_hours;
  const delta = worklog.delta_hours;

  body.appendChild(h('div', { class: 'wl-kpis' },
    worklogKpi('Estimate', estimate === null || estimate === undefined ? '—' : fmtHours(estimate)),
    worklogKpi('Actual', actual === null || actual === undefined ? '—' : fmtHours(actual)),
    worklogKpi('Delta', delta === null || delta === undefined ? '—' : (delta > 0 ? '+' : '') + fmtHours(delta),
      delta === null || delta === undefined ? '' : (delta > 0 ? 'is-over' : (delta < 0 ? 'is-under' : ''))),
    worklogKpi('Tokens', fmtTokens(totals.tokens || 0)),
    worklogKpi('Sessions', String(totals.sessions || 0)),
    worklogKpi('Attempts', String(totals.attempts || 0)),
    worklogKpi('Gates', String(totals.gates || 0))));

  if (estimate === null && actual !== null) {
    body.appendChild(h('p', { class: 'hint', style: { marginTop: '-6px', marginBottom: '12px' },
      text: 'No estimate yet — add one in Properties to compare effort.' }));
  }

  body.appendChild(worklogTableSection('Attempts', ['#', 'Result', 'Started', 'Duration', 'Note'],
    (worklog.attempts || []).map((attempt) => [
      h('span', { class: 'wl-num', text: '#' + (attempt.n === null || attempt.n === undefined ? '?' : attempt.n) }),
      attempt.result ? statusPill(attempt.result === 'pass' ? 'done' : 'failed') : h('span', { class: 'faint', text: 'open' }),
      h('span', { title: attempt.started || '', text: relTime(attempt.started) }),
      h('span', { class: 'wl-num', text: fmtDuration(attempt.seconds || 0) }),
      attempt.note ? h('span', { text: truncate(attempt.note, 90) }) : h('span', { class: 'faint', text: '—' })
    ]), 'No attempts recorded.'));

  body.appendChild(worklogTableSection('Sessions', ['Session', 'Role', 'Status', 'Provider', 'Started', 'Duration', 'Tokens'],
    (worklog.sessions || []).map((session) => [
      h('span', { class: 'wl-num', text: session.id || '—' }),
      h('span', { text: session.role || '—' }),
      session.status ? statusPill(session.status) : h('span', { class: 'faint', text: '—' }),
      h('span', { text: session.provider || '—' }),
      h('span', { title: session.started || '', text: relTime(session.started) }),
      h('span', { class: 'wl-num', text: fmtDuration(session.seconds || 0) }),
      h('span', { class: 'wl-num', text: fmtTokens(session.tokens || 0) })
    ]), 'No headless sessions have run for this task.'));

  body.appendChild(worklogTableSection('Gates', ['Gate', 'Result', 'Started', 'Duration', 'Command', ''],
    (worklog.gates || []).map((gate) => [
      h('span', { class: 'mono', text: gate.gate || '—' }),
      gate.result ? h('span', { class: 'chip ' + (gate.result === 'pass' ? 'chip-pass' : 'chip-miss'), text: gate.result }) : h('span', { class: 'faint', text: '—' }),
      h('span', { title: gate.started || '', text: relTime(gate.started) }),
      h('span', { class: 'wl-num', text: fmtDuration(gate.seconds || 0) }),
      h('span', { class: 'mono', style: { maxWidth: '150px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', display: 'inline-block' }, title: gate.command || '', text: gate.command || '—' }),
      gate.record ? h('button', {
        class: 'btn btn-sm', type: 'button', text: 'Log',
        on: { click: () => loadEvidenceLog('reviews/evidence/' + gate.record) }
      }) : null
    ]), 'No gate records for this task.'));

  body.appendChild(worklogTableSection('Usage', ['Session', 'Tokens', 'Source', 'Updated'],
    (worklog.usage || []).map((usage) => [
      h('span', { class: 'wl-num', text: usage.session || '—' }),
      h('span', { class: 'wl-num', text: fmtTokens(usage.tokens || 0) }),
      h('span', { text: usage.source || '—' }),
      h('span', { title: usage.updated || '', text: relTime(usage.updated) })
    ]), 'No token usage recorded.'));

  return body;
}

function worklogTableSection(title, headings, rows, emptyText) {
  const section = h('section', { class: 'wl-section' });
  section.appendChild(h('div', { class: 'drawer-label', text: title }));
  if (!rows.length) {
    section.appendChild(h('div', { class: 'hint', text: emptyText }));
    return section;
  }
  const table = h('table', { class: 'wl-table' });
  const head = h('tr');
  for (const heading of headings) head.appendChild(h('th', { text: heading }));
  table.appendChild(h('thead', {}, head));
  const body = h('tbody');
  for (const row of rows) {
    const tr = h('tr');
    for (const cell of row) {
      if (cell === null || cell === undefined) {
        tr.appendChild(h('td'));
      } else if (cell instanceof Node) {
        tr.appendChild(h('td', {}, cell));
      } else {
        tr.appendChild(h('td', { text: String(cell) }));
      }
    }
    body.appendChild(tr);
  }
  table.appendChild(body);
  section.appendChild(table);
  return section;
}


function drawerGatesTab(task, detail) {
  const body = h('div');
  const declared = task.gates || [];
  const passed = task.gates_passed || [];
  const missing = task.gates_missing || [];

  body.appendChild(h('section', { class: 'drawer-section' },
    h('div', { class: 'drawer-label', text: 'Declared gates' }),
    declared.length
      ? h('div', { class: 'row-wrap' },
        declared.map((gate) => h('span', {
          class: 'chip ' + (passed.indexOf(gate) !== -1 ? 'chip-pass' : 'chip-miss'),
          title: passed.indexOf(gate) !== -1 ? 'A passing record exists' : 'No passing record yet'
        }, gate)))
      : h('div', { class: 'hint', text: 'This task declares no gates.' })));

  if (missing.length) {
    body.appendChild(h('section', { class: 'drawer-section' },
      h('div', { class: 'drawer-label', text: 'Missing' }),
      h('div', { class: 'row-wrap' }, missing.map((gate) => h('span', { class: 'chip chip-miss', text: gate })))));
  }

  if (detail && Array.isArray(detail.gate_records) && detail.gate_records.length) {
    const list = h('div', { class: 'col', style: { gap: '6px' } });
    for (const record of detail.gate_records.slice(0, 12)) {
      const result = String(record.result || '').toLowerCase();
      const color = result === 'pass' ? 'green' : (result === 'fail' ? 'red' : 'amber');
      list.appendChild(h('div', { class: 'session-row' },
        h('span', { class: 'badge bg-' + color + ' st-' + color }, h('span', { class: 'dot' }), record.result || 'unknown'),
        h('span', { class: 'mono', text: record.gate || 'gate' }),
        h('span', { class: 'hint', text: 'exit ' + (record.exit_code !== undefined ? record.exit_code : '?') }),
        h('span', { class: 'hint', text: relTime(record.started) }),
        record.log ? h('button', {
          class: 'btn btn-sm', type: 'button', style: { marginLeft: 'auto' }, text: 'Log',
          on: { click: () => loadEvidenceLog(record.log) }
        }) : null));
    }
    body.appendChild(h('section', { class: 'drawer-section' },
      h('div', { class: 'drawer-label', text: 'Gate records' }), list));
  }

  body.appendChild(renderGateRunner(task, detail));
  return body;
}

function renderGateRunner(task, detail) {
  const section = h('section', { class: 'drawer-section' });
  section.appendChild(h('div', { class: 'drawer-label', text: 'Run a gate' }));

  const names = [];
  for (const gate of task.gates || []) if (names.indexOf(gate) === -1) names.push(gate);
  if (detail && detail.stage && Array.isArray(detail.stage.exit_gates)) {
    for (const gate of detail.stage.exit_gates) if (names.indexOf(gate) === -1) names.push(gate);
  }
  if (state.config && state.config.gate_commands) {
    for (const key of Object.keys(state.config.gate_commands)) if (names.indexOf(key) === -1) names.push(key);
  }

  const form = h('div', { class: 'col', style: { gap: '8px' } });
  let nameControl;
  if (names.length) {
    nameControl = h('select', {
      class: 'select',
      'aria-label': 'Gate to run',
      on: {
        change: (event) => {
          state.drawer.gate.name = event.target.value;
          state.drawer.gate.command = gateCommandFor(event.target.value, detail);
          const input = document.getElementById('gate-command');
          if (input) input.value = state.drawer.gate.command;
        }
      }
    }, h('option', { value: '', text: 'Choose a gate…' }));
    for (const gate of names) {
      const option = h('option', { value: gate, text: gate });
      if (state.drawer.gate.name === gate) option.selected = true;
      nameControl.appendChild(option);
    }
    nameControl.value = state.drawer.gate.name || '';
  } else {
    nameControl = h('input', {
      class: 'input', type: 'text', placeholder: 'custom gate name', 'aria-label': 'Gate name',
      value: state.drawer.gate.name || '',
      on: { input: (event) => { state.drawer.gate.name = event.target.value; } }
    });
  }
  form.appendChild(h('label', { class: 'field' },
    h('span', { class: 'field-label', text: 'Gate name' }), nameControl));

  form.appendChild(h('label', { class: 'field' },
    h('span', { class: 'field-label', text: 'Command' }),
    h('input', {
      class: 'input', id: 'gate-command', type: 'text', value: state.drawer.gate.command,
      placeholder: 'e.g. pnpm test', 'data-fkey': 'gate-command',
      on: { input: (event) => { state.drawer.gate.command = event.target.value; } }
    }),
    h('span', { class: 'field-help', text: 'Runs as a shell command in the project root; output streams into the jobs tray.' })));

  form.appendChild(h('label', { class: 'field' },
    h('span', { class: 'field-label', text: 'Timeout (seconds)' }),
    h('input', {
      class: 'input', type: 'number', min: '1', value: state.drawer.gate.timeout,
      on: { input: (event) => { state.drawer.gate.timeout = event.target.value; } }
    })));

  form.appendChild(h('button', {
    class: 'btn btn-primary', type: 'button', text: 'Run gate',
    disabled: !canWrite() || state.drawer.busy === 'gate',
    title: !canWrite() ? 'The dashboard is read-only' : 'POST /api/jobs/gate',
    on: { click: () => runGateFromDrawer() }
  }));
  section.appendChild(form);
  return section;
}

async function runGateFromDrawer() {
  const task = currentDrawerTask();
  const gate = state.drawer.gate;
  const name = String(gate.name || '').trim();
  const command = String(gate.command || '').trim();
  if (!name) { toast('Choose a gate name first', 'warn'); return; }
  if (!command) { toast('Enter the command to run', 'warn'); return; }
  state.drawer.busy = 'gate';
  state.drawer.actionError = null;
  renderDrawer();
  try {
    const job = await api('/api/jobs/gate', {
      method: 'POST',
      body: { task: task.id, name: name, command: command, timeout: Number(gate.timeout) || 1800 }
    });
    toast('Gate ' + name + ' started', 'ok');
    state.jobsOpen = true;
    renderJobsTray();
    await loadJobs();
    if (job && job.id) openJobLog(job.id);
  } catch (err) {
    state.drawer.actionError = err;
    toast('Gate failed to start: ' + describeError(err), 'error');
  } finally {
    state.drawer.busy = null;
    renderDrawer();
  }
}

function drawerRunTab(task, detail) {
  const body = h('div');
  const run = (detail && detail.run) || task.run || {};
  const attempts = Array.isArray(run.attempts) ? run.attempts : [];

  const kv = h('dl', { class: 'kv' });
  const add = (label, value) => {
    kv.appendChild(h('dt', { text: label }));
    kv.appendChild(h('dd', {}, value instanceof Node ? value : h('span', { text: value })));
  };
  add('Run state', String(run.state || '—'));
  add('Attempt', String(task.attempt || 0) + (task.max_attempts ? ' / ' + task.max_attempts : ''));
  add('Round', String(task.round || 0) + (task.max_rounds ? ' / ' + task.max_rounds : ''));
  add('Tokens', fmtTokens(task.tokens || 0) + (task.budget && task.budget.max ? ' / ' + fmtTokens(task.budget.max) : ''));
  add('Updated', run.updated ? relTime(run.updated) : '—');
  if (task.ready && task.wave !== null && task.wave !== undefined) add('Wave', String(task.wave + 1));
  if (task.blocked_reason) add('Blocked', task.blocked_reason);
  body.appendChild(h('section', { class: 'drawer-section' }, kv));

  if (attempts.length) {
    body.appendChild(h('section', { class: 'drawer-section' },
      h('div', { class: 'drawer-label', text: 'Attempts' }),
      h('div', { class: 'col', style: { gap: '6px' } }, attempts.map((attempt) => {
        const result = String(attempt.result || '');
        const color = result === 'pass' ? 'green' : (result === 'fail' ? 'red' : 'neutral');
        return h('div', { class: 'session-row' },
          h('span', { class: 'chip', text: '#' + (attempt.n || '?') }),
          h('span', { class: 'badge bg-' + color + ' st-' + color }, h('span', { class: 'dot' }), result || 'open'),
          h('span', { class: 'hint', text: (attempt.ended ? relTime(attempt.ended) : 'running') }),
          attempt.note ? h('span', { class: 'hint grow truncate', title: attempt.note, text: attempt.note }) : null);
      }))));
  }

  const events = (detail && Array.isArray(detail.events) ? detail.events : []).slice().reverse().slice(0, 80);
  if (events.length) {
    const list = h('div', { class: 'activity' });
    for (const event of events) {
      list.appendChild(h('div', { class: 'activity-item' },
        h('span', { class: 'activity-time', text: relTime(event.at) }),
        h('span', { class: 'activity-icon bg-neutral st-neutral', text: eventIcon(event.kind) }),
        h('div', { class: 'activity-main' },
          h('div', { class: 'activity-line' },
            h('span', { class: 'chip', text: event.kind || 'event' }),
            h('span', { class: 'activity-summary', text: summarizeRunEvent(event) })))));
    }
    body.appendChild(h('section', { class: 'drawer-section' },
      h('div', { class: 'drawer-label', text: 'Events' }), list));
  } else {
    body.appendChild(h('section', { class: 'drawer-section' },
      h('div', { class: 'drawer-label', text: 'Events' }),
      h('div', { class: 'hint', text: 'No run events recorded yet.' })));
  }
  return body;
}

function eventIcon(kind) {
  switch (kind) {
    case 'gate': return '✓';
    case 'state': return '⇄';
    case 'review': return '✎';
    case 'start': return '▶';
    case 'approval': return '✓';
    case 'note': return '✎';
    default: return '·';
  }
}

function summarizeRunEvent(event) {
  const data = event && event.data ? event.data : {};
  if (event.kind === 'gate') return 'gate ' + (data.gate || '?') + ': ' + (data.result || '?');
  if (event.kind === 'state') {
    return (data.from || '?') + ' → ' + (data.to || '?') + (data.note ? ' (' + data.note + ')' : '');
  }
  if (event.kind === 'review') return 'review ' + (data.verdict || data.result || '?');
  if (event.kind === 'approval') return (data.id || 'approval') + ' ' + (data.action || '') + ' ' + (data.status || '');
  if (event.kind === 'start') return 'attempt started' + (data.actor ? ' by ' + data.actor : '');
  try { return JSON.stringify(data); } catch (err) { return String(data); }
}

function drawerReviewTab(task, detail) {
  const body = h('div');
  const review = (detail && detail.review) || {};
  const verdict = (task.review && task.review.verdict) || review.verdict || null;
  body.appendChild(h('section', { class: 'drawer-section' },
    h('div', { class: 'row-wrap' },
      verdict ? h('span', {
        class: 'badge bg-' + (verdict === 'pass' ? 'green' : 'red') + ' st-' + (verdict === 'pass' ? 'green' : 'red')
      }, h('span', { class: 'dot' }), 'verdict: ' + verdict)
        : h('span', { class: 'pill', text: 'no verdict' }),
      h('span', { class: 'hint', text: review.path || 'reviews/' + task.id + '.md' }))));
  body.appendChild(h('section', { class: 'drawer-section' },
    h('div', { class: 'drawer-label', text: 'Review' }),
    detail ? mdBlock(review.text, 'No review written yet.') : loadingRow('Loading review…')));
  if (task.review && task.review.updated) {
    body.appendChild(h('p', { class: 'hint', text: 'Updated ' + relTime(task.review.updated) }));
  }
  return body;
}

function drawerEvidenceTab(task, detail) {
  const body = h('div');
  const logs = (detail && Array.isArray(detail.gate_logs)) ? detail.gate_logs : [];
  body.appendChild(h('section', { class: 'drawer-section' },
    h('div', { class: 'drawer-label', text: 'Evidence records' }),
    (task.evidence && task.evidence.length)
      ? h('div', { class: 'col', style: { gap: '4px' } },
        task.evidence.map((entry) => h('span', { class: 'chip mono', title: String(entry), text: String(entry) })))
      : h('div', { class: 'hint', text: 'No evidence paths listed on the task.' })));

  if (logs.length) {
    const list = h('div', { class: 'col', style: { gap: '4px' } });
    for (const log of logs) {
      list.appendChild(h('div', { class: 'session-row' },
        h('span', { class: 'mono', text: String(log.gate || 'gate') }),
        h('span', { class: 'hint', text: log.present ? fmtNum(log.size || 0) + ' bytes' : 'missing' }),
        h('button', {
          class: 'btn btn-sm', type: 'button', style: { marginLeft: 'auto' }, text: 'View log',
          on: { click: () => loadEvidenceLog(log.log) }
        })));
    }
    body.appendChild(h('section', { class: 'drawer-section' },
      h('div', { class: 'drawer-label', text: 'Gate logs' }), list));
  }

  const loaded = state.drawer.evidenceLog;
  if (loaded) {
    const section = h('section', { class: 'drawer-section' },
      h('div', { class: 'between' },
        h('div', { class: 'drawer-label', text: basename(loaded.name || '') }),
        h('button', {
          class: 'btn btn-sm btn-ghost', type: 'button', text: 'Close',
          on: { click: () => { state.drawer.evidenceLog = null; renderDrawer(); } }
        })));
    if (loaded.loading) section.appendChild(loadingRow('Loading log…'));
    else if (loaded.error) section.appendChild(errorCallout(loaded.error));
    else section.appendChild(h('pre', { class: 'log-pre', text: loaded.text || '(empty log)' }));
    body.appendChild(section);
  }
  return body;
}

async function loadEvidenceLog(logName) {
  const taskId = state.drawer.id;
  if (!taskId) return;
  const name = basename(logName || '');
  state.drawer.evidenceLog = { name: logName, loading: true };
  renderDrawer();
  try {
    const result = await api('/api/tasks/' + encodeURIComponent(taskId) + '/logs/' + encodeURIComponent(name));
    if (state.drawer.id !== taskId) return;
    state.drawer.evidenceLog = { name: logName, text: result && typeof result.text === 'string' ? result.text : '' };
  } catch (err) {
    if (state.drawer.id !== taskId) return;
    state.drawer.evidenceLog = { name: logName, error: err };
  }
  if (state.drawer.tab !== 'evidence') state.drawer.tab = 'evidence';
  renderDrawer();
}

function drawerHandoffTab(task, detail) {
  const body = h('div');
  if (task.blocked_reason) {
    body.appendChild(h('div', { class: 'callout callout-warn', style: { marginBottom: '12px' } },
      h('div', { class: 'callout-stack' },
        h('div', { text: 'Blocked: ' + task.blocked_reason }),
        task.blocked_action ? h('div', { class: 'cmd-row' },
          h('span', { class: 'cmd', text: task.blocked_action }),
          h('button', { class: 'btn btn-sm', type: 'button', text: 'Copy', on: { click: () => copyText(task.blocked_action) } })) : null)));
  }
  const handoff = Array.isArray(task.handoff) ? task.handoff : (typeof task.handoff === 'string' && task.handoff ? [task.handoff] : []);
  body.appendChild(h('section', { class: 'drawer-section' },
    h('div', { class: 'drawer-label', text: 'Handoff' }),
    handoff.length
      ? h('div', { class: 'md' }, mdFragment(handoff.join('\n\n')))
      : h('div', { class: 'hint', text: 'No handoff notes for this task.' })));

  const deps = task.depends_on || [];
  body.appendChild(h('section', { class: 'drawer-section' },
    h('div', { class: 'drawer-label', text: 'Depends on' }),
    deps.length ? h('div', { class: 'row-wrap' }, deps.map((dep) => taskChip(dep))) : h('div', { class: 'hint', text: 'No dependencies.' })));

  const blocks = ((state.snapshot && state.snapshot.tasks) || [])
    .filter((other) => (other.depends_on || []).indexOf(task.id) !== -1);
  body.appendChild(h('section', { class: 'drawer-section' },
    h('div', { class: 'drawer-label', text: 'Blocks' }),
    blocks.length ? h('div', { class: 'row-wrap' }, blocks.map((other) => taskChip(other.id, other.title)))
      : h('div', { class: 'hint', text: 'No other task depends on this one.' })));

  if (task.scope_write && task.scope_write.length) {
    body.appendChild(h('section', { class: 'drawer-section' },
      h('div', { class: 'drawer-label', text: 'Write scope' }),
      h('div', { class: 'row-wrap' }, task.scope_write.map((entry) => h('span', { class: 'chip mono', text: String(entry) })))));
  }
  return body;
}

/* ---------- drawer: sessions ---------- */

function drawerSessionTab(task, detail) {
  const body = h('div');
  const form = drawerSessionForm();
  const sessions = (state.sessions || []).filter((session) => session.task === task.id);

  const launch = h('div', { class: 'card-panel panel-pad', style: { marginBottom: '12px' } },
    h('div', { class: 'drawer-label', text: 'Launch a headless session' }),
    h('div', { class: 'col', style: { gap: '8px' } },
      h('div', { class: 'row-wrap' },
        h('select', {
          class: 'select', 'aria-label': 'Session role', style: { width: 'auto' },
          on: { change: (event) => { form.role = event.target.value; } }
        }, SESSION_ROLES.map((role) => {
          const option = h('option', { value: role, text: role });
          if (form.role === role) option.selected = true;
          return option;
        })),
        h('label', { class: 'checkbox' },
          h('input', {
            type: 'checkbox', checked: form.worktree,
            on: { change: (event) => { form.worktree = event.target.checked; } }
          }),
          'worktree')),
      h('textarea', {
        class: 'textarea', rows: '2', placeholder: 'Optional operator note for the session',
        value: form.note, 'data-fkey': 'drawer-session-note',
        on: { input: (event) => { form.note = event.target.value; } }
      }),
      h('div', { class: 'row' },
        h('button', {
          class: 'btn btn-primary', type: 'button', text: 'Start session',
          disabled: !canWrite() || state.drawer.busy === 'session',
          title: !canWrite() ? 'The dashboard is read-only' : 'POST /api/sessions',
          on: { click: () => launchDrawerSession() }
        }),
        h('button', {
          class: 'btn btn-ghost', type: 'button', text: 'All sessions',
          on: { click: () => navigate('sessions') }
        }))));
  body.appendChild(launch);

  if (!state.sessionsLoaded) {
    body.appendChild(loadingRow('Loading sessions…'));
    return body;
  }

  if (!sessions.length) {
    body.appendChild(h('p', { class: 'hint', text: 'No session has run for this task yet.' }));
    return body;
  }

  const list = h('div', { class: 'session-list' });
  for (const session of sessions) {
    const active = SESSION_ACTIVE.has(session.status);
    list.appendChild(h('div', { class: 'session-row' + (state.drawer.watch && state.drawer.watch.sessionId === session.id ? ' is-active' : '') },
      h('span', { class: 'session-id', text: session.id }),
      statusPill(session.status),
      h('span', { class: 'hint', text: session.role || 'worker' }),
      h('span', { class: 'hint', text: fmtTokens(session.tokens || 0) + ' tokens' }),
      h('span', { class: 'hint', text: relTime(session.started) }),
      h('div', { style: { marginLeft: 'auto', display: 'flex', gap: '4px' } },
        h('button', {
          class: 'btn btn-sm', type: 'button', text: 'Watch',
          on: { click: () => startDrawerWatch(session.id) }
        }),
        active ? h('button', {
          class: 'btn btn-sm btn-danger', type: 'button', text: 'Stop',
          on: { click: () => stopSession(session.id) }
        }) : null)));
  }
  body.appendChild(list);

  const watch = state.drawer.watch;
  if (watch) {
    const session = (state.sessions || []).find((item) => item.id === watch.sessionId);
    const status = session ? session.status : watch.status;
    const consoleNode = h('div', { class: 'session-console', style: { marginTop: '12px' } },
      h('div', { class: 'session-console-head' },
        h('span', { class: 'mono', text: watch.sessionId }),
        status ? statusPill(status) : null,
        SESSION_ACTIVE.has(status) ? h('span', { class: 'console-live' }, h('span', { class: 'dot' }), 'live · 700ms') : null,
        h('div', { style: { marginLeft: 'auto', display: 'flex', gap: '4px' } },
          h('button', {
            class: 'btn btn-sm', type: 'button', text: 'Log',
            on: { click: () => openSessionLog(watch.sessionId) }
          }),
          h('button', {
            class: 'btn btn-sm btn-ghost', type: 'button', text: 'Clear',
            on: { click: () => { state.drawer.watch.text = ''; renderDrawer(); } }
          }))),
      h('div', { class: 'session-console-body' },
        h('pre', { class: 'log-pre', id: 'drawer-console', text: watch.text || '' })));
    body.appendChild(consoleNode);
  }
  return body;
}

function drawerSessionForm() {
  if (!state.drawer.sessionForm) state.drawer.sessionForm = { role: 'worker', worktree: false, note: '' };
  return state.drawer.sessionForm;
}

async function launchDrawerSession() {
  const task = currentDrawerTask();
  const form = drawerSessionForm();
  state.drawer.busy = 'session';
  state.drawer.actionError = null;
  renderDrawer();
  try {
    const session = await api('/api/sessions', {
      method: 'POST',
      body: { task: task.id, role: form.role, note: form.note || '', worktree: Boolean(form.worktree) }
    });
    toast('Session ' + session.id + ' started', 'ok');
    await loadSessions({ quiet: true });
    state.drawer.watch = null;
    startDrawerWatch(session.id);
    state.drawer.tab = 'session';
    ensureDrawerSessionPolling();
  } catch (err) {
    state.drawer.actionError = err;
    toast('Session failed to start: ' + describeError(err), 'error');
  } finally {
    state.drawer.busy = null;
    renderDrawer();
  }
}

function startDrawerWatch(sessionId) {
  if (!sessionId) return;
  if (state.drawer.watch && state.drawer.watch.timer) {
    window.clearInterval(state.drawer.watch.timer);
  }
  state.drawer.watch = { sessionId: sessionId, offset: 0, text: '', status: null, timer: null };
  state.drawer.tab = 'session';
  renderDrawer();
  const tick = async () => {
    const watch = state.drawer.watch;
    if (!watch || watch.sessionId !== sessionId) return;
    try {
      const chunk = await api('/api/sessions/' + encodeURIComponent(sessionId) + '/log?offset=' + watch.offset);
      if (state.drawer.watch !== watch) return;
      if (chunk && typeof chunk.text === 'string' && chunk.text) watch.text += chunk.text;
      if (chunk && typeof chunk.next === 'number') watch.offset = chunk.next;
      const session = (state.sessions || []).find((item) => item.id === sessionId);
      if (session) {
        watch.status = session.status;
        watch.missing = 0;
      } else {
        watch.missing = (watch.missing || 0) + 1;
        if (watch.missing >= 3) watch.status = 'unknown';
      }
      const pre = document.getElementById('drawer-console');
      if (pre) { pre.textContent = watch.text; pre.scrollTop = pre.scrollHeight; }
      if (watch.status && !SESSION_ACTIVE.has(watch.status)) {
        if (watch.timer) window.clearInterval(watch.timer);
        watch.timer = null;
        renderDrawer();
      }
    } catch (err) {
      watch.text += '\n[dashboard] ' + describeError(err) + '\n';
      if (watch.timer) window.clearInterval(watch.timer);
      watch.timer = null;
      renderDrawer();
    }
  };
  state.drawer.watch.timer = window.setInterval(tick, 700);
  tick();
}

async function stopSession(sessionId) {
  try {
    await api('/api/sessions/' + encodeURIComponent(sessionId) + '/stop', { method: 'POST', body: {} });
    toast('Stop requested', 'ok');
    await loadSessions({ quiet: true });
  } catch (err) {
    toast('Stop failed: ' + describeError(err), 'error');
  }
}
/* =========================================================================
   2.1 — Your Work cockpit and Inbox
   ========================================================================= */

function ywQueueRow(options) {
  const opts = options || {};
  const row = h('button', {
    class: 'queue-row', type: 'button',
    title: opts.title || '',
    on: { click: () => openTask(opts.taskId) }
  });
  const main = h('div', { class: 'queue-main' },
    h('div', { class: 'queue-title', text: opts.title || opts.taskId }),
    opts.sub ? h('div', { class: 'queue-sub', text: opts.sub }) : null);
  row.appendChild(main);
  if (opts.right) append(row, [opts.right]);
  return row;
}

function ywTaskRow(taskId, fallbackTitle, extraSub, options) {
  const task = taskById(taskId);
  const opts = options || {};
  const subParts = [];
  if (task) {
    subParts.push(task.stage_title || String(task.stage || ''));
    if (task.owner) subParts.push('owner ' + task.owner);
  }
  if (extraSub) subParts.push(extraSub);
  const status = task ? task.status : opts.status;
  return ywQueueRow({
    taskId: taskId,
    title: (task && task.title) || fallbackTitle || taskId,
    sub: subParts.filter(Boolean).join(' · ') || undefined,
    right: status ? statusPill(status) : null
  });
}

function ywCard(title, count, body, extraHead) {
  return h('section', { class: 'card-panel', id: extraHead && extraHead.id ? extraHead.id : null },
    h('div', { class: 'panel-head' },
      h('div', { class: 'row' },
        h('span', { class: 'panel-title', text: title }),
        count !== null && count !== undefined ? h('span', { class: 'pill', text: String(count) }) : null),
      extraHead && extraHead.actions ? h('div', { class: 'row' }, extraHead.actions) : null),
    h('div', { class: 'panel-body' }, body));
}

function renderYourWork() {
  const view = h('div', { class: 'yourwork' });
  dom.view.appendChild(view);
  const data = state.yourWork;
  const me = settingsMe();

  view.appendChild(h('div', { class: 'view-head' },
    h('div', {},
      h('h1', { class: 'view-title', text: 'Your Work' }),
      h('p', { class: 'view-sub', text: [
        'me: ' + me,
        data && data.project ? data.project : '',
        data && data.generated_at ? 'updated ' + relTime(data.generated_at) : ''
      ].filter(Boolean).join(' · ') })),
    h('div', { class: 'view-actions' },
      h('button', {
        class: 'btn btn-sm', type: 'button', text: 'Refresh',
        on: {
          click: async () => {
            await Promise.all([loadYourWork(), loadInbox()]);
            renderHeader();
            renderView();
          }
        }
      }))));

  if (!state.yourWorkLoaded && !data) {
    view.appendChild(loadingRow('Building your cockpit…'));
    return;
  }
  if (!data) {
    view.appendChild(errorCallout(state.yourWorkError || new ApiError('Your Work is unavailable.', 0, null)));
    return;
  }

  const counts = data.counts || {};
  const tiles = [
    { label: 'Mine', value: counts.mine || 0, target: 'yw-mine', cls: 'tile-blue', sub: 'tasks you own' },
    { label: 'Reviews', value: counts.reviews || 0, target: 'yw-reviews', cls: 'tile-violet', sub: 'awaiting a verdict' },
    { label: 'Approvals', value: counts.approvals || 0, target: null, view: 'approvals', cls: 'tile-accent', sub: 'owner decisions' },
    { label: 'Blocked', value: counts.blocked || 0, target: 'yw-blocked', cls: 'tile-orange', sub: 'need unblocking' },
    { label: 'Budget', value: counts.budget || 0, target: 'yw-budget', cls: 'tile-red', sub: 'near or over tokens' },
    { label: 'Ready', value: counts.ready || 0, target: 'yw-ready', cls: 'tile-green', sub: 'in the next wave' },
    { label: 'Sessions running', value: counts.sessions_running || 0, target: null, view: 'sessions', cls: 'tile-accent', sub: 'headless agents' }
  ];
  const tileGrid = h('div', { class: 'tiles' });
  for (const tile of tiles) {
    tileGrid.appendChild(h('button', {
      class: 'tile ' + tile.cls, type: 'button',
      title: tile.label + ': ' + tile.value,
      on: {
        click: () => {
          if (tile.view) navigate(tile.view);
          else {
            const target = document.getElementById(tile.target);
            if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
          }
        }
      }
    }, h('span', { class: 'tile-value', text: String(tile.value) }),
      h('span', { class: 'tile-label', text: tile.label }),
      h('span', { class: 'tile-sub', text: tile.sub })));
  }
  view.appendChild(tileGrid);

  const grid = h('div', { class: 'yourwork-grid' });
  const left = h('div', { class: 'yourwork-col' });
  const right = h('div', { class: 'yourwork-col' });
  grid.appendChild(left);
  grid.appendChild(right);
  view.appendChild(grid);

  /* workload by status (mine) */
  const workload = data.workload || {};
  const workloadBody = h('div', { class: 'workload' });
  const workloadTotal = Object.keys(workload).reduce((sum, key) => sum + Number(workload[key] || 0), 0);
  if (!workloadTotal) {
    workloadBody.appendChild(h('div', { class: 'hint', text: 'No tasks are assigned to ' + me + ' right now.' }));
  } else {
    for (const status of statusOrder()) {
      const amount = Number(workload[status] || 0);
      if (!amount) continue;
      const meta = stMeta(status);
      workloadBody.appendChild(h('div', { class: 'workload-row' },
        h('span', { class: 'workload-label' },
          h('span', { class: 'dot st-' + meta.color }), h('span', { text: meta.label })),
        progressBar(amount, workloadTotal, ''),
        h('span', { class: 'workload-value', text: String(amount) })));
    }
  }
  left.appendChild(ywCard('Workload · mine', workloadTotal, workloadBody));

  /* mine */
  const mineRows = (data.mine || []).map((row) => ywTaskRow(row.id, row.title, null, { status: row.status }));
  left.appendChild(ywCard('Mine', (data.mine || []).length,
    mineRows.length ? h('div', { class: 'queue' }, mineRows) : h('div', { class: 'hint', text: 'No tasks are assigned to you.' }),
    { id: 'yw-mine' }));

  /* review queue */
  const reviewRows = (data.reviews || []).map((row) => {
    const verdict = row.review && row.review.verdict;
    return ywTaskRow(row.id, row.title, verdict ? 'verdict: ' + verdict : 'no verdict yet', { status: row.status });
  });
  left.appendChild(ywCard('Review queue', (data.reviews || []).length,
    reviewRows.length ? h('div', { class: 'queue' }, reviewRows) : h('div', { class: 'hint', text: 'Nothing waits for a review.' }),
    { id: 'yw-reviews' }));

  /* ready */
  const readyRows = (data.ready || []).map((row) => ywTaskRow(row.id, row.title, 'wave 1', null));
  left.appendChild(ywCard('Ready now', (data.ready || []).length,
    readyRows.length ? h('div', { class: 'queue' }, readyRows) : h('div', { class: 'hint', text: 'No task is ready for dispatch.' }),
    { id: 'yw-ready' }));

  /* inbox */
  right.appendChild(renderInboxPanel());

  /* approvals */
  const approvalRows = (data.approvals || []).map((record) => h('button', {
    class: 'queue-row', type: 'button', title: record.note || '',
    on: { click: () => navigate('approvals') }
  },
  h('div', { class: 'queue-main' },
    h('div', { class: 'queue-title', text: (record.id || 'AP') + ' · ' + (record.action || 'approval') }),
    h('div', { class: 'queue-sub', text: (record.task ? record.task + ' · ' : '') + (record.note || 'requested by ' + (record.requested_by || '—')) })),
  h('span', { class: 'pill', text: relTime(record.requested_at) })));
  right.appendChild(ywCard('Approvals waiting', (data.approvals || []).length,
    approvalRows.length ? h('div', { class: 'queue' }, approvalRows) : h('div', { class: 'hint', text: 'No pending approvals.' })));

  /* blocked */
  const blockedRows = (data.blocked || []).map((row) => ywTaskRow(row.id, row.title, row.reason || 'blocked', { status: 'blocked' }));
  right.appendChild(ywCard('Blocked', (data.blocked || []).length,
    blockedRows.length ? h('div', { class: 'queue' }, blockedRows) : h('div', { class: 'hint', text: 'No task is blocked.' }),
    { id: 'yw-blocked' }));

  /* budget */
  const budgetRows = (data.budget || []).map((row) => {
    const budget = row.budget || {};
    const sub = (budget.over ? 'over budget' : 'near budget') + (budget.max ? ' · ' + fmtTokens(budget.used || 0) + '/' + fmtTokens(budget.max) : '');
    return ywTaskRow(row.id, row.title, sub, null);
  });
  right.appendChild(ywCard('Budget watch', (data.budget || []).length,
    budgetRows.length ? h('div', { class: 'queue' }, budgetRows) : h('div', { class: 'hint', text: 'No task is near its token budget.' }),
    { id: 'yw-budget' }));

  /* claimed */
  const claimedRows = (data.claimed || []).map((row) => {
    const claim = row.claim || {};
    return ywTaskRow(row.id, row.title, 'claimed by ' + (claim.harness || 'session') + (claim.session ? ' · ' + claim.session : ''), null);
  });
  right.appendChild(ywCard('Claimed now', (data.claimed || []).length,
    claimedRows.length ? h('div', { class: 'queue' }, claimedRows) : h('div', { class: 'hint', text: 'No live claims.' })));

  /* sessions */
  const sessions = data.sessions || [];
  const sessionRows = sessions.slice(0, 8).map((session) => h('button', {
    class: 'session-row', type: 'button', title: 'Open Sessions',
    on: { click: () => navigate('sessions') }
  },
  h('span', { class: 'session-id', text: session.id || 'session' }),
  session.status ? statusPill(session.status) : h('span', { class: 'faint', text: '—' }),
  session.task ? h('span', { class: 'chip mono', text: session.task }) : null,
  h('span', { class: 'hint', text: (session.role || 'worker') + ' · ' + fmtTokens(session.tokens || 0) + ' tokens' }),
  h('span', { class: 'hint', style: { marginLeft: 'auto' }, text: relTime(session.started) })));
  right.appendChild(ywCard('Sessions', sessions.length,
    sessionRows.length ? h('div', { class: 'sessions-strip' }, sessionRows) : h('div', { class: 'hint', text: 'No headless sessions recorded yet.' })));
}

function renderInboxPanel() {
  const counts = state.inboxCounts || { total: 0, unread: 0, high: 0 };
  const items = state.inboxItems || [];
  const unread = items.filter((item) => !item.read);

  const actions = h('div', { class: 'row' },
    h('button', {
      class: 'btn btn-sm', type: 'button', text: 'Mark all read',
      disabled: !unread.length || !canWrite(),
      title: canWrite() ? 'Mark every inbox item read' : 'The dashboard is read-only',
      on: { click: () => markAllInboxRead() }
    }));

  const panel = h('section', { class: 'card-panel', id: 'yw-inbox' },
    h('div', { class: 'panel-head' },
      h('div', { class: 'inbox-head' },
        h('span', { class: 'panel-title', text: 'Inbox' }),
        h('span', { class: 'pill' + (counts.unread ? ' pill-accent' : ''), text: String(counts.unread || 0) + ' unread' }),
        counts.high ? h('span', { class: 'pill pill-danger', text: String(counts.high) + ' high' }) : null),
      actions),
    h('div', { class: 'panel-body' }));

  const body = panel.querySelector('.panel-body');
  if (!state.inboxLoaded && !items.length) {
    body.appendChild(loadingRow('Loading the inbox…'));
    return panel;
  }
  if (!items.length) {
    body.appendChild(h('div', { class: 'hint', text: 'Inbox zero — nothing needs your attention.' }));
    return panel;
  }

  const list = h('div', { class: 'inbox-list' });
  for (const item of items) {
    const severity = ['high', 'medium', 'low', 'info'].indexOf(item.severity) !== -1 ? item.severity : 'info';
    const row = h('div', {
      class: 'inbox-item ' + (item.read ? 'is-read' : 'is-unread'),
      role: 'button',
      tabindex: '0',
      title: item.summary || item.title || '',
      on: {
        click: () => openInboxItem(item),
        keydown: (event) => {
          if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); openInboxItem(item); }
        }
      }
    },
    h('span', { class: 'inbox-sev sev-' + severity, title: 'Severity: ' + severity }),
    h('div', { class: 'inbox-main' },
      h('div', { class: 'inbox-title', text: item.title || item.id }),
      item.summary ? h('div', { class: 'inbox-sub', text: item.summary }) : null,
      h('div', { class: 'inbox-meta' },
        h('span', { class: 'chip', text: item.kind || 'item' }),
        item.task ? taskChip(item.task) : null,
        h('span', { text: relTime(item.at) }))),
    h('div', { class: 'inbox-side' },
      item.read ? h('span', { class: 'faint text-sm', text: 'read' }) : h('span', { class: 'badge bg-blue st-blue', text: 'new' }),
      item.action ? h('span', { class: 'hint text-sm', text: item.action }) : null,
      !item.read ? h('button', {
        class: 'btn btn-sm btn-ghost', type: 'button', text: 'Mark read',
        disabled: !canWrite(),
        title: canWrite() ? 'Mark this item read' : 'The dashboard is read-only',
        on: {
          click: (event) => {
            event.stopPropagation();
            markInboxRead([item.id], true);
          }
        }
      }) : null));
    list.appendChild(row);
  }
  body.appendChild(list);
  return panel;
}

/* =========================================================================
   2.1 — Settings: project, features, labels, local sessions and gates
   ========================================================================= */

const FEATURE_ORDER = ['inbox', 'worklog', 'views', 'labels', 'timeline', 'cycles',
  'modules', 'coverage', 'analytics', 'pages', 'intake', 'assistant', 'automations', 'github'];

function settingsUI() {
  if (!state.settingsUI) {
    state.settingsUI = {
      editLabel: null,
      editColor: 'neutral',
      addColor: 'neutral',
      addGroup: 'custom',
      labelError: null,
      error: null,
      busy: null,
      adding: false
    };
  }
  return state.settingsUI;
}

function renderSettings() {
  const view = h('div', { class: 'settings' });
  dom.view.appendChild(view);
  const snapshot = state.snapshot;
  const project = (snapshot && snapshot.project) || {};
  const config = state.config || {};
  const health = state.health || {};
  const ui = settingsUI();

  view.appendChild(h('div', { class: 'view-head' },
    h('div', {},
      h('h1', { class: 'view-title', text: 'Settings' }),
      h('p', { class: 'view-sub', text: [
        project.name || 'project',
        'profile ' + (project.profile || '—'),
        config.read_only ? 'read-only' : 'writable'
      ].join(' · ') })),
    h('div', { class: 'view-actions' },
      h('button', {
        class: 'btn btn-sm', type: 'button', text: 'Refresh',
        on: {
          click: async () => {
            await Promise.all([loadSettings(), loadConfig(), loadSnapshot(), loadViews()]);
            renderHeader();
            renderTabs();
            renderView();
          }
        }
      }))));

  if (!state.settingsLoaded && !state.settings) {
    view.appendChild(loadingRow('Loading settings…'));
    return;
  }
  if (state.settingsError) view.appendChild(errorCallout(state.settingsError));
  if (ui.error) view.appendChild(errorCallout(ui.error));

  const settingsErrors = (state.settings && state.settings.errors) || [];
  if (settingsErrors.length) {
    const box = h('div', { class: 'callout callout-warn' },
      h('div', { class: 'callout-stack' },
        h('div', { text: 'dashboard.json has validation problems:' }),
        h('ul', {}, settingsErrors.map((message) => h('li', { text: message })))));
    view.appendChild(box);
  }

  view.appendChild(renderSettingsGeneral(project, config, health));
  view.appendChild(renderSettingsFeatures(ui));
  if (feature('labels')) view.appendChild(renderSettingsLabels(ui));
  view.appendChild(renderSettingsSessions(config, ui));
  view.appendChild(renderSettingsGates(config, ui));
  view.appendChild(renderSettingsTemplates(ui, config));
  view.appendChild(renderSettingsAbout(project, config, health, settingsErrors));
}

/* ---------- General ---------- */

function renderSettingsGeneral(project, config, health) {
  const meInput = h('input', {
    class: 'input', type: 'text', value: settingsMe(), 'data-fkey': 'settings-me',
    'aria-label': 'My handle (me)'
  });
  const card = h('section', { class: 'card-panel settings-section' },
    h('div', { class: 'panel-head' }, h('span', { class: 'panel-title', text: 'General' })),
    h('div', { class: 'panel-body' },
      h('dl', { class: 'kv settings-grid' },
        h('dt', { text: 'Project' }), h('dd', { text: project.name || '—' }),
        h('dt', { text: 'Profile' }), h('dd', { text: project.profile || '—' }),
        h('dt', { text: 'Stage' }), h('dd', { text: project.stage === null || project.stage === undefined ? '—' : String(project.stage) }),
        h('dt', { text: 'Base branch' }), h('dd', { text: project.base_branch || '—' }),
        h('dt', { text: 'Board schema' }), h('dd', { text: project.schema_version || '—' }),
        h('dt', { text: 'Generator' }), h('dd', { text: project.generator_version || '—' }),
        h('dt', { text: 'Root' }), h('dd', { class: 'mono', text: (health && health.root) || config.project_root || '—' })),
      h('div', { class: 'settings-row' },
        h('div', { class: 'settings-row-main' },
          h('div', { class: 'settings-row-title', text: '"Me" handle' }),
          h('div', { class: 'settings-row-sub', text: 'Tasks with this owner count as "Mine" in Your Work and in the mine built-in view.' })),
        h('div', { class: 'settings-actions' },
          meInput,
          h('button', {
            class: 'btn btn-sm btn-primary', type: 'button', text: 'Save',
            disabled: !canWrite() || uiBusy('general'),
            title: canWrite() ? 'PUT /api/settings' : 'The dashboard is read-only',
            on: {
              click: async () => {
                const value = meInput.value.trim();
                if (!value) { toast('The handle must not be empty', 'warn'); return; }
                await saveSettings({ defaults: { me: value } }, 'general', 'Handle saved');
              }
            }
          })))));
  return card;
}

function uiBusy(key) {
  return Boolean(state.settingsUI && state.settingsUI.busy === key);
}

async function saveSettings(payload, busyKey, message) {
  const ui = settingsUI();
  ui.busy = busyKey;
  ui.error = null;
  renderView();
  try {
    await api('/api/settings', { method: 'PUT', body: payload });
    await Promise.all([loadSettings(), loadSnapshot(), loadViews()]);
    renderHeader();
    renderTabs();
    toast(message || 'Settings saved', 'ok');
    ui.busy = null;
    renderView();
    return true;
  } catch (err) {
    ui.busy = null;
    ui.error = err;
    toast('Settings: ' + describeError(err), 'error');
    renderView();
    return false;
  }
}

/* ---------- Features ---------- */

function renderSettingsFeatures(ui) {
  const defaults = featureDefaults();
  const current = (state.settings && state.settings.features) || defaults;
  const keys = FEATURE_ORDER.filter((key) => Object.prototype.hasOwnProperty.call(defaults, key));
  for (const key of Object.keys(defaults)) if (keys.indexOf(key) === -1) keys.push(key);

  const grid = h('div', { class: 'feature-grid' });
  for (const key of keys) {
    const planned = defaults[key] === false;
    const enabled = Boolean(current[key]);
    grid.appendChild(h('label', { class: 'settings-row' },
      h('div', { class: 'settings-row-main' },
        h('div', { class: 'settings-row-title' },
          h('span', { text: FEATURE_LABELS[key] || key }),
          planned ? h('span', { class: 'pill pill-planned', text: 'planned' }) : null,
          planned && enabled ? h('span', { class: 'pill pill-accent', text: 'on' }) : null),
        h('div', { class: 'settings-row-sub', text: FEATURE_NOTES[key] || '' })),
      h('span', { class: 'switch' },
        h('input', {
          type: 'checkbox', checked: enabled,
          'data-feature': key,
          'aria-label': 'Enable ' + (FEATURE_LABELS[key] || key),
          disabled: !canWrite() || uiBusy('features'),
          on: {
            change: async (event) => {
              const boxes = document.querySelectorAll('[data-feature]');
              const features = {};
              for (const box of boxes) features[box.getAttribute('data-feature')] = box.checked;
              event.target.disabled = true;
              await saveSettings({ features: features }, 'features', 'Feature flags saved');
            }
          }
        }))));
  }

  return h('section', { class: 'card-panel settings-section' },
    h('div', { class: 'panel-head' },
      h('span', { class: 'panel-title', text: 'Features' }),
      h('span', { class: 'hint', text: 'Only the current views are on by default; planned views stay off until you enable them.' })),
    h('div', { class: 'panel-body' }, grid));
}

/* ---------- Labels ---------- */

function palettePicker(selected, onPick) {
  const row = h('div', { class: 'palette-picker', role: 'group', 'aria-label': 'Label colour' });
  for (const color of settingsPalette()) {
    row.appendChild(h('button', {
      class: 'swatch ' + paletteClass(color), type: 'button',
      'aria-pressed': selected === color ? 'true' : 'false',
      'aria-label': color, title: color,
      on: { click: () => onPick(color) }
    }));
  }
  return row;
}

function groupPicker(selected, onChange) {
  const select = h('select', { class: 'select', 'aria-label': 'Label group', on: { change: (event) => onChange(event.target.value) } });
  for (const group of settingsGroups()) {
    const option = h('option', { value: group, text: group });
    if ((selected || 'custom') === group) option.selected = true;
    select.appendChild(option);
  }
  select.value = selected || 'custom';
  return select;
}

function renderSettingsLabels(ui) {
  const labels = settingsLabels();
  const groups = settingsGroups();
  const body = h('div', { class: 'panel-body' });

  const grouped = new Map();
  for (const label of labels) {
    const group = groups.indexOf(label.group) !== -1 ? label.group : 'custom';
    if (!grouped.has(group)) grouped.set(group, []);
    grouped.get(group).push(label);
  }

  const admin = h('div', { class: 'label-admin' });
  for (const group of groups) {
    if (!grouped.has(group)) continue;
    admin.appendChild(h('div', { class: 'label-group-head', text: group }));
    for (const label of grouped.get(group)) {
      const editing = ui.editLabel === label.id;
      if (editing) {
        const titleInput = h('input', {
          class: 'input', type: 'text',
          value: ui.editTitle !== undefined ? ui.editTitle : label.title,
          'data-fkey': 'label-edit-title', 'aria-label': 'Label title',
          on: { input: (event) => { ui.editTitle = event.target.value; } }
        });
        admin.appendChild(h('div', { class: 'label-form' },
          h('label', { class: 'field' }, h('span', { class: 'field-label', text: 'Title' }), titleInput),
          palettePicker(ui.editColor || label.color, (color) => { ui.editColor = color; renderView(); }),
          groupPicker(label.group, (group) => { ui.editGroup = group; }),
          h('button', {
            class: 'btn btn-sm btn-primary', type: 'button', text: 'Save',
            on: {
              click: () => saveLabel(label.id, {
                title: titleInput.value.trim(),
                color: ui.editColor || label.color,
                group: ui.editGroup || label.group
              })
            }
          }),
          h('button', {
            class: 'btn btn-sm btn-ghost', type: 'button', text: 'Cancel',
            on: { click: () => { ui.editLabel = null; ui.editTitle = undefined; ui.labelError = null; renderView(); } }
          })));
        if (ui.labelError) admin.appendChild(errorCallout(ui.labelError));
        continue;
      }
      admin.appendChild(h('div', { class: 'label-admin-row' },
        h('div', { class: 'label-admin-main' },
          labelChip(label),
          h('span', { class: 'label-admin-id', text: label.id }),
          h('span', { class: 'chip', text: label.group })),
        h('div', { class: 'label-admin-actions' },
          h('button', {
            class: 'btn btn-sm', type: 'button', text: 'Edit', disabled: !canWrite(),
            on: {
              click: () => {
                ui.editLabel = label.id;
                ui.editColor = label.color;
                ui.editGroup = label.group;
                ui.editTitle = label.title;
                ui.labelError = null;
                renderView();
              }
            }
          }),
          h('button', {
            class: 'btn btn-sm btn-danger', type: 'button', text: 'Delete', disabled: !canWrite(),
            on: { click: () => deleteLabel(label.id) }
          }))));
    }
  }
  if (!labels.length) admin.appendChild(h('div', { class: 'hint', text: 'No labels defined yet.' }));
  body.appendChild(admin);

  /* add form */
  if (ui.adding) {
    const idInput = h('input', {
      class: 'input', type: 'text', placeholder: 'bug',
      value: ui.addId || '', 'data-fkey': 'label-add-id', 'aria-label': 'Label id',
      on: { input: (event) => { ui.addId = event.target.value; } }
    });
    const titleInput = h('input', {
      class: 'input', type: 'text', placeholder: 'Bug',
      value: ui.addTitle || '', 'data-fkey': 'label-add-title', 'aria-label': 'Label title',
      on: { input: (event) => { ui.addTitle = event.target.value; } }
    });
    body.appendChild(h('div', { class: 'label-form' },
      h('label', { class: 'field' }, h('span', { class: 'field-label', text: 'Id' }), idInput),
      h('label', { class: 'field' }, h('span', { class: 'field-label', text: 'Title' }), titleInput),
      palettePicker(ui.addColor, (color) => { ui.addColor = color; renderView(); }),
      groupPicker(ui.addGroup, (group) => { ui.addGroup = group; }),
      h('button', {
        class: 'btn btn-primary btn-sm', type: 'button', text: 'Add label',
        on: { click: () => addLabelFromForm(idInput.value.trim(), titleInput.value.trim()) }
      }),
      h('button', {
        class: 'btn btn-ghost btn-sm', type: 'button', text: 'Cancel',
        on: { click: () => { ui.adding = false; ui.labelError = null; renderView(); } }
      })));
    if (ui.labelError) body.appendChild(errorCallout(ui.labelError));
  } else {
    body.appendChild(h('div', { class: 'settings-actions' },
      h('button', {
        class: 'btn btn-sm', type: 'button', text: '+ Add label', disabled: !canWrite(),
        on: { click: () => { ui.adding = true; ui.addColor = 'neutral'; ui.addGroup = 'custom'; ui.addId = ''; ui.addTitle = ''; ui.labelError = null; renderView(); } }
      }),
      h('span', { class: 'hint', text: 'Labels are committed in dashboard.json and referenced by id on the board.' })));
  }

  return h('section', { class: 'card-panel settings-section' },
    h('div', { class: 'panel-head' },
      h('span', { class: 'panel-title', text: 'Labels' }),
      h('span', { class: 'pill', text: String(labels.length) })),
    body);
}

async function addLabelFromForm(labelId, title) {
  const ui = settingsUI();
  if (!labelId || !/^[a-z][a-z0-9-]{0,40}$/.test(labelId)) {
    ui.labelError = new ApiError('Label id must start with a lowercase letter and use only a-z, 0-9 and dashes.', 400, null);
    renderView();
    return;
  }
  if (!title) {
    ui.labelError = new ApiError('A label title is required.', 400, null);
    renderView();
    return;
  }
  ui.busy = 'label';
  try {
    await api('/api/settings/labels', {
      method: 'POST',
      body: { id: labelId, title: title, color: ui.addColor || 'neutral', group: ui.addGroup || 'custom' }
    });
    ui.adding = false;
    ui.busy = null;
    ui.addId = '';
    ui.addTitle = '';
    ui.labelError = null;
    await Promise.all([loadSettings(), loadSnapshot()]);
    renderHeader();
    toast('Label added', 'ok');
    renderView();
  } catch (err) {
    ui.busy = null;
    ui.labelError = err;
    renderView();
  }
}

async function saveLabel(labelId, payload) {
  const ui = settingsUI();
  if (!payload.title) {
    ui.labelError = new ApiError('A label title is required.', 400, null);
    renderView();
    return;
  }
  ui.busy = 'label';
  try {
    await api('/api/settings/labels/' + encodeURIComponent(labelId), { method: 'PUT', body: payload });
    ui.busy = null;
    ui.editLabel = null;
    ui.editTitle = undefined;
    ui.labelError = null;
    await Promise.all([loadSettings(), loadSnapshot()]);
    renderHeader();
    toast('Label saved', 'ok');
    renderView();
  } catch (err) {
    ui.busy = null;
    ui.labelError = err;
    renderView();
  }
}

async function deleteLabel(labelId) {
  const ui = settingsUI();
  const run = async (force) => {
    try {
      await api('/api/settings/labels/' + encodeURIComponent(labelId), {
        method: 'DELETE',
        body: force ? { force: true } : {}
      });
      await Promise.all([loadSettings(), loadSnapshot(), loadViews()]);
      renderHeader();
      toast('Label deleted', 'ok');
      ui.labelError = null;
      renderView();
      return true;
    } catch (err) {
      if (!force && err.status === 400 && /used by/i.test(String(err.message))) {
        const remove = await confirmDialog({
          title: 'Label is in use',
          message: describeError(err) + ' Remove it from those tasks and delete it?',
          confirmLabel: 'Remove and delete'
        });
        if (remove) return run(true);
        return false;
      }
      ui.labelError = err;
      toast('Delete failed: ' + describeError(err), 'error');
      renderView();
      return false;
    }
  };
  const confirmed = await confirmDialog({
    title: 'Delete label "' + labelId + '"?',
    message: 'The label is removed from dashboard.json. If tasks still use it, you are asked before it is stripped from them.',
    confirmLabel: 'Delete label'
  });
  if (confirmed) await run(false);
}

/* ---------- Sessions (machine-local /api/config) ---------- */

function renderSettingsSessions(config, ui) {
  const session = Object.assign({
    provider: 'claude', command: ['claude'], permission_mode: 'acceptEdits',
    allowed_tools: [], model: null, timeout_s: 7200, max_concurrent: 2
  }, (config && config.session) || {});

  const providerInput = h('input', { class: 'input', type: 'text', value: session.provider || '', 'aria-label': 'Provider' });
  const commandArea = h('textarea', {
    class: 'textarea', rows: '2',
    'aria-label': 'Provider command',
    placeholder: 'claude\nor ["claude"]'
  });
  commandArea.value = Array.isArray(session.command) ? session.command.join('\n') : String(session.command || '');
  const modeInput = h('input', { class: 'input', type: 'text', value: session.permission_mode || '', 'aria-label': 'Permission mode' });
  const toolsInput = h('input', {
    class: 'input', type: 'text', 'aria-label': 'Allowed tools',
    value: Array.isArray(session.allowed_tools) ? session.allowed_tools.join(', ') : ''
  });
  const modelInput = h('input', { class: 'input', type: 'text', value: session.model || '', placeholder: 'provider default', 'aria-label': 'Model' });
  const timeoutInput = h('input', { class: 'input', type: 'number', min: '1', value: String(session.timeout_s || 7200), 'aria-label': 'Timeout seconds' });
  const concurrentInput = h('input', { class: 'input', type: 'number', min: '1', value: String(session.max_concurrent || 2), 'aria-label': 'Max concurrent sessions' });

  const card = h('section', { class: 'card-panel settings-section' },
    h('div', { class: 'panel-head' },
      h('span', { class: 'panel-title', text: 'Sessions (this machine)' }),
      h('span', { class: 'hint', text: 'Machine-local: stored in the dashboard runtime folder, not committed.' })),
    h('div', { class: 'panel-body' },
      h('div', { class: 'form-grid' },
        h('label', { class: 'field' }, h('span', { class: 'field-label', text: 'Provider' }), providerInput),
        h('label', { class: 'field' }, h('span', { class: 'field-label', text: 'Permission mode' }), modeInput),
        h('label', { class: 'field span-2' },
          h('span', { class: 'field-label', text: 'Command' }), commandArea,
          h('span', { class: 'field-help', text: 'One argument per line, or a JSON array such as ["claude"].' })),
        h('label', { class: 'field span-2' },
          h('span', { class: 'field-label', text: 'Allowed tools' }), toolsInput,
          h('span', { class: 'field-help', text: 'Comma-separated, e.g. Bash, Read, Write.' })),
        h('label', { class: 'field' }, h('span', { class: 'field-label', text: 'Model' }), modelInput),
        h('label', { class: 'field' }, h('span', { class: 'field-label', text: 'Timeout (seconds)' }), timeoutInput),
        h('label', { class: 'field' }, h('span', { class: 'field-label', text: 'Max concurrent' }), concurrentInput)),
      h('div', { class: 'settings-actions' },
        h('button', {
          class: 'btn btn-sm btn-primary', type: 'button', text: 'Save session settings',
          disabled: !canWrite() || uiBusy('sessions'),
          title: canWrite() ? 'PUT /api/config {session}' : 'The dashboard is read-only',
          on: {
            click: () => saveLocalSession({
              providerInput, commandArea, modeInput, toolsInput, modelInput, timeoutInput, concurrentInput
            })
          }
        }),
        h('span', { class: 'hint', text: 'Changing the provider or command affects the next session only.' }))));
  return card;
}

function parseCommand(text) {
  const trimmed = String(text || '').trim();
  if (!trimmed) return ['claude'];
  if (trimmed.charAt(0) === '[') {
    try {
      const parsed = JSON.parse(trimmed);
      if (Array.isArray(parsed) && parsed.length && parsed.every((part) => typeof part === 'string')) return parsed;
    } catch (err) { /* fall through to line split */ }
  }
  return trimmed.split('\n').map((line) => line.trim()).filter(Boolean);
}

async function saveLocalSession(form) {
  const command = parseCommand(form.commandArea.value);
  if (!command.length) {
    toast('The provider command must not be empty', 'warn');
    return;
  }
  const session = {
    provider: form.providerInput.value.trim() || 'claude',
    command: command,
    permission_mode: form.modeInput.value.trim() || null,
    allowed_tools: form.toolsInput.value.split(/[,\n]/).map((part) => part.trim()).filter(Boolean),
    model: form.modelInput.value.trim() || null,
    timeout_s: Number(form.timeoutInput.value) || 7200,
    max_concurrent: Number(form.concurrentInput.value) || 2
  };
  try {
    await api('/api/config', { method: 'PUT', body: { session: session } });
    await loadConfig();
    toast('Session settings saved', 'ok');
    renderView();
  } catch (err) {
    toast('Session settings: ' + describeError(err), 'error');
  }
}

/* ---------- Gate commands (machine-local) ---------- */

function renderSettingsGates(config, ui) {
  const commands = Object.assign({}, (config && config.gate_commands) || {});
  const rowsHost = h('div', { class: 'col', style: { gap: '6px' } });
  const addRow = (name, command) => {
    const row = h('div', { class: 'row', 'data-gate-row': '1' },
      h('input', { class: 'input', type: 'text', value: name || '', placeholder: 'gate name', 'aria-label': 'Gate name', style: { maxWidth: '180px' } }),
      h('input', { class: 'input', type: 'text', value: command || '', placeholder: 'pnpm test', 'aria-label': 'Gate command' }),
      h('button', {
        class: 'btn btn-sm btn-ghost', type: 'button', text: '×', 'aria-label': 'Remove gate command',
        on: { click: () => row.remove() }
      }));
    rowsHost.appendChild(row);
  };
  for (const name of Object.keys(commands).sort()) addRow(name, commands[name]);

  return h('section', { class: 'card-panel settings-section' },
    h('div', { class: 'panel-head' },
      h('span', { class: 'panel-title', text: 'Gate commands (this machine)' }),
      h('span', { class: 'hint', text: 'Prefills the gate runner; suggested values come from docs/quality.md.' })),
    h('div', { class: 'panel-body' },
      rowsHost,
      h('div', { class: 'settings-actions' },
        h('button', {
          class: 'btn btn-sm', type: 'button', text: '+ Add gate', disabled: !canWrite(),
          on: { click: () => addRow('', '') }
        }),
        h('button', {
          class: 'btn btn-sm btn-primary', type: 'button', text: 'Save gate commands',
          disabled: !canWrite() || uiBusy('gates'),
          on: { click: () => saveGateCommands(rowsHost) }
        }))));
}

async function saveGateCommands(rowsHost) {
  const map = {};
  for (const row of rowsHost.querySelectorAll('[data-gate-row]')) {
    const inputs = row.querySelectorAll('input');
    const name = inputs[0] ? inputs[0].value.trim() : '';
    const command = inputs[1] ? inputs[1].value.trim() : '';
    if (!name && !command) continue;
    if (!name || !command) {
      toast('Every gate row needs a name and a command', 'warn');
      return;
    }
    map[name] = command;
  }
  try {
    await api('/api/config', { method: 'PUT', body: { gate_commands: map } });
    await loadConfig();
    toast('Gate commands saved', 'ok');
    renderView();
  } catch (err) {
    toast('Gate commands: ' + describeError(err), 'error');
  }
}

/* ---------- About ---------- */

function renderSettingsAbout(project, config, health, settingsErrors) {
  const dashboardVersion = (config && config.version) || health.version || '—';
  const polierVersion = config && config.polier ? config.polier.version : '—';
  return h('section', { class: 'card-panel settings-section' },
    h('div', { class: 'panel-head' }, h('span', { class: 'panel-title', text: 'About' })),
    h('div', { class: 'panel-body' },
      h('dl', { class: 'kv settings-grid' },
        h('dt', { text: 'Dashboard' }), h('dd', { text: 'v' + dashboardVersion }),
        h('dt', { text: 'Polier' }), h('dd', { text: polierVersion ? 'v' + polierVersion : '—' }),
        h('dt', { text: 'Server started' }), h('dd', { text: health.started ? relTime(health.started) : '—' }),
        h('dt', { text: 'Role' }), h('dd', { text: (health.role || config.role || '—') + (config.read_only ? ' · read-only' : '') }),
        h('dt', { text: 'Token' }), h('dd', { text: config.token_required ? 'required' : 'not required' }),
        h('dt', { text: 'dashboard.json' }), h('dd', { text: settingsErrors.length ? settingsErrors.length + ' problem(s)' : 'valid' })),
      h('p', { class: 'hint', text: 'dashboard.json is committed project settings; sessions, gate commands and inbox read state live in the git-common runtime folder.' })));
}

/* =========================================================================
   2.2 — Timeline: stages on a time axis
   ========================================================================= */

function clampIndex(value, length) {
  if (!length) return 0;
  return Math.max(0, Math.min(length - 1, value));
}

function layoutTimelineStage(stage, dayCount, start) {
  const slots = [];
  const bars = [];
  const tasks = (stage.tasks || []).slice().sort((a, b) => {
    const byStart = String(a.start || '').localeCompare(String(b.start || ''));
    return byStart !== 0 ? byStart : String(a.id || '').localeCompare(String(b.id || ''));
  });
  for (const task of tasks) {
    const rawStart = dayIndexOf(task.start, start);
    const rawEnd = dayIndexOf(task.end, start);
    const startIndex = clampIndex(rawStart, dayCount);
    const endIndex = clampIndex(Math.max(rawEnd, rawStart), dayCount);
    let slot = slots.findIndex((last) => startIndex > last);
    if (slot === -1) {
      slot = slots.length;
      slots.push(endIndex);
    } else {
      slots[slot] = endIndex;
    }
    bars.push({ task: task, start: startIndex, end: endIndex, slot: slot });
  }
  return { bars: bars, slots: Math.max(1, slots.length) };
}

function dayCellClasses(day, weekStarts, todayIndex, index) {
  const classes = ['tl-cell'];
  if (Number(day.weekday) >= 5) classes.push('is-weekend');
  if (weekStarts.has(day.date) || Number(day.weekday) === 0) classes.push('is-week');
  if (index === todayIndex) classes.push('is-today');
  return classes.join(' ');
}

function renderTimeline() {
  const view = h('div', { class: 'timeline', dataset: { mode: timelineMode() } });
  dom.view.appendChild(view);
  const data = state.timeline;
  const mode = timelineMode();
  const dayWidth = mode === 'weeks' ? 12 : 28;

  view.appendChild(h('div', { class: 'view-head' },
    h('div', {},
      h('h1', { class: 'view-title', text: 'Timeline' }),
      h('p', {
        class: 'view-sub',
        text: data
          ? 'The plan on a time axis · ' + data.totals.tasks + ' tasks · ' + data.hours_per_day + ' h/day · today ' + shortDay(data.today)
          : 'The plan on a time axis'
      })),
    h('div', { class: 'view-actions' },
      h('div', { class: 'seg mode-toggle', role: 'group', 'aria-label': 'Timeline density' },
        h('label', { class: 'seg-option' },
          h('input', {
            type: 'radio', name: 'timeline-mode', value: 'days', checked: mode === 'days',
            on: { change: () => setTimelineMode('days') }
          }),
          h('span', { text: 'Days' })),
        h('label', { class: 'seg-option' },
          h('input', {
            type: 'radio', name: 'timeline-mode', value: 'weeks', checked: mode === 'weeks',
            on: { change: () => setTimelineMode('weeks') }
          }),
          h('span', { text: 'Weeks' }))),
      h('button', {
        class: 'btn btn-sm', type: 'button', text: 'Refresh',
        on: { click: () => loadTimeline().then(() => renderView()) }
      }))));

  if (viewLoadingOrError(view, state.timelineLoaded, state.timelineError, 'Building the timeline…')) return;
  if (!data) return;

  const days = Array.isArray(data.days) ? data.days : [];
  const stages = Array.isArray(data.stages) ? data.stages : [];
  const todayIndex = days.findIndex((day) => day.today);
  const weekStarts = new Set((data.weeks || []).map((week) => week.start));

  view.appendChild(h('div', { class: 'tl-toolbar' },
    h('div', { class: 'tl-totals' },
      h('span', {}, h('strong', { text: String(data.totals.scheduled) }), ' scheduled'),
      h('span', {}, h('strong', { text: String(data.totals.days) }), ' days'),
      h('span', {}, h('strong', { text: fmtHours(data.totals.hours) }), ' planned'),
      h('span', {}, h('strong', { text: String(data.totals.explicit) }), ' explicit dates'),
      h('span', {}, h('strong', { text: String(data.totals.critical_path_tasks) }), ' critical-path tasks')),
    h('div', { class: 'tl-controls' },
      h('span', { class: 'tl-note', text: data.hours_per_day + ' h per working day' }))));

  const legend = h('div', { class: 'tl-legend' });
  for (const status of Object.keys(STATUS)) {
    const color = STATUS[status].color;
    legend.appendChild(h('span', { class: 'tl-legend-item' },
      h('span', {
        class: 'tl-legend-swatch',
        style: {
          background: 'var(--st-' + color + '-bg)',
          borderLeftColor: 'var(--st-' + color + ')',
          borderLeftWidth: '3px',
          borderLeftStyle: 'solid'
        }
      }),
      STATUS[status].label));
  }
  legend.appendChild(h('span', { class: 'tl-legend-item' },
    h('span', { class: 'tl-legend-mark is-critical', text: '◆' }), 'critical path'));
  legend.appendChild(h('span', { class: 'tl-legend-item' },
    h('span', { class: 'tl-legend-mark is-explicit', text: '✎' }), 'explicit dates'));
  legend.appendChild(h('span', { class: 'tl-legend-item' },
    h('span', { class: 'tl-legend-mark is-overdue', text: '!' }), 'overdue'));
  legend.appendChild(h('span', { class: 'tl-legend-item' },
    h('span', { class: 'tl-legend-swatch', style: { background: 'var(--accent)', opacity: '0.55' } }), 'today'));
  view.appendChild(legend);

  if ((data.unscheduled || []).length) {
    const callout = h('div', { class: 'callout callout-warn' },
      h('div', { class: 'callout-stack' },
        h('div', { text: (data.unscheduled || []).length + ' task(s) could not be scheduled:' }),
        h('div', { class: 'tl-unscheduled' }, (data.unscheduled || []).map((id) => taskChip(id)))));
    view.appendChild(callout);
  }

  if (!days.length || !data.totals.scheduled) {
    view.appendChild(emptyState('Nothing scheduled yet',
      'The timeline needs tasks with a stage. Add tasks in the Plan view or set planning dates in a task drawer.',
      h('button', { class: 'btn', type: 'button', text: 'Open plan', on: { click: () => navigate('plan') } })));
    return;
  }

  /* month spans */
  const months = [];
  let current = null;
  days.forEach((day, index) => {
    const label = monthLabel(day.date);
    if (!current || current.label !== label) {
      current = { label: label, start: index, count: 1 };
      months.push(current);
    } else {
      current.count += 1;
    }
  });

  const grid = h('div', {
    class: 'tl-grid',
    style: { '--tl-day': dayWidth + 'px', '--tl-label': '212px' }
  });

  const axisWidth = days.length * dayWidth;
  const monthRow = h('div', { class: 'tl-months' });
  for (const month of months) {
    monthRow.appendChild(h('div', {
      class: 'tl-month',
      style: { width: month.count * dayWidth + 'px' },
      text: month.label
    }));
  }
  const dayRow = h('div', { class: 'tl-days' });
  days.forEach((day, index) => {
    const headCell = h('div', {
      class: 'tl-day-head'
        + (Number(day.weekday) >= 5 ? ' is-weekend' : '')
        + (weekStarts.has(day.date) || Number(day.weekday) === 0 ? ' is-week' : '')
        + (index === todayIndex ? ' is-today' : ''),
      style: { width: dayWidth + 'px' },
      title: fullDay(day.date) + (index === todayIndex ? ' · today' : '')
    },
      h('span', { class: 'tl-weekday', text: weekdayInitial(day.weekday) }),
      h('span', { class: 'tl-daynum', text: String(Number(String(day.date).slice(8, 10))) }));
    dayRow.appendChild(headCell);
  });

  grid.appendChild(h('div', { class: 'tl-head' },
    h('div', { class: 'tl-label' },
      h('span', { class: 'tl-corner-title', text: 'Stages' }),
      h('span', { class: 'tl-corner-sub', text: days.length + ' days · ' + shortDay(data.start) + ' → ' + shortDay(data.end) })),
    h('div', { class: 'tl-axis', style: { width: axisWidth + 'px' } }, monthRow, dayRow)));

  for (const stage of stages) {
    const layout = layoutTimelineStage(stage, days.length, data.start);
    const laneHeight = Math.max(44, layout.slots * 33 + 10);
    const label = h('div', { class: 'tl-label tl-stage' },
      h('div', { class: 'tl-stage-top' },
        h('span', { class: 'tl-stage-index', text: '#' + stage.index }),
        h('span', { class: 'tl-stage-title', text: stage.title || stage.id, title: stage.goal || '' })),
      h('div', { class: 'tl-stage-meta' },
        stage.owner_decision
          ? h('span', { class: 'chip', title: 'Owner decision: ' + stage.owner_decision, text: stage.owner_decision })
          : null,
        h('span', { class: 'tl-stage-count', text: (stage.counts && stage.counts.done ? stage.counts.done : 0) + '/' + ((stage.tasks || []).length) + ' · ' + percentText(stage.progress) })),
      progressBar(stage.progress * 100, 100, stage.progress >= 1 ? 'is-ok' : ''));

    const lane = h('div', { class: 'tl-lane', style: { width: axisWidth + 'px', height: laneHeight + 'px' } });
    days.forEach((day, index) => {
      lane.appendChild(h('div', {
        class: dayCellClasses(day, weekStarts, todayIndex, index),
        style: { left: index * dayWidth + 'px', width: dayWidth + 'px' }
      }));
    });
    if (todayIndex >= 0) {
      lane.appendChild(h('div', { class: 'tl-today-line', style: { left: (todayIndex * dayWidth + dayWidth / 2) + 'px' } }));
    }

    if (!layout.bars.length) {
      lane.appendChild(h('div', { class: 'tl-empty-lane', text: 'No tasks in this stage.' }));
    }
    for (const bar of layout.bars) {
      const task = bar.task;
      const color = stMeta(task.status).color;
      const width = Math.max(dayWidth - 4, (bar.end - bar.start + 1) * dayWidth - 4);
      const marks = [];
      if (task.critical) marks.push(h('span', { class: 'tl-bar-mark is-critical', title: 'On the critical path', text: '◆' }));
      if (task.explicit) marks.push(h('span', { class: 'tl-bar-mark is-explicit', title: 'Explicit planning dates', text: '✎' }));
      if (task.overdue) marks.push(h('span', { class: 'tl-bar-mark is-overdue', title: 'Overdue (target date passed)', text: '!' }));
      const title = task.id + ' · ' + (task.title || '') +
        '\n' + task.status + (task.explicit ? ' · explicit' : '') +
        (task.critical ? ' · critical path' : '') +
        (task.overdue ? ' · overdue' : '') +
        '\n' + shortDay(task.start) + ' → ' + shortDay(task.end) +
        ' · ' + fmtHours(task.hours) +
        (task.estimate_hours !== null && task.estimate_hours !== undefined ? ' (estimate ' + fmtHours(task.estimate_hours) + ')' : '') +
        (task.labels && task.labels.length ? '\nlabels: ' + task.labels.map(labelTitle).join(', ') : '');
      lane.appendChild(h('button', {
        class: 'tl-bar status-' + color + (task.critical ? ' is-critical' : ''),
        type: 'button',
        style: { left: (bar.start * dayWidth + 2) + 'px', width: width + 'px', top: (bar.slot * 33 + 7) + 'px' },
        title: title,
        dataset: { taskId: task.id },
        on: { click: () => openTask(task.id) }
      },
        h('span', { class: 'tl-bar-id', text: task.id }),
        h('span', { class: 'tl-bar-title', text: task.title || '' }),
        marks.length ? h('span', { class: 'tl-bar-mark', style: { marginLeft: 'auto', display: 'inline-flex', gap: '2px' } }, marks) : null));
    }

    grid.appendChild(h('div', { class: 'tl-row' }, label, lane));
  }

  view.appendChild(h('div', { class: 'tl-scroll' }, grid));
  view.appendChild(h('p', { class: 'tl-note', style: { marginTop: '8px' },
    text: 'Bars are derived from dependencies, estimates and the stage order; ✎ marks owner-set dates, ◆ the critical path. Click a bar to open the task.' }));
}

/* =========================================================================
   2.2 — Cycles: stages as execution units, with burndown and decisions
   ========================================================================= */

function svgEl(tag, attrs, text) {
  const node = document.createElementNS('http://www.w3.org/2000/svg', tag);
  if (attrs) {
    for (const key of Object.keys(attrs)) {
      if (attrs[key] === null || attrs[key] === undefined) continue;
      node.setAttribute(key, String(attrs[key]));
    }
  }
  if (text !== null && text !== undefined) node.textContent = String(text);
  return node;
}

function cycleStatusTone(status) {
  if (status === 'completed') return 'green';
  if (status === 'active') return 'blue';
  if (status === 'stopped') return 'red';
  return 'neutral';
}

function burndownSvg(points, options) {
  const opts = options || {};
  const rows = Array.isArray(points) ? points : [];
  const width = 320;
  const height = 82;
  const left = 28;
  const right = 8;
  const top = 8;
  const bottom = 16;
  const svg = svgEl('svg', {
    viewBox: '0 0 ' + width + ' ' + height,
    role: 'img',
    'aria-label': opts.label || 'Burndown: remaining and completed tasks over time'
  });
  if (!rows.length) {
    svg.appendChild(svgEl('text', { x: width / 2, y: height / 2, 'text-anchor': 'middle', class: 'g-title' }, 'Burndown appears after the first done task'));
    return svg;
  }
  const max = Math.max(1, ...rows.map((row) => Number(row.remaining) || 0), ...rows.map((row) => Number(row.done) || 0));
  const span = Math.max(1, rows.length - 1);
  const step = (width - left - right) / span;
  const yOf = (value) => top + (height - top - bottom) * (1 - (Number(value) || 0) / max);

  for (const fraction of [0, 0.5, 1]) {
    const value = max * fraction;
    const y = yOf(value);
    svg.appendChild(svgEl('line', { x1: left, x2: width - right, y1: y, y2: y, stroke: 'var(--border)', 'stroke-width': '1' }));
    svg.appendChild(svgEl('text', { x: left - 4, y: y + 3, 'text-anchor': 'end', class: 'g-title', 'font-size': '8' }, String(Math.round(value))));
  }
  const polyline = (key, color) => {
    const points = rows.map((row, index) => (left + index * step) + ',' + yOf(row[key])).join(' ');
    return svgEl('polyline', { points: points, fill: 'none', stroke: color, 'stroke-width': '1.6', 'stroke-linejoin': 'round' });
  };
  svg.appendChild(polyline('remaining', 'var(--accent)'));
  svg.appendChild(polyline('done', 'var(--st-green)'));
  rows.forEach((row, index) => {
    if (rows.length <= 2 || index === 0 || index === rows.length - 1) {
      svg.appendChild(svgEl('circle', { cx: left + index * step, cy: yOf(row.remaining), r: '1.8', fill: 'var(--accent)' }));
      svg.appendChild(svgEl('circle', { cx: left + index * step, cy: yOf(row.done), r: '1.8', fill: 'var(--st-green)' }));
    }
  });
  svg.appendChild(svgEl('text', { x: left, y: height - 3, class: 'g-title', 'font-size': '8' }, shortDay(rows[0].date)));
  svg.appendChild(svgEl('text', { x: width - right, y: height - 3, 'text-anchor': 'end', class: 'g-title', 'font-size': '8' }, shortDay(rows[rows.length - 1].date)));
  return svg;
}

function renderCycles() {
  const view = h('div', { class: 'cycles' });
  dom.view.appendChild(view);
  const data = state.cycles;

  view.appendChild(h('div', { class: 'view-head' },
    h('div', {},
      h('h1', { class: 'view-title', text: 'Cycles' }),
      h('p', { class: 'view-sub', text: data ? data.totals.cycles + ' cycles · ' + data.totals.completed + ' completed · active: ' + (data.active || '—') : 'Stages as execution units' })),
    h('div', { class: 'view-actions' },
      h('button', { class: 'btn btn-sm', type: 'button', text: 'Refresh', on: { click: () => loadCycles().then(() => renderView()) } }))));

  if (viewLoadingOrError(view, state.cyclesLoaded, state.cyclesError, 'Reading the cycles…')) return;
  if (!data) return;
  const cycles = data.cycles || [];
  if (!cycles.length) {
    view.appendChild(emptyState('No cycles yet', 'Cycles are the board stages. Add stages in the Plan view.', null));
    return;
  }

  const totals = data.totals || {};
  const active = cycles.find((cycle) => cycle.status === 'active');
  view.appendChild(h('div', { class: 'tile-row' },
    statTile('Active cycle', active ? active.title : '—', { tone: 'tile-blue', sub: active ? '#' + active.index + ' · ' + percentText(active.progress) : 'none active' }),
    statTile('Completed', (totals.completed || 0) + ' / ' + (totals.cycles || 0), { tone: 'tile-green', sub: 'stages finished' }),
    statTile('Tasks done', (totals.done || 0) + ' / ' + (totals.tasks || 0), { tone: 'tile-accent', sub: 'across all cycles' }),
    statTile('Effort', fmtHours(totals.estimate_hours) + ' est', { tone: 'tile-violet', sub: fmtHours(totals.actual_hours) + ' actual' }),
    statTile('Tokens', fmtTokens(totals.tokens || 0), { tone: 'tile-accent', sub: 'recorded usage' })));

  const grid = h('div', { class: 'cycles-grid' });
  for (const cycle of cycles) {
    const tone = cycleStatusTone(cycle.status);
    const card = h('section', {
      class: 'card-panel cycle-card' + (data.active === cycle.id ? ' is-active' : ''),
      id: 'cycle-' + cycle.id
    });

    const decisionControls = h('div', { class: 'cycle-actions' },
      h('span', { class: 'hint', text: 'owner' }),
      ['continue', 'pending', 'stop'].map((decision) => h('button', {
        class: 'seg-chip', type: 'button',
        'aria-pressed': cycle.owner_decision === decision ? 'true' : 'false',
        disabled: !canWrite() || state.cyclesBusy === cycle.id,
        title: canWrite() ? 'Set the owner decision to ' + decision : 'The dashboard is read-only',
        on: { click: () => changeCycleDecision(cycle, decision) }
      }, decision === 'stop' ? 'stop' : decision === 'pending' ? 'pending' : 'continue')));

    card.appendChild(h('div', { class: 'cycle-head' },
      h('span', { class: 'cycle-index', text: '#' + cycle.index }),
      h('div', { class: 'cycle-title-wrap' },
        h('div', { class: 'cycle-title', text: cycle.title || cycle.id }),
        cycle.goal ? h('div', { class: 'cycle-goal', text: cycle.goal }) : null),
      h('div', { class: 'cycle-meta' },
        h('span', { class: 'badge bg-' + tone + ' st-' + tone },
          h('span', { class: 'dot' }), cycle.status),
        cycle.owner_decision ? h('span', { class: 'pill', text: 'decision: ' + cycle.owner_decision }) : null)));

    card.appendChild(h('div', { class: 'cycle-progress' },
      h('div', { class: 'cycle-progress-line' },
        h('span', { text: cycle.done + ' / ' + cycle.total + ' tasks done' }),
        h('span', { class: 'mono', text: percentText(cycle.progress) })),
      progressBar(cycle.done, cycle.total, cycle.progress >= 1 ? 'is-ok' : '')));

    const gates = cycle.exit_gates || [];
    if (gates.length) {
      card.appendChild(h('div', { class: 'cycle-gates' },
        gates.map((gate) => h('span', {
          class: 'chip ' + (gate.passed ? 'chip-pass' : 'chip-miss'),
          title: gate.passed ? 'Gate has a passing record' : 'Gate is still missing',
          text: gate.name
        }))));
    }

    card.appendChild(decisionControls);

    card.appendChild(h('div', { class: 'burndown' },
      burndownSvg(cycle.burndown, { label: 'Burndown for ' + (cycle.title || cycle.id) }),
      h('div', { class: 'burndown-caption' },
        h('span', {}, h('span', { class: 'chart-legend-dot', style: { background: 'var(--accent)' } }), 'remaining'),
        h('span', {}, h('span', { class: 'chart-legend-dot', style: { background: 'var(--st-green)' } }), 'done'))));

    card.appendChild(h('div', { class: 'cycle-effort' },
      h('span', {}, 'tokens ', h('strong', { text: fmtTokens(cycle.tokens || 0) })),
      h('span', {}, 'estimate ', h('strong', { text: fmtHours(cycle.estimate_hours) })),
      h('span', {}, 'actual ', h('strong', { text: fmtHours(cycle.actual_hours) })),
      h('span', {}, 'sessions ', h('strong', { text: String(cycle.sessions || 0) })),
      cycle.tasks_open && cycle.tasks_open.length
        ? h('span', { class: 'cycle-task-open', text: cycle.tasks_open.length + ' open' })
        : null));

    const taskList = h('div', { class: 'cycle-tasks' });
    for (const task of cycle.tasks || []) {
      taskList.appendChild(h('button', {
        class: 'cycle-task', type: 'button', title: 'Open ' + task.id,
        on: { click: () => openTask(task.id) }
      },
        h('span', { class: 'queue-main' },
          h('div', { class: 'queue-title', text: task.title || task.id }),
          h('div', { class: 'queue-sub', text: task.id + (task.owner ? ' · ' + task.owner : '') })),
        statusPill(task.status)));
    }
    if (!(cycle.tasks || []).length) taskList.appendChild(h('div', { class: 'hint', text: 'No tasks in this cycle.' }));
    card.appendChild(taskList);
    grid.appendChild(card);
  }
  view.appendChild(grid);
  view.appendChild(h('p', { class: 'tl-note', style: { marginTop: '10px' },
    text: 'Burndown uses the state events in runs/: done dates are real, not planned.' }));
}

async function changeCycleDecision(cycle, decision) {
  if (!cycle || decision === cycle.owner_decision) return;
  if (decision === 'stop') {
    const confirmed = await confirmDialog({
      title: 'Stop cycle "' + (cycle.title || cycle.id) + '"?',
      message: 'A stopped stage blocks dispatch for its tasks until the owner continues it again.',
      confirmLabel: 'Stop cycle'
    });
    if (!confirmed) return;
  }
  state.cyclesBusy = cycle.id;
  renderView();
  try {
    await api('/api/plan/stages/' + encodeURIComponent(cycle.id) + '/decision', {
      method: 'POST',
      body: { decision: decision }
    });
    toast('Cycle ' + cycle.id + ' decision: ' + decision, 'ok');
    await Promise.all([loadCycles(), loadSnapshot()]);
    if (state.route.view === 'cycles') renderView();
  } catch (err) {
    toast('Cycle decision failed: ' + describeError(err), 'error');
  } finally {
    state.cyclesBusy = null;
    renderView();
  }
}

/* =========================================================================
   2.2 — Modules: the package map as the structural view
   ========================================================================= */

function moduleHealthTone(health) {
  if (health === 'attention') return 'attention';
  if (health === 'watch') return 'watch';
  if (health === 'done') return 'done';
  return 'ok';
}

function renderModules() {
  const view = h('div', { class: 'modules' });
  dom.view.appendChild(view);
  const data = state.modules;

  view.appendChild(h('div', { class: 'view-head' },
    h('div', {},
      h('h1', { class: 'view-title', text: 'Modules' }),
      h('p', { class: 'view-sub', text: data ? data.totals.modules + ' modules · ' + data.totals.tasks + ' tasks · ' + data.totals.attention + ' need attention · ' + data.totals.watch + ' to watch' : 'The package map' })),
    h('div', { class: 'view-actions' },
      h('button', { class: 'btn btn-sm', type: 'button', text: 'Refresh', on: { click: () => loadModules().then(() => renderView()) } }))));

  if (viewLoadingOrError(view, state.modulesLoaded, state.modulesError, 'Reading the package map…')) return;
  if (!data) return;

  const totals = data.totals || {};
  view.appendChild(h('div', { class: 'tile-row' },
    statTile('Modules', totals.modules || 0, { tone: 'tile-blue', sub: 'packages on the board' }),
    statTile('Module tasks', totals.tasks || 0, { tone: 'tile-accent', sub: (totals.done || 0) + ' done' }),
    statTile('Attention', totals.attention || 0, { tone: 'tile-red', sub: 'blocked or failed' }),
    statTile('Watch', totals.watch || 0, { tone: 'tile-amber', sub: 'missing docs or gates' }),
    statTile('Unassigned', (data.unassigned && data.unassigned.count) || 0, { tone: 'tile-violet', sub: 'tasks without a package' })));

  const modules = data.modules || [];
  if (!modules.length) {
    view.appendChild(emptyState('No modules declared',
      'The board has no packages[] entries yet. The Plan view edits stages and tasks, and the generator writes the package map.',
      null));
  } else {
    const grid = h('div', { class: 'module-grid' });
    for (const module of modules) {
      const health = moduleHealthTone(module.health);
      const counts = module.counts || {};
      const totalsRow = module.totals || {};
      const card = h('section', { class: 'card-panel module-card' });

      card.appendChild(h('div', { class: 'module-head' },
        h('span', { class: 'module-path', text: module.path || '(no path)', title: module.path || '' }),
        h('span', { class: 'chip', text: module.kind || 'module' }),
        h('span', { class: 'pill health-' + health, title: (module.health_reasons || []).join(', ') || 'all good', text: module.health })));

      card.appendChild(h('div', { class: 'cycle-progress' },
        h('div', { class: 'cycle-progress-line' },
          h('span', { text: (totalsRow.done || 0) + ' / ' + (totalsRow.tasks || 0) + ' tasks done' }),
          h('span', { class: 'mono', text: percentText(module.progress) })),
        progressBar(totalsRow.done || 0, totalsRow.tasks || 0, module.progress >= 1 ? 'is-ok' : '')));

      const countsRow = h('div', { class: 'module-chips' });
      for (const status of Object.keys(counts)) {
        const meta = stMeta(status);
        countsRow.appendChild(h('span', { class: 'chip' },
          h('span', { class: 'dot st-' + meta.color }), meta.label + ' ' + counts[status]));
      }
      if (!Object.keys(counts).length) countsRow.appendChild(h('span', { class: 'hint', text: 'No tasks' }));
      card.appendChild(countsRow);

      card.appendChild(h('div', { class: 'module-stats' },
        h('span', {}, 'tokens ', h('strong', { text: fmtTokens(totalsRow.tokens || 0) })),
        h('span', {}, 'estimate ', h('strong', { text: fmtHours(totalsRow.estimate_hours) })),
        h('span', {}, 'actual ', h('strong', { text: fmtHours(totalsRow.actual_hours) })),
        module.waiting ? h('span', {}, h('strong', { class: 'st-amber', text: String(module.waiting) }), ' waiting') : null));

      if ((module.health_reasons || []).length) {
        card.appendChild(h('div', { class: 'module-stats' },
          h('span', { class: 'st-amber', text: 'watch: ' + module.health_reasons.join(' · ') })));
      }

      if ((module.docs || []).length) {
        card.appendChild(h('div', { class: 'module-subhead', text: 'Docs' }));
        card.appendChild(h('div', { class: 'module-chips' },
          module.docs.map((doc) => h('span', {
            class: 'doc-chip ' + (doc.present ? 'is-present' : 'is-missing'),
            title: doc.path
          }, doc.present ? '✓' : '○', ' ', basename(doc.path)))));
      }

      if ((module.contracts || []).length) {
        card.appendChild(h('div', { class: 'module-subhead', text: 'Contracts' }));
        card.appendChild(h('div', { class: 'module-chips' },
          module.contracts.map((contract) => h('span', {
            class: 'chip', title: (contract.path || '') + (contract.schema_files ? ' · ' + contract.schema_files + ' schema files' : '')
          }, (contract.name || 'contract') + (contract.version ? ' v' + contract.version : '')))));
      }

      if ((module.may_import || []).length) {
        card.appendChild(h('div', { class: 'module-imports' }, 'may import ', h('code', { text: module.may_import.join(', ') })));
      }

      card.appendChild(h('div', { class: 'module-subhead', text: 'Tasks' }));
      const taskChips = h('div', { class: 'module-chips' });
      for (const task of module.tasks || []) {
        const meta = stMeta(task.status);
        taskChips.appendChild(h('button', {
          class: 'chip chip-link req-task-chip', type: 'button',
          title: (task.title || task.id) + ' · ' + meta.label + (task.gates_missing && task.gates_missing.length ? ' · missing gates: ' + task.gates_missing.join(', ') : ''),
          on: { click: () => openTask(task.id) }
        },
          h('span', { class: 'req-task-status st-' + meta.color, style: { background: 'currentColor' } }),
          h('span', { class: 'mono', text: task.id })));
      }
      if (!(module.tasks || []).length) taskChips.appendChild(h('span', { class: 'hint', text: 'No tasks assigned to this module.' }));
      card.appendChild(taskChips);

      grid.appendChild(card);
    }
    view.appendChild(grid);
  }

  /* unassigned tasks */
  const unassigned = (data.unassigned && data.unassigned.tasks) || [];
  const unassignedCard = h('section', { class: 'card-panel', style: { marginTop: '16px' } },
    h('div', { class: 'panel-head' },
      h('span', { class: 'panel-title', text: 'Unassigned tasks' }),
      h('span', { class: 'pill', text: String(unassigned.length) })),
    h('div', { class: 'panel-body' }));
  if (!unassigned.length) {
    unassignedCard.querySelector('.panel-body').appendChild(h('div', { class: 'hint', text: 'Every task has a module.' }));
  } else {
    const chips = h('div', { class: 'module-chips' });
    for (const task of unassigned) {
      const meta = stMeta(task.status);
      chips.appendChild(h('button', {
        class: 'chip chip-link', type: 'button',
        title: (task.title || task.id) + (task.package ? ' · ' + task.package : ''),
        on: { click: () => openTask(task.id) }
      }, h('span', { class: 'dot st-' + meta.color }), task.id));
    }
    unassignedCard.querySelector('.panel-body').appendChild(h('div', { class: 'col', style: { gap: '8px' } },
      h('div', { class: 'hint', text: 'Tasks without a board package. Assign a package in the task properties or the plan editor.' }),
      chips));
  }
  view.appendChild(unassignedCard);
  view.appendChild(h('p', { class: 'tl-note', style: { marginTop: '10px' },
    text: 'Health is derived: attention = blocked or failed tasks, watch = missing gates or package docs, done = all tasks done.' }));
}

/* =========================================================================
   2.2 — Coverage: requirements, tasks and evidence
   ========================================================================= */

function coverageStateTone(stateName) {
  if (stateName === 'covered') return 'green';
  if (stateName === 'partial') return 'amber';
  if (stateName === 'open') return 'blue';
  if (stateName === 'missing') return 'red';
  return 'neutral';
}

function renderCoverage() {
  const view = h('div', { class: 'coverage' });
  dom.view.appendChild(view);
  const data = state.coverage;

  view.appendChild(h('div', { class: 'view-head' },
    h('div', {},
      h('h1', { class: 'view-title', text: 'Coverage' }),
      h('p', { class: 'view-sub', text: data ? data.summary.defined + ' defined requirements · ' + data.summary.covered + ' covered · ' + data.summary.uncovered + ' uncovered · ' + data.summary.undefined.length + ' undefined' : 'Requirements mapped to tasks and evidence' })),
    h('div', { class: 'view-actions' },
      h('button', { class: 'btn btn-sm', type: 'button', text: 'Refresh', on: { click: () => loadCoverage().then(() => renderView()) } }))));

  if (viewLoadingOrError(view, state.coverageLoaded, state.coverageError, 'Reading the requirements…')) return;
  if (!data) return;
  const summary = data.summary || {};
  const requirements = data.requirements || [];

  view.appendChild(h('div', { class: 'tile-row' },
    statTile('Defined', summary.defined || 0, { tone: 'tile-accent', sub: 'in docs/quality.md' }),
    statTile('Covered', summary.covered || 0, { tone: 'tile-green', sub: 'all linked tasks done' }),
    statTile('Partial', summary.partial || 0, { tone: 'tile-amber', sub: 'some work done' }),
    statTile('Open', summary.open || 0, { tone: 'tile-blue', sub: 'tasks not finished' }),
    statTile('Missing', summary.missing || 0, { tone: 'tile-red', sub: 'no linked tasks' }),
    statTile('Undefined', (summary.undefined || []).length, { tone: 'tile-violet', sub: 'referenced, not defined' })));

  if ((summary.undefined || []).length) {
    view.appendChild(h('div', { class: 'callout callout-warn' },
      h('div', { class: 'callout-stack' },
        h('div', { text: 'Tasks reference requirements that docs/quality.md does not define:' }),
        h('div', { class: 'undefined-list' },
          summary.undefined.map((requirementId) => h('span', { class: 'chip', text: requirementId })),
          h('span', { class: 'hint', text: 'Add a "**' + (summary.undefined[0] || 'D9') + '** text" line to the quality document.' })))));
  }

  const counts = {
    all: requirements.length,
    covered: summary.covered || 0,
    partial: summary.partial || 0,
    open: summary.open || 0,
    missing: summary.missing || 0
  };
  const filter = state.coverageFilter || 'all';
  const chips = h('div', { class: 'seg-chips', style: { marginBottom: '12px' } });
  for (const key of ['all', 'covered', 'partial', 'open', 'missing']) {
    chips.appendChild(h('button', {
      class: 'seg-chip', type: 'button',
      'aria-pressed': filter === key ? 'true' : 'false',
      on: { click: () => { state.coverageFilter = key; renderView(); } }
    }, capitalize(key), h('span', { class: 'faint', text: String(counts[key] || 0) })));
  }
  view.appendChild(chips);

  const filtered = requirements.filter((requirement) => filter === 'all' || requirement.state === filter);
  if (!filtered.length) {
    view.appendChild(emptyState('No requirements match',
      filter === 'all'
        ? 'Add "**D1** text" requirement lines to docs/quality.md and reference them from tasks with satisfies.'
        : 'Switch the filter to see the other requirements.',
      null));
    return;
  }

  const list = h('div', { class: 'coverage-list' });
  for (const requirement of filtered) {
    const tone = coverageStateTone(requirement.state);
    const card = h('section', {
      class: 'card-panel req-card' + (requirement.defined ? '' : ' req-undefined'),
      id: 'req-' + requirement.id
    });

    card.appendChild(h('div', { class: 'req-head' },
      h('span', { class: 'req-id', text: requirement.id }),
      h('div', { class: 'req-main' },
        h('div', { class: 'req-title', text: requirement.title || requirement.id }),
        requirement.defined && requirement.definition && requirement.definition !== requirement.title
          ? h('div', { class: 'req-claim', text: truncate(requirement.definition, 220) })
          : null),
      h('div', { class: 'row-wrap' },
        requirement.defined ? null : h('span', { class: 'pill pill-warn', text: 'undefined' }),
        h('span', { class: 'badge bg-' + tone + ' st-' + tone }, h('span', { class: 'dot' }), requirement.state))));

    card.appendChild(h('div', { class: 'req-progress' },
      progressBar(requirement.coverage * 100, 100, requirement.state === 'covered' ? 'is-ok' : ''),
      h('span', { class: 'req-count', text: requirement.done + '/' + requirement.total + ' done · ' + requirement.active + ' active · ' + requirement.evidence + ' evidence' })));

    const taskChips = h('div', { class: 'req-tasks' });
    for (const task of requirement.tasks || []) {
      const meta = stMeta(task.status);
      taskChips.appendChild(h('button', {
        class: 'chip chip-link req-task-chip', type: 'button',
        title: (task.title || task.id) + ' · ' + meta.label + (task.owner ? ' · ' + task.owner : ''),
        on: { click: () => openTask(task.id) }
      },
        h('span', { class: 'req-task-status st-' + meta.color, style: { background: 'currentColor' } }),
        h('span', { class: 'mono', text: task.id }),
        task.evidence ? h('span', { class: 'req-evidence', title: task.evidence + ' passing gate record(s)', text: '✓' + task.evidence }) : null));
    }
    if (!(requirement.tasks || []).length) taskChips.appendChild(h('span', { class: 'hint', text: 'No task references this requirement.' }));
    card.appendChild(taskChips);
    list.appendChild(card);
  }
  view.appendChild(list);
  view.appendChild(h('p', { class: 'tl-note', style: { marginTop: '10px' },
    text: 'Requirements come from docs/quality.md; tasks link them with satisfies. Evidence counts passing gate records.' }));
}

/* =========================================================================
   2.2 — Analytics: throughput, cycle time, gates, effort
   ========================================================================= */

function chartCard(title, body, options) {
  const opts = options || {};
  const card = h('section', { class: 'card-panel' + (opts.span ? ' span-2' : '') },
    h('div', { class: 'panel-head' },
      h('span', { class: 'panel-title', text: title }),
      opts.note ? h('span', { class: 'hint', text: opts.note }) : null),
    h('div', { class: 'panel-body' }, body));
  return card;
}

function throughputChart(rows) {
  const width = 640;
  const height = 170;
  const left = 32;
  const right = 10;
  const top = 10;
  const bottom = 24;
  const data = Array.isArray(rows) ? rows : [];
  const max = Math.max(1, ...data.map((row) => Number(row.done) || 0));
  const svg = svgEl('svg', {
    viewBox: '0 0 ' + width + ' ' + height,
    role: 'img',
    'aria-label': 'Tasks completed per ISO week, last ' + data.length + ' weeks (total ' + data.reduce((sum, row) => sum + Number(row.done || 0), 0) + ')'
  });
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;
  for (const fraction of [0, 0.5, 1]) {
    const y = top + plotHeight * (1 - fraction);
    svg.appendChild(svgEl('line', { x1: left, x2: width - right, y1: y, y2: y, stroke: 'var(--border)', 'stroke-width': '1' }));
    svg.appendChild(svgEl('text', { x: left - 5, y: y + 3, 'text-anchor': 'end', class: 'g-title', 'font-size': '9' }, String(Math.round(max * fraction))));
  }
  const slot = data.length ? plotWidth / data.length : plotWidth;
  const barWidth = Math.max(4, Math.min(30, slot - 6));
  data.forEach((row, index) => {
    const value = Number(row.done) || 0;
    const barHeight = plotHeight * (value / max);
    const x = left + slot * index + (slot - barWidth) / 2;
    const y = top + plotHeight - barHeight;
    svg.appendChild(svgEl('rect', {
      x: x, y: y, width: barWidth, height: Math.max(0, barHeight),
      rx: '2', fill: value ? 'var(--accent)' : 'var(--surface-3)'
    }));
    svg.appendChild(svgEl('title', {}, row.week + ': ' + value + ' done'));
    if (index % 3 === 0 || index === data.length - 1) {
      const label = String(row.week || '').replace(/^\d{4}-/, '');
      svg.appendChild(svgEl('text', {
        x: left + slot * index + slot / 2, y: height - 6, 'text-anchor': 'middle',
        class: 'g-title', 'font-size': '9'
      }, label));
    }
  });
  return svg;
}

function horizontalBars(rows, options) {
  const opts = options || {};
  const data = Array.isArray(rows) ? rows : [];
  if (!data.length) return h('div', { class: 'chart-empty', text: opts.emptyText || 'No data yet.' });
  const max = Math.max(1, ...data.map((row) => Number(row.value) || 0));
  const box = h('div', { class: 'hbars', role: 'img', 'aria-label': opts.label || 'Bar chart' });
  for (const row of data) {
    const value = Number(row.value) || 0;
    box.appendChild(h('div', { class: 'hbar-row' },
      h('span', { class: 'hbar-label', title: row.label, text: row.label }),
      h('div', { class: 'hbar-track' },
        h('div', {
          class: 'hbar-fill',
          style: { width: Math.max(value ? 2 : 0, (value / max) * 100) + '%', background: row.color || 'var(--accent)' }
        })),
      h('span', { class: 'hbar-value', text: row.display !== undefined ? String(row.display) : String(value) })));
  }
  return box;
}

function gateResultColor(result) {
  if (result === 'pass') return 'var(--st-green)';
  if (result === 'fail') return 'var(--st-red)';
  if (result === 'infra' || result === 'timeout') return 'var(--st-amber)';
  if (result === 'busy') return 'var(--st-orange)';
  return 'var(--st-neutral)';
}

function groupedEffortBars(rows) {
  const data = Array.isArray(rows) ? rows : [];
  if (!data.length) return h('div', { class: 'chart-empty', text: 'No stage effort recorded yet.' });
  const max = Math.max(1, ...data.map((row) => Math.max(Number(row.estimate_hours) || 0, Number(row.actual_hours) || 0)));
  const box = h('div', { class: 'grouped-bars', role: 'img', 'aria-label': 'Estimate and actual hours per stage' });
  for (const row of data) {
    const estimate = Number(row.estimate_hours) || 0;
    const actual = Number(row.actual_hours) || 0;
    box.appendChild(h('div', { class: 'grouped-row' },
      h('span', { class: 'hbar-label', title: row.stage, text: row.stage || '(none)' }),
      h('div', { class: 'grouped-bars-track' },
        h('div', { class: 'grouped-bar' },
          h('span', { class: 'chart-legend-dot', style: { background: 'var(--st-blue)' } }),
          h('div', { class: 'hbar-track' },
            h('div', { class: 'hbar-fill', style: { width: Math.max(estimate ? 2 : 0, (estimate / max) * 100) + '%', background: 'var(--st-blue)' } })),
          h('span', { class: 'hbar-value', text: fmtHours(estimate) })),
        h('div', { class: 'grouped-bar' },
          h('span', { class: 'chart-legend-dot', style: { background: 'var(--st-green)' } }),
          h('div', { class: 'hbar-track' },
            h('div', { class: 'hbar-fill', style: { width: Math.max(actual ? 2 : 0, (actual / max) * 100) + '%', background: 'var(--st-green)' } })),
          h('span', { class: 'hbar-value', text: fmtHours(actual) })))));
  }
  return box;
}

function renderAnalytics() {
  const view = h('div', { class: 'analytics' });
  dom.view.appendChild(view);
  const data = state.analytics;

  view.appendChild(h('div', { class: 'view-head' },
    h('div', {},
      h('h1', { class: 'view-title', text: 'Analytics' }),
      h('p', { class: 'view-sub', text: data ? 'Derived from board state, runs/ and evidence · ' + data.kpis.tasks_total + ' tasks · ' + data.today : 'Project health from evidence' })),
    h('div', { class: 'view-actions' },
      h('button', { class: 'btn btn-sm', type: 'button', text: 'Refresh', on: { click: () => loadAnalytics().then(() => renderView()) } }))));

  if (viewLoadingOrError(view, state.analyticsLoaded, state.analyticsError, 'Computing analytics…')) return;
  if (!data) return;
  const kpis = data.kpis || {};

  const completion = Number(kpis.completion) || 0;
  const gateRate = kpis.gate_pass_rate;
  const reworkRate = Number(kpis.rework_rate) || 0;
  const delta = Number(kpis.estimate_delta_hours) || 0;
  view.appendChild(h('div', { class: 'analytics-kpis' },
    tileValue('Completion', percentText(completion), {
      tone: completion >= 1 ? 'is-good' : (completion > 0 ? '' : ''),
      sub: (kpis.tasks_done || 0) + ' of ' + (kpis.tasks_total || 0) + ' tasks done'
    }),
    tileValue('Gate pass rate', gateRate === null || gateRate === undefined ? '—' : percentText(gateRate), {
      tone: gateRate === null || gateRate === undefined ? '' : (gateRate >= 0.9 ? 'is-good' : (gateRate >= 0.6 ? 'is-warn' : 'is-bad')),
      sub: (data.gate_results || []).reduce((sum, row) => sum + Number(row.count || 0), 0) + ' gate records'
    }),
    tileValue('Rework rate', percentText(reworkRate), {
      tone: reworkRate > 0.3 ? 'is-bad' : (reworkRate > 0 ? 'is-warn' : 'is-good'),
      sub: (kpis.rework_tasks || 0) + ' task(s) reworked'
    }),
    tileValue('Blocked now', countText(kpis.blocked_now), {
      tone: kpis.blocked_now ? 'is-warn' : 'is-good',
      sub: 'avg ' + Number(kpis.blocked_avg_days || 0).toFixed(1) + 'd · max ' + Number(kpis.blocked_max_days || 0).toFixed(1) + 'd'
    }),
    tileValue('Estimate vs actual', (delta > 0 ? '+' : '') + fmtHours(delta), {
      tone: delta > 0 ? 'is-warn' : (delta < 0 ? 'is-good' : ''),
      sub: 'est ' + fmtHours(kpis.estimate_hours) + ' · act ' + fmtHours(kpis.actual_hours)
    }),
    tileValue('Tokens', fmtTokens(kpis.tokens_total || 0), {
      sub: (kpis.attempts_total || 0) + ' attempts'
    }),
    tileValue('Sessions', countText(kpis.sessions_total), {
      sub: fmtTokens(data.sessions ? data.sessions.tokens : 0) + ' tokens · ' + fmtDuration((data.sessions && data.sessions.total_seconds) || 0)
    })));

  const statusChips = h('div', { class: 'row-wrap', style: { marginBottom: '14px' } },
    h('span', { class: 'hint', text: 'Status:' }));
  for (const status of Object.keys(kpis.status_counts || {})) {
    const meta = stMeta(status);
    statusChips.appendChild(h('span', { class: 'chip' },
      h('span', { class: 'dot st-' + meta.color }), meta.label + ' ' + kpis.status_counts[status]));
  }
  view.appendChild(statusChips);

  const grid = h('div', { class: 'analytics-grid' });

  const throughputBody = h('div', {},
    h('div', { class: 'chart' }, throughputChart(data.throughput || [])),
    h('div', { class: 'chart-legend' },
      h('span', { class: 'chart-legend-item' },
        h('span', { class: 'chart-legend-dot', style: { background: 'var(--accent)' } }),
        data.throughput_total + ' done in the last 12 weeks')));
  grid.appendChild(chartCard('Throughput', throughputBody, { span: true, note: 'tasks completed per ISO week' }));

  grid.appendChild(chartCard('Cycle time per stage',
    horizontalBars((data.cycle_time || []).map((row) => ({
      label: row.stage + ' (' + row.tasks + ')',
      value: Number(row.avg_days) || 0,
      display: Number(row.avg_days).toFixed(1) + 'd',
      color: 'var(--st-violet)'
    })), { emptyText: 'No finished task has a start and done event yet.', label: 'Average cycle time per stage in days' }),
    { note: 'first work event → done' }));

  grid.appendChild(chartCard('Gate results',
    horizontalBars((data.gate_results || []).map((row) => ({
      label: row.result,
      value: Number(row.count) || 0,
      color: gateResultColor(row.result)
    })), { emptyText: 'No gate records yet.', label: 'Gate results by outcome' }),
    { note: 'evidence records' }));

  grid.appendChild(chartCard('Estimate vs actual per stage',
    groupedEffortBars((data.effort && data.effort.stages) || []),
    { span: true, note: 'hours · estimate is planned, actual comes from runs and sessions' }));

  grid.appendChild(chartCard('Tokens per stage',
    horizontalBars(((data.effort && data.effort.stages) || []).map((row) => ({
      label: row.stage,
      value: Number(row.tokens) || 0,
      display: fmtTokens(row.tokens || 0),
      color: 'var(--st-teal)'
    })), { emptyText: 'No token usage recorded yet.', label: 'Token usage per stage' })));

  grid.appendChild(chartCard('Sessions',
    h('div', { class: 'grouped-bars' },
      ...(Object.keys((data.sessions && data.sessions.counts) || {}).length
        ? Object.keys(data.sessions.counts).map((status) => h('div', { class: 'between' },
          h('span', { class: 'chart-legend-item' }, statusPill(status)),
          h('span', { class: 'mono', text: String(data.sessions.counts[status]) })))
        : [h('div', { class: 'chart-empty', text: 'No headless sessions recorded yet.' })]),
      h('div', { class: 'between', style: { marginTop: '8px' } },
        h('span', { class: 'hint', text: 'Total session time' }),
        h('span', { class: 'mono', text: fmtDuration((data.sessions && data.sessions.total_seconds) || 0) })))));

  view.appendChild(grid);
  view.appendChild(h('p', { class: 'tl-note', style: { marginTop: '10px' },
    text: 'Every number is derived from files Polier already writes; there is no separate metrics store.' }));
}

/* =========================================================================
   2.3 — Pages: collections, search, reader, history and backlinks
   ========================================================================= */

function pageCollectionId(page) {
  return page.collection + (page.subcollection ? '/' + page.subcollection : '');
}

function selectedPageEntry() {
  return state.pageDetail || (state.pagesSelected ? pageByPath(state.pagesSelected) : null);
}

function openPage(path, ref) {
  if (!path) return;
  state.pagesSelected = path;
  state.pagesRef = ref || null;
  const target = '#/pages/' + encodeURIComponent(path);
  if (location.hash === target) applyRoute();
  else location.hash = target;
}

function renderPages() {
  const view = h('div', { class: 'pages-view' });
  dom.view.appendChild(view);
  const index = state.pages;
  const page = state.pageDetail;
  const searchQuery = String(state.pagesSearch || '').trim();
  const searching = searchQuery.length >= 2;

  view.appendChild(h('div', { class: 'view-head' },
    h('div', {},
      h('h1', { class: 'view-title', text: 'Pages' }),
      h('p', {
        class: 'view-sub',
        text: index
          ? index.counts.pages + ' pages · ' + index.counts.collections + ' collections · ' + index.counts.favorites + ' favorites'
          : 'The project knowledge layer'
      })),
    h('div', { class: 'view-actions' },
      h('button', {
        class: 'btn btn-sm', type: 'button', text: 'Refresh',
        on: {
          click: async () => {
            await loadPages();
            if (state.pagesSelected) await loadPage(state.pagesSelected, state.pagesRef);
            renderView();
          }
        }
      }))));

  view.appendChild(h('div', { class: 'pages-toolbar' },
    h('div', { class: 'pages-searchbox' },
      h('input', {
        class: 'input', type: 'search', value: state.pagesSearch || '',
        placeholder: 'Search the project knowledge…', 'aria-label': 'Search pages',
        'data-fkey': 'pages-search',
        on: { input: (event) => schedulePagesSearch(event.target.value) }
      })),
    h('span', { class: 'hint', text: searching ? 'Searching titles and Markdown content (min 2 characters).' : 'Read-only view of Markdown files in the project.' })));

  if (!state.pagesLoaded && !index) {
    if (state.pagesError) {
      view.appendChild(errorCallout(state.pagesError));
      view.appendChild(h('div', { style: { marginTop: '10px' } },
        h('button', { class: 'btn', type: 'button', text: 'Retry', on: { click: () => loadPages().then(() => renderView()) } })));
    } else {
      view.appendChild(loadingRow('Indexing the project pages…'));
    }
    return;
  }
  if (state.pagesError) view.appendChild(errorCallout(state.pagesError));
  if (!index || !(index.pages || []).length) {
    view.appendChild(emptyState('No pages found',
      'Polier indexes README, ARCHITECTURE, docs/, tasks/, reviews/ and package Markdown files.',
      null));
    return;
  }

  const grid = h('div', { class: 'pages-grid' });
  grid.appendChild(renderPagesSidebar());
  grid.appendChild(renderPagesList(searching, searchQuery));
  grid.appendChild(renderPagesReader());
  view.appendChild(grid);
}

function renderPagesSidebar() {
  const index = state.pages;
  const sidebar = h('aside', { class: 'pages-sidebar', 'aria-label': 'Page collections' });
  const favorites = (state.pageFavorites || []).filter((path) => pageExistsInIndex(path));

  sidebar.appendChild(h('div', { class: 'pages-section-title' },
    h('span', { text: 'Favorites' }),
    h('span', { class: 'collection-count', text: String(favorites.length) })));
  if (!favorites.length) {
    sidebar.appendChild(h('div', { class: 'hint', style: { padding: '2px 6px 6px' }, text: 'Star a page to keep it here.' }));
  } else {
    for (const path of favorites) {
      const page = pageByPath(path);
      if (!page) continue;
      sidebar.appendChild(h('button', {
        class: 'fav-page' + (state.pagesSelected === path ? ' is-active' : ''),
        type: 'button', title: path,
        on: { click: () => openPage(path) }
      },
        h('span', { class: 'page-star is-on', 'aria-hidden': 'true', text: '★' }),
        h('span', { class: 'truncate', text: page.title })));
    }
  }

  sidebar.appendChild(h('div', { class: 'pages-section-title', style: { marginTop: '6px' } },
    h('span', { text: 'Collections' })));
  const selectedPage = state.pagesSelected ? pageByPath(state.pagesSelected) : null;
  const selectedCollection = selectedPage ? pageCollectionId(selectedPage) : null;
  for (const collection of index.collections || []) {
    const containsSelected = collection.id === selectedCollection;
    const stored = state.pagesCollapsed[collection.id];
    const collapsed = stored === undefined ? !containsSelected : Boolean(stored);
    const label = collection.sub ? collection.title + ' / ' + collection.sub : collection.title;
    const wrapper = h('div', { class: 'tree-collection' });
    wrapper.appendChild(h('button', {
      class: 'tree-toggle', type: 'button',
      'aria-expanded': collapsed ? 'false' : 'true',
      title: collection.id,
      on: {
        click: () => {
          state.pagesCollapsed[collection.id] = !collapsed;
          renderView();
        }
      }
    },
      h('span', { class: 'tree-caret', text: collapsed ? '▸' : '▾' }),
      h('span', { class: 'truncate', text: label }),
      h('span', { class: 'collection-count', text: String(collection.pages.length) })));
    if (!collapsed) {
      const pagesHost = h('div', { class: 'tree-pages' });
      for (const entry of collection.pages) {
        pagesHost.appendChild(h('button', {
          class: 'tree-page' + (state.pagesSelected === entry.path ? ' is-active' : ''),
          type: 'button', title: entry.path,
          on: { click: () => openPage(entry.path) }
        },
          h('span', { class: 'truncate', text: entry.title }),
          entry.favorite ? h('span', { class: 'page-star is-on', 'aria-hidden': 'true', text: '★' }) : null));
      }
      wrapper.appendChild(pagesHost);
    }
    sidebar.appendChild(wrapper);
  }
  return sidebar;
}

function renderPagesList(searching, searchQuery) {
  const pane = h('section', { class: 'pages-listpane', 'aria-label': 'Page list' });
  const index = state.pages;

  if (searching) {
    pane.appendChild(h('div', { class: 'pages-list-head' },
      h('span', { class: 'pages-list-title', text: 'Search results' }),
      h('span', { class: 'collection-count', text: state.pagesResults.length + ' hits' })));
    if (state.pagesSearching) {
      pane.appendChild(h('div', { class: 'reader-loading' }, loadingRow('Searching…')));
      return pane;
    }
    if (state.pagesSearchError) {
      pane.appendChild(h('div', { class: 'reader-loading' }, errorCallout(state.pagesSearchError)));
      return pane;
    }
    if (!state.pagesResults.length) {
      pane.appendChild(h('div', { class: 'pages-empty', text: 'No page matches "' + searchQuery + '".' }));
      return pane;
    }
    for (const result of state.pagesResults) {
      pane.appendChild(h('button', {
        class: 'page-list-item' + (state.pagesSelected === result.path ? ' is-active' : ''),
        type: 'button', title: result.path,
        on: { click: () => openPage(result.path) }
      },
        h('div', { class: 'page-list-title-row' },
          h('span', { class: 'page-list-name', text: result.title }),
          h('span', { class: 'page-result-score', text: 'score ' + result.score }),
          result.favorite ? h('span', { class: 'page-star is-on', 'aria-hidden': 'true', text: '★' }) : null),
        h('div', { class: 'page-list-path', text: result.path }),
        result.snippet ? h('div', { class: 'page-result-snippet', text: result.snippet }) : null));
    }
    return pane;
  }

  const selectedPage = state.pagesSelected ? pageByPath(state.pagesSelected) : null;
  const collectionId = selectedPage ? pageCollectionId(selectedPage) : (index.collections[0] || {}).id;
  const collection = (index.collections || []).find((entry) => entry.id === collectionId) || index.collections[0];
  if (!collection) {
    pane.appendChild(h('div', { class: 'pages-empty', text: 'No collection selected.' }));
    return pane;
  }
  pane.appendChild(h('div', { class: 'pages-list-head' },
    h('span', { class: 'pages-list-title', text: collection.title + (collection.sub ? ' / ' + collection.sub : '') }),
    h('span', { class: 'collection-count', text: collection.pages.length + ' pages' })));
  for (const entry of collection.pages) {
    pane.appendChild(h('button', {
      class: 'page-list-item' + (state.pagesSelected === entry.path ? ' is-active' : ''),
      type: 'button', title: entry.path,
      on: { click: () => openPage(entry.path) }
    },
      h('div', { class: 'page-list-title-row' },
        h('span', { class: 'page-list-name', text: entry.title }),
        entry.favorite ? h('span', { class: 'page-star is-on', 'aria-hidden': 'true', text: '★' }) : null),
      h('div', { class: 'page-list-path', text: entry.path })));
  }
  return pane;
}

function renderPagesReader() {
  const pane = h('article', { class: 'pages-reader', 'aria-label': 'Page reader' });
  const path = state.pagesSelected;

  if (!path) {
    pane.appendChild(h('div', { class: 'pages-empty', text: 'Select a page from the list.' }));
    return pane;
  }
  if (state.pageLoading && !state.pageDetail) {
    pane.appendChild(h('div', { class: 'reader-loading' }, loadingRow('Loading the page…')));
    return pane;
  }
  if (state.pageError && !state.pageDetail) {
    pane.appendChild(h('div', { class: 'reader-loading' }, errorCallout(state.pageError)));
    pane.appendChild(h('div', { style: { padding: '0 16px 16px' } },
      h('button', { class: 'btn', type: 'button', text: 'Retry', on: { click: () => loadPage(path, state.pagesRef).then(() => renderView()) } })));
    return pane;
  }
  const page = state.pageDetail;
  if (!page) {
    pane.appendChild(h('div', { class: 'pages-empty', text: 'This page could not be loaded.' }));
    return pane;
  }

  const favorite = (state.pageFavorites || []).indexOf(page.path) !== -1;
  pane.appendChild(h('div', { class: 'reader-head' },
    h('div', { class: 'reader-title-row' },
      h('h2', { class: 'reader-title', text: page.title || page.path }),
      h('button', {
        class: 'page-star' + (favorite ? ' is-on' : ''),
        type: 'button',
        disabled: !canWrite(),
        title: canWrite() ? (favorite ? 'Remove from favorites' : 'Add to favorites') : 'The dashboard is read-only',
        'aria-label': favorite ? 'Remove from favorites' : 'Add to favorites',
        text: favorite ? '★' : '☆',
        on: { click: () => togglePageFavorite(page.path) }
      })),
    h('div', { class: 'reader-meta' },
      h('span', { class: 'reader-path', text: page.path }),
      pageKindChip(page.kind),
      h('span', { class: 'chip', text: page.collection_title + (page.subcollection ? ' / ' + page.subcollection : '') }),
      h('span', { text: page.words + ' words' }),
      h('span', { text: 'updated ' + relTime(page.updated) }),
      page.favorite ? h('span', { class: 'badge bg-amber st-amber', text: 'favorite' }) : null)));

  if (page.ref) {
    pane.appendChild(h('div', { class: 'revision-banner' },
      h('span', { text: 'Viewing old revision ' + page.ref + ' — the working copy may differ.' }),
      h('button', {
        class: 'btn btn-sm', type: 'button', text: 'Back to current',
        on: { click: () => openPage(page.path, null) }
      })));
  }

  const body = h('div', { class: 'reader-body' });
  const content = h('div', { class: 'md' }, mdFragment(page.text || '', { linkBase: page.path }));
  content.addEventListener('click', (event) => {
    const target = event.target && event.target.closest ? event.target.closest('a[data-page-link]') : null;
    if (!target) return;
    event.preventDefault();
    openPage(target.getAttribute('data-page-link'));
  });
  body.appendChild(content);

  /* History */
  const history = page.history || [];
  const historySection = h('section', { class: 'reader-section' },
    h('div', { class: 'reader-section-title' },
      h('span', { text: 'History' }),
      page.ref ? h('button', {
        class: 'btn btn-sm btn-ghost', type: 'button', text: 'Current',
        on: { click: () => openPage(page.path, null) }
      }) : h('span', { class: 'hint', text: history.length + ' revision(s)' })));
  if (!history.length) {
    historySection.appendChild(h('div', { class: 'hint', text: 'No git history for this page (not committed yet).' }));
  } else {
    for (const entry of history) {
      historySection.appendChild(h('button', {
        class: 'history-row' + (page.ref === entry.hash ? ' is-current' : ''),
        type: 'button', title: entry.subject,
        on: { click: () => openPage(page.path, entry.hash) }
      },
        h('span', { class: 'history-hash', text: entry.hash }),
        h('span', { class: 'history-date', text: entry.date }),
        h('span', { class: 'truncate', style: { flex: '1 1 auto' }, text: entry.subject }),
        h('span', { class: 'hint', text: entry.author })));
    }
  }
  body.appendChild(historySection);

  /* Backlinks */
  const backlinks = page.backlinks || [];
  const backlinkSection = h('section', { class: 'reader-section' },
    h('div', { class: 'reader-section-title' },
      h('span', { text: 'Backlinks' }),
      h('span', { class: 'hint', text: backlinks.length + ' reference(s)' })));
  if (!backlinks.length) {
    backlinkSection.appendChild(h('div', { class: 'hint', text: 'No page or task references this page yet.' }));
  } else {
    const chips = h('div', { class: 'backlink-chips' });
    for (const link of backlinks) {
      if (link.kind === 'task') {
        chips.appendChild(h('button', {
          class: 'chip chip-link req-task-chip', type: 'button',
          title: 'Open task ' + link.id,
          on: { click: () => openTask(link.id) }
        },
          statusDot(link.status),
          h('span', { class: 'mono', text: link.id })));
      } else {
        chips.appendChild(h('button', {
          class: 'chip chip-link', type: 'button', title: link.path,
          on: { click: () => openPage(link.path) }
        }, link.title || link.path));
      }
    }
    backlinkSection.appendChild(chips);
  }
  body.appendChild(backlinkSection);

  pane.appendChild(body);
  return pane;
}

/* =========================================================================
   2.3 — Intake: proposals, accept/reject and task creation
   ========================================================================= */

function intakeFilterLabel(status) {
  return status === 'all' ? 'All' : status;
}

function filteredIntakeEntries() {
  const entries = intakeEntries();
  const filter = state.intakeFilter || 'proposed';
  return filter === 'all' ? entries : entries.filter((entry) => entry.status === filter);
}

function renderIntake() {
  const view = h('div', { class: 'intake' });
  dom.view.appendChild(view);
  const counts = intakeCounts();
  const total = state.intake ? state.intake.total : 0;

  view.appendChild(h('div', { class: 'view-head' },
    h('div', {},
      h('h1', { class: 'view-title', text: 'Intake' }),
      h('p', { class: 'view-sub', text: total + ' proposal(s) · ' + counts.proposed + ' proposed · ' + counts.accepted + ' accepted · ' + counts.rejected + ' rejected' })),
    h('div', { class: 'view-actions' },
      canWrite() ? h('button', {
        class: 'btn btn-sm btn-primary', type: 'button', text: 'New proposal',
        on: { click: () => openNewIntakeModal() }
      }) : null,
      h('button', {
        class: 'btn btn-sm', type: 'button', text: 'Refresh',
        on: { click: () => loadIntake().then(() => renderView()) }
      }))));

  if (!state.intakeLoaded && !state.intake) {
    if (state.intakeError) {
      view.appendChild(errorCallout(state.intakeError));
      view.appendChild(h('div', { style: { marginTop: '10px' } },
        h('button', { class: 'btn', type: 'button', text: 'Retry', on: { click: () => loadIntake().then(() => renderView()) } })));
    } else {
      view.appendChild(loadingRow('Reading the intake…'));
    }
    return;
  }
  if (state.intakeError) view.appendChild(errorCallout(state.intakeError));

  view.appendChild(h('div', { class: 'tile-row' },
    statTile('Proposed', counts.proposed, { tone: 'tile-amber', sub: 'waiting for a decision', onClick: () => { state.intakeFilter = 'proposed'; renderView(); } }),
    statTile('Accepted', counts.accepted, { tone: 'tile-green', sub: 'became tasks', onClick: () => { state.intakeFilter = 'accepted'; renderView(); } }),
    statTile('Rejected', counts.rejected, { tone: 'tile-red', sub: 'with a reason', onClick: () => { state.intakeFilter = 'rejected'; renderView(); } }),
    statTile('Total', total, { tone: 'tile-accent', sub: 'all proposals', onClick: () => { state.intakeFilter = 'all'; renderView(); } })));

  const chips = h('div', { class: 'seg-chips', style: { marginBottom: '12px' } });
  for (const status of ['proposed', 'accepted', 'rejected', 'all']) {
    const amount = status === 'all' ? total : counts[status] || 0;
    chips.appendChild(h('button', {
      class: 'seg-chip', type: 'button',
      'aria-pressed': (state.intakeFilter || 'proposed') === status ? 'true' : 'false',
      on: { click: () => { state.intakeFilter = status; renderView(); } }
    }, capitalize(status), h('span', { class: 'faint', text: String(amount) })));
  }
  view.appendChild(chips);

  const entries = filteredIntakeEntries();
  if (!entries.length) {
    view.appendChild(emptyState(
      state.intakeFilter === 'proposed' ? 'No proposals waiting' : 'No ' + (state.intakeFilter || 'proposed') + ' proposals',
      state.intakeFilter === 'proposed'
        ? 'Ideas, issues and requests land here first. Accepting one creates a pending task with a template.'
        : 'Switch the filter to see other proposals.',
      canWrite() && state.intakeFilter === 'proposed'
        ? h('button', { class: 'btn btn-primary', type: 'button', text: 'New proposal', on: { click: () => openNewIntakeModal() } })
        : null));
    return;
  }

  const list = h('div', { class: 'intake-list' });
  for (const entry of entries) list.appendChild(renderIntakeEntry(entry));
  view.appendChild(list);
}

function renderIntakeEntry(entry) {
  const card = h('section', { class: 'card-panel intake-card', id: 'intake-' + entry.id });
  card.appendChild(h('div', { class: 'intake-head' },
    h('div', { class: 'intake-main' },
      h('div', { class: 'intake-title-row' },
        h('span', { class: 'intake-id', text: entry.id }),
        h('span', { class: 'intake-title', text: entry.title })),
      h('div', { class: 'intake-meta' },
        h('span', { class: 'chip', title: 'Created ' + entry.created, text: relTime(entry.created) }),
        h('span', { class: 'chip', text: 'by ' + (entry.created_by || '—') }),
        h('span', { class: 'chip', text: 'source: ' + (entry.source || '—') }),
        entry.links && entry.links.length ? h('span', { class: 'chip', text: entry.links.length + ' link(s)' }) : null)),
    h('div', { class: 'row-wrap' },
      intakeKindChip(entry.kind),
      intakePriorityChip(entry.priority),
      intakeStatusPill(entry.status))));

  if (entry.description) card.appendChild(h('div', { class: 'intake-desc', text: entry.description }));

  if (entry.task) {
    card.appendChild(h('div', { class: 'intake-meta' },
      h('span', { class: 'hint', text: 'accepted as task' }),
      taskChip(entry.task)));
  }
  if (entry.decision) {
    card.appendChild(h('div', { class: 'decision-box' },
      entry.status === 'rejected' ? 'Rejected' : 'Accepted',
      ' by ' + (entry.decision.by || '—') + ' · ' + relTime(entry.decision.at) +
      (entry.decision.note ? ' — ' + entry.decision.note : '')));
  }
  if (entry.links && entry.links.length) {
    const links = h('div', { class: 'intake-links' });
    for (const link of entry.links) {
      if (/\.md$/i.test(link) && feature('pages')) {
        links.appendChild(h('button', {
          class: 'chip chip-link', type: 'button', title: 'Open page ' + link,
          on: { click: () => openPage(link) }
        }, h('span', { class: 'mono', text: link })));
      } else if (/^https?:\/\//i.test(link)) {
        links.appendChild(h('a', { class: 'chip', href: link, rel: 'noopener noreferrer', text: link }));
      } else {
        links.appendChild(h('span', { class: 'chip mono', title: link, text: link }));
      }
    }
    card.appendChild(links);
  }

  const actions = h('div', { class: 'intake-actions' },
    h('button', {
      class: 'btn btn-sm', type: 'button', text: entry.status === 'proposed' ? 'Review proposal' : 'Details',
      on: { click: () => openIntakeDetail(entry.id) }
    }));
  if (entry.status === 'proposed' && canWrite()) {
    actions.appendChild(h('button', {
      class: 'btn btn-sm btn-primary', type: 'button', text: 'Accept',
      on: { click: () => openAcceptModal(entry) }
    }));
    actions.appendChild(h('button', {
      class: 'btn btn-sm btn-danger', type: 'button', text: 'Reject',
      on: { click: () => openRejectModal(entry) }
    }));
  }
  card.appendChild(actions);
  return card;
}

/* ---------- new proposal ---------- */

function openNewIntakeModal() {
  if (!canWrite()) return;
  const titleInput = h('input', { class: 'input', type: 'text', placeholder: 'Short, actionable title', 'data-autofocus': '1' });
  const descriptionArea = h('textarea', { class: 'textarea', rows: '3', placeholder: 'What is it, and why does it matter?' });
  const kindSelect = h('select', { class: 'select', 'aria-label': 'Kind' },
    ['idea', 'issue', 'request', 'question'].map((kind) => h('option', { value: kind, text: kind })));
  const prioritySelect = h('select', { class: 'select', 'aria-label': 'Priority' },
    ['low', 'medium', 'high'].map((priority) => h('option', { value: priority, text: priority })));
  prioritySelect.value = 'medium';
  const linksArea = h('textarea', { class: 'textarea', rows: '2', placeholder: 'One project path or URL per line (optional)' });
  const errorBox = h('div');

  const body = h('div', { class: 'plan-editor' }, errorBox,
    h('div', { class: 'intake-form-grid' },
      h('label', { class: 'field span-2' },
        h('span', { class: 'field-label', text: 'Title' }), titleInput,
        h('span', { class: 'field-help', text: '3–160 characters.' })),
      h('label', { class: 'field' }, h('span', { class: 'field-label', text: 'Kind' }), kindSelect),
      h('label', { class: 'field' }, h('span', { class: 'field-label', text: 'Priority' }), prioritySelect),
      h('label', { class: 'field span-2' },
        h('span', { class: 'field-label', text: 'Description' }), descriptionArea),
      h('label', { class: 'field span-2' },
        h('span', { class: 'field-label', text: 'Links' }), linksArea,
        h('span', { class: 'field-help', text: 'Optional — paths like docs/quality.md or URLs.' }))));

  openModal({
    title: 'New intake proposal',
    body: body,
    footer: [
      h('button', { class: 'btn', type: 'button', text: 'Cancel', on: { click: () => closeModal() } }),
      h('button', {
        class: 'btn btn-primary', type: 'button', text: 'Create proposal',
        on: {
          click: async () => {
            const title = titleInput.value.trim();
            if (title.length < 3 || title.length > 160) {
              errorBox.replaceChildren(errorCallout(new ApiError('The title must be 3–160 characters.', 400, null)));
              return;
            }
            try {
              await api('/api/intake', {
                method: 'POST',
                body: {
                  title: title,
                  description: descriptionArea.value.trim(),
                  kind: kindSelect.value,
                  priority: prioritySelect.value,
                  links: linksArea.value.split('\n').map((line) => line.trim()).filter(Boolean),
                  source: 'web'
                }
              });
              closeModal();
              await loadIntake();
              state.intakeFilter = 'proposed';
              renderView();
              toast('Proposal created', 'ok');
            } catch (err) {
              errorBox.replaceChildren(errorCallout(err));
            }
          }
        }
      })
    ]
  });
  focusSoon(titleInput);
}

/* ---------- detail / edit ---------- */

function openIntakeDetail(entryId) {
  const entry = intakeEntries().find((item) => item.id === entryId);
  if (!entry) { toast('Unknown intake entry', 'error'); return; }
  const proposed = entry.status === 'proposed';
  const editable = proposed && canWrite();
  const errorBox = h('div');
  const body = h('div', { class: 'plan-editor' }, errorBox);

  let titleInput = null;
  let descriptionArea = null;
  let kindSelect = null;
  let prioritySelect = null;
  let linksArea = null;

  if (editable) {
    titleInput = h('input', { class: 'input', type: 'text', value: entry.title, 'data-autofocus': '1' });
    descriptionArea = h('textarea', { class: 'textarea', rows: '4' });
    descriptionArea.value = entry.description || '';
    kindSelect = h('select', { class: 'select', 'aria-label': 'Kind' },
      ['idea', 'issue', 'request', 'question'].map((kind) => {
        const option = h('option', { value: kind, text: kind });
        if (entry.kind === kind) option.selected = true;
        return option;
      }));
    kindSelect.value = entry.kind || 'idea';
    prioritySelect = h('select', { class: 'select', 'aria-label': 'Priority' },
      ['low', 'medium', 'high'].map((priority) => {
        const option = h('option', { value: priority, text: priority });
        if (entry.priority === priority) option.selected = true;
        return option;
      }));
    prioritySelect.value = entry.priority || 'medium';
    linksArea = h('textarea', { class: 'textarea', rows: '2', placeholder: 'One link per line' });
    linksArea.value = (entry.links || []).join('\n');
    body.appendChild(h('div', { class: 'intake-form-grid' },
      h('label', { class: 'field span-2' }, h('span', { class: 'field-label', text: 'Title' }), titleInput),
      h('label', { class: 'field' }, h('span', { class: 'field-label', text: 'Kind' }), kindSelect),
      h('label', { class: 'field' }, h('span', { class: 'field-label', text: 'Priority' }), prioritySelect),
      h('label', { class: 'field span-2' }, h('span', { class: 'field-label', text: 'Description' }), descriptionArea),
      h('label', { class: 'field span-2' }, h('span', { class: 'field-label', text: 'Links' }), linksArea)));
  } else {
    body.appendChild(h('div', { class: 'row-wrap' },
      h('span', { class: 'intake-id', text: entry.id }),
      intakeStatusPill(entry.status),
      intakeKindChip(entry.kind),
      intakePriorityChip(entry.priority)));
    body.appendChild(h('div', { class: 'intake-title', text: entry.title }));
    if (entry.description) body.appendChild(h('div', { class: 'intake-desc', style: { WebkitLineClamp: 'unset' }, text: entry.description }));
    body.appendChild(h('div', { class: 'intake-meta' },
      h('span', { text: 'created ' + relTime(entry.created) + ' by ' + (entry.created_by || '—') }),
      h('span', { text: 'source: ' + (entry.source || '—') })));
    if (entry.links && entry.links.length) {
      const links = h('div', { class: 'intake-links' });
      for (const link of entry.links) links.appendChild(h('span', { class: 'chip mono', text: link }));
      body.appendChild(links);
    }
    if (entry.task) {
      body.appendChild(h('div', { class: 'row-wrap' }, h('span', { class: 'hint', text: 'Created task:' }), taskChip(entry.task)));
    }
    if (entry.decision) {
      body.appendChild(h('div', { class: 'decision-box' },
        h('div', {}, entry.status === 'rejected' ? 'Rejected by ' : 'Accepted by ', h('strong', { text: entry.decision.by || '—' }),
          ' · ' + relTime(entry.decision.at)),
        entry.decision.note ? h('div', { text: entry.decision.note }) : null));
    }
  }

  const footer = [];
  footer.push(h('button', { class: 'btn', type: 'button', text: 'Close', on: { click: () => closeModal() } }));
  if (editable) {
    footer.push(h('button', {
      class: 'btn', type: 'button', text: 'Save changes',
      on: {
        click: async () => {
          const title = titleInput.value.trim();
          if (title.length < 3 || title.length > 160) {
            errorBox.replaceChildren(errorCallout(new ApiError('The title must be 3–160 characters.', 400, null)));
            return;
          }
          try {
            await api('/api/intake/' + encodeURIComponent(entry.id), {
              method: 'PATCH',
              body: {
                title: title,
                description: descriptionArea.value.trim(),
                kind: kindSelect.value,
                priority: prioritySelect.value,
                links: linksArea.value.split('\n').map((line) => line.trim()).filter(Boolean)
              }
            });
            closeModal();
            await loadIntake();
            renderView();
            toast('Proposal saved', 'ok');
          } catch (err) {
            errorBox.replaceChildren(errorCallout(err));
          }
        }
      }
    }));
    footer.push(h('button', {
      class: 'btn btn-danger', type: 'button', text: 'Reject',
      on: { click: () => { closeModal(); openRejectModal(entry); } }
    }));
    footer.push(h('button', {
      class: 'btn btn-primary', type: 'button', text: 'Accept…',
      on: { click: () => { closeModal(); openAcceptModal(entry); } }
    }));
  }
  openModal({ title: 'Proposal ' + entry.id, body: body, footer: footer });
}

/* ---------- accept ---------- */

async function openAcceptModal(entry) {
  if (!canWrite()) return;
  if (!state.templatesLoaded) await loadTaskTemplates();
  const stages = (state.snapshot && state.snapshot.stages) || [];
  if (!stages.length) { toast('No stages on the board', 'warn'); return; }
  const errorBox = h('div');

  const templateSelect = h('select', { class: 'select', 'aria-label': 'Task template' },
    h('option', { value: '', text: 'No template' }),
    (state.templates || []).map((template) => h('option', { value: template.id, text: (template.name || template.id) + ' (' + template.id + ')' })));
  const stageSelect = h('select', { class: 'select', 'aria-label': 'Stage' },
    stages.map((stage) => h('option', { value: stage.id, text: '#' + stage.index + ' ' + (stage.title || stage.id) })));
  stageSelect.value = stages[0].id;
  const idInput = h('input', { class: 'input', type: 'text', placeholder: 'auto', 'aria-label': 'Task id' });
  const ownerInput = h('input', { class: 'input', type: 'text', placeholder: 'optional owner', 'aria-label': 'Owner' });
  const packageInput = h('input', { class: 'input', type: 'text', placeholder: 'optional package path', 'aria-label': 'Package' });
  const complexityInput = h('input', { class: 'input', type: 'number', min: '1', max: '10', placeholder: '2', 'aria-label': 'Complexity' });
  const estimateInput = h('input', { class: 'input', type: 'number', min: '0', max: '10000', step: '0.5', placeholder: 'hours', 'aria-label': 'Estimate hours' });
  const scopeArea = h('textarea', { class: 'textarea', rows: '3', placeholder: 'One write path per line' });
  const scopeReadArea = h('textarea', { class: 'textarea', rows: '2', placeholder: 'One read path per line (optional)' });
  const acceptanceArea = h('textarea', { class: 'textarea', rows: '2', placeholder: 'One criterion per line' });
  const gatesInput = h('input', { class: 'input', type: 'text', placeholder: 'layout, tests' });
  const noteInput = h('input', { class: 'input', type: 'text', placeholder: 'Optional decision note' });
  const labelsHost = h('div', { class: 'label-select' });
  const labels = settingsLabels();
  const grouped = new Map();
  for (const label of labels) {
    const group = settingsGroups().indexOf(label.group) !== -1 ? label.group : 'custom';
    if (!grouped.has(group)) grouped.set(group, []);
    grouped.get(group).push(label);
  }
  for (const group of settingsGroups()) {
    if (!grouped.has(group)) continue;
    labelsHost.appendChild(h('span', { class: 'props-label-group', text: group }));
    for (const label of grouped.get(group)) {
      labelsHost.appendChild(h('label', { class: 'checkbox' },
        h('input', { type: 'checkbox', value: label.id, 'data-accept-label': label.id }),
        labelChip(label)));
    }
  }
  if (!labels.length) labelsHost.appendChild(h('span', { class: 'hint', text: 'No labels defined.' }));
  const preview = h('div', { class: 'template-preview', text: 'Pick a template to pre-fill scope, acceptance, gates, effort and labels.' });

  const applyTemplate = () => {
    const template = templateById(templateSelect.value);
    if (!template) {
      preview.textContent = 'Pick a template to pre-fill scope, acceptance, gates, effort and labels.';
      return;
    }
    if (template.stage && stages.some((stage) => stage.id === template.stage)) stageSelect.value = template.stage;
    if (template.owner) ownerInput.value = template.owner;
    if (template.package) packageInput.value = template.package;
    if (template.complexity !== null && template.complexity !== undefined) complexityInput.value = String(template.complexity);
    if (template.estimate_hours !== null && template.estimate_hours !== undefined) estimateInput.value = String(template.estimate_hours);
    scopeArea.value = (template.scope_write || []).join('\n');
    scopeReadArea.value = (template.scope_read || []).join('\n');
    acceptanceArea.value = (template.acceptance || []).join('\n');
    gatesInput.value = (template.gates || []).join(', ');
    for (const box of labelsHost.querySelectorAll('[data-accept-label]')) {
      box.checked = (template.labels || []).indexOf(box.getAttribute('data-accept-label')) !== -1;
    }
    preview.replaceChildren(templateChips(template));
  };
  templateSelect.addEventListener('change', applyTemplate);

  const body = h('div', { class: 'accept-structure' },
    errorBox,
    h('p', { class: 'hint', text: 'Accepting creates a pending task on the board from "' + entry.title + '". Stage, write scope, acceptance and gates are required.' }),
    h('div', { class: 'editor-template-bar' },
      h('label', { class: 'field' }, h('span', { class: 'field-label', text: 'Template' }), templateSelect),
      h('label', { class: 'field' }, h('span', { class: 'field-label', text: 'Stage' }), stageSelect)),
    preview,
    h('div', { class: 'intake-form-grid' },
      h('label', { class: 'field' }, h('span', { class: 'field-label', text: 'Task id' }), idInput),
      h('label', { class: 'field' }, h('span', { class: 'field-label', text: 'Owner' }), ownerInput),
      h('label', { class: 'field' }, h('span', { class: 'field-label', text: 'Package' }), packageInput),
      h('label', { class: 'field' }, h('span', { class: 'field-label', text: 'Complexity' }), complexityInput),
      h('label', { class: 'field' }, h('span', { class: 'field-label', text: 'Estimate (hours)' }), estimateInput),
      h('label', { class: 'field' }, h('span', { class: 'field-label', text: 'Gates' }), gatesInput),
      h('label', { class: 'field span-2' }, h('span', { class: 'field-label', text: 'Write scope' }), scopeArea),
      h('label', { class: 'field span-2' }, h('span', { class: 'field-label', text: 'Read scope' }), scopeReadArea),
      h('label', { class: 'field span-2' }, h('span', { class: 'field-label', text: 'Acceptance' }), acceptanceArea),
      h('label', { class: 'field span-2' }, h('span', { class: 'field-label', text: 'Labels' }), labelsHost),
      h('label', { class: 'field span-2' }, h('span', { class: 'field-label', text: 'Decision note' }), noteInput)));

  openModal({
    title: 'Accept ' + entry.id,
    body: body,
    footer: [
      h('button', { class: 'btn', type: 'button', text: 'Cancel', on: { click: () => closeModal() } }),
      h('button', {
        class: 'btn btn-primary', type: 'button', text: 'Accept and create task',
        on: {
          click: async () => {
            const task = {};
            const id = idInput.value.trim();
            if (id) task.id = id;
            if (ownerInput.value.trim()) task.owner = ownerInput.value.trim();
            if (packageInput.value.trim()) task.package = packageInput.value.trim();
            if (complexityInput.value) task.complexity = Number(complexityInput.value);
            if (estimateInput.value) task.estimate_hours = Number(estimateInput.value);
            const scope = scopeArea.value.split('\n').map((line) => line.trim()).filter(Boolean);
            if (scope.length) task.scope_write = scope;
            const readScope = scopeReadArea.value.split('\n').map((line) => line.trim()).filter(Boolean);
            if (readScope.length) task.scope_read = readScope;
            const acceptance = acceptanceArea.value.split('\n').map((line) => line.trim()).filter(Boolean);
            if (acceptance.length) task.acceptance = acceptance;
            const gates = gatesInput.value.split(/[,\n]/).map((part) => part.trim()).filter(Boolean);
            if (gates.length) task.gates = gates;
            const selectedLabels = [];
            for (const box of labelsHost.querySelectorAll('[data-accept-label]')) {
              if (box.checked) selectedLabels.push(box.getAttribute('data-accept-label'));
            }
            if (selectedLabels.length) task.labels = selectedLabels;
            /* the backend reads the structure from task; stage also goes top-level for compatibility */
            task.stage = stageSelect.value;
            if (!task.title) task.title = entry.title;
            if (!task.goal) task.goal = entry.description || entry.title;
            const payload = {
              stage: stageSelect.value,
              template: templateSelect.value || null,
              note: noteInput.value.trim(),
              by: 'owner',
              task: task
            };
            try {
              const result = await api('/api/intake/' + encodeURIComponent(entry.id) + '/accept', { method: 'POST', body: payload });
              closeModal();
              await Promise.all([loadIntake(), loadSnapshot()]);
              renderView();
              toast('Created task ' + (result.task && result.task.id ? result.task.id : ''), 'ok');
              if (result.task && result.task.id) openTask(result.task.id);
            } catch (err) {
              errorBox.replaceChildren(errorCallout(err));
            }
          }
        }
      })
    ]
  });
}

/* ---------- reject ---------- */

function openRejectModal(entry) {
  if (!canWrite()) return;
  const errorBox = h('div');
  const noteArea = h('textarea', { class: 'textarea', rows: '3', placeholder: 'Why is this rejected? (required)', 'data-autofocus': '1' });
  const body = h('div', { class: 'col', style: { gap: '10px' } },
    errorBox,
    h('p', { class: 'hint', text: 'Rejecting "' + entry.title + '" keeps the reason in the intake history.' }),
    h('label', { class: 'field' }, h('span', { class: 'field-label', text: 'Reason' }), noteArea));
  openModal({
    title: 'Reject ' + entry.id,
    body: body,
    footer: [
      h('button', { class: 'btn', type: 'button', text: 'Cancel', on: { click: () => closeModal() } }),
      h('button', {
        class: 'btn btn-danger', type: 'button', text: 'Reject proposal',
        on: {
          click: async () => {
            if (!noteArea.value.trim()) {
              errorBox.replaceChildren(errorCallout(new ApiError('A rejection needs a reason.', 400, null)));
              return;
            }
            try {
              await api('/api/intake/' + encodeURIComponent(entry.id) + '/reject', {
                method: 'POST',
                body: { note: noteArea.value.trim(), by: 'owner' }
              });
              closeModal();
              await loadIntake();
              renderView();
              toast('Proposal rejected', 'ok');
            } catch (err) {
              errorBox.replaceChildren(errorCallout(err));
            }
          }
        }
      })
    ]
  });
  focusSoon(noteArea);
}

/* =========================================================================
   2.3 — Task templates: plan editor, save-as-template and settings list
   ========================================================================= */

function buildOwnerInput(value) {
  return h('input', { class: 'input', type: 'text', placeholder: 'optional owner', value: value || '' });
}

function labelCheckboxHost(task, templateLabels) {
  const host = h('div', { class: 'editor-labels', 'aria-label': 'Labels' });
  const selected = (task && Array.isArray(task.labels)) ? task.labels.slice()
    : (Array.isArray(templateLabels) ? templateLabels.slice() : []);
  const labels = settingsLabels();
  const groups = settingsGroups();
  if (!labels.length) host.appendChild(h('span', { class: 'hint', text: 'No labels defined in Settings.' }));
  for (const group of groups) {
    const inGroup = labels.filter((label) => (groups.indexOf(label.group) !== -1 ? label.group : 'custom') === group);
    if (!inGroup.length) continue;
    host.appendChild(h('span', { class: 'props-label-group', text: group }));
    for (const label of inGroup) {
      host.appendChild(h('label', { class: 'checkbox' },
        h('input', { type: 'checkbox', value: label.id, checked: selected.indexOf(label.id) !== -1 }),
        labelChip(label)));
    }
  }
  return host;
}



/* ---------- save an existing task as a template ---------- */

function openSaveTemplateModal(taskId) {
  if (!canWrite()) return;
  const task = taskById(taskId);
  if (!task) { toast('Unknown task', 'error'); return; }
  const idInput = h('input', {
    class: 'input', type: 'text', placeholder: 'review-task',
    value: taskId.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, ''), 'data-autofocus': '1'
  });
  const nameInput = h('input', { class: 'input', type: 'text', placeholder: 'Template name', value: 'From ' + taskId });
  const errorBox = h('div');
  const body = h('div', { class: 'plan-editor' }, errorBox,
    h('p', { class: 'hint', text: 'Saves the task shape (scope, acceptance, gates, complexity, labels, estimate, package, owner) to templates/tasks/<id>.json.' }),
    h('div', { class: 'form-grid' },
      h('label', { class: 'field' },
        h('span', { class: 'field-label', text: 'Template id' }), idInput,
        h('span', { class: 'field-help', text: 'Lowercase letters, digits and dashes.' })),
      h('label', { class: 'field' },
        h('span', { class: 'field-label', text: 'Name' }), nameInput)));
  openModal({
    title: 'Save ' + taskId + ' as a template',
    body: body,
    footer: [
      h('button', { class: 'btn', type: 'button', text: 'Cancel', on: { click: () => closeModal() } }),
      h('button', {
        class: 'btn btn-primary', type: 'button', text: 'Save template',
        on: {
          click: async () => {
            const id = idInput.value.trim();
            if (!/^[a-z][a-z0-9-]{0,40}$/.test(id)) {
              errorBox.replaceChildren(errorCallout(new ApiError('Template id must be lowercase (a-z, 0-9, -).', 400, null)));
              return;
            }
            try {
              await api('/api/task-templates', {
                method: 'POST',
                body: { from_task: taskId, id: id, name: nameInput.value.trim() || undefined }
              });
              closeModal();
              await loadTaskTemplates();
              toast('Template ' + id + ' saved', 'ok');
              renderView();
            } catch (err) {
              errorBox.replaceChildren(errorCallout(err));
            }
          }
        }
      })
    ]
  });
  focusSoon(idInput);
}

/* ---------- Settings: task templates ---------- */

function renderSettingsTemplates(ui, config) {
  const templates = state.templates;
  const card = h('section', { class: 'card-panel settings-section' },
    h('div', { class: 'panel-head' },
      h('div', { class: 'row' },
        h('span', { class: 'panel-title', text: 'Task templates' }),
        templates ? h('span', { class: 'pill', text: String(templates.length) }) : null),
      h('span', { class: 'hint', text: 'Committed in templates/tasks/; used by the plan editor and intake accept.' })),
    h('div', { class: 'panel-body' }));

  const body = card.querySelector('.panel-body');
  if (!state.templatesLoaded && !state.templatesError) {
    body.appendChild(loadingRow('Loading templates…'));
    return card;
  }
  if (state.templatesError) {
    body.appendChild(errorCallout(state.templatesError));
    return card;
  }
  if (!templates || !templates.length) {
    body.appendChild(h('div', { class: 'hint', text: 'No templates yet. Save one from a task in the Plan view.' }));
    return card;
  }
  for (const template of templates) {
    body.appendChild(h('div', { class: 'template-row' },
      h('div', { class: 'template-main' },
        h('div', { class: 'template-name', text: template.name || template.id }),
        h('div', { class: 'template-id', text: template.id })),
      templateChips(template),
      h('div', { class: 'template-actions' },
        h('button', {
          class: 'btn btn-sm btn-danger', type: 'button', text: 'Delete',
          disabled: !canWrite(),
          title: canWrite() ? 'DELETE /api/task-templates/' + template.id : 'The dashboard is read-only',
          on: { click: () => deleteTemplate(template.id) }
        }))));
  }
  return card;
}

async function deleteTemplate(templateId) {
  if (!canWrite()) return;
  const confirmed = await confirmDialog({
    title: 'Delete template "' + templateId + '"?',
    message: 'The template file is removed from templates/tasks/. Existing tasks are untouched.',
    confirmLabel: 'Delete template'
  });
  if (!confirmed) return;
  try {
    await api('/api/task-templates/' + encodeURIComponent(templateId), { method: 'DELETE' });
    await loadTaskTemplates();
    toast('Template deleted', 'ok');
    renderView();
  } catch (err) {
    toast('Delete failed: ' + describeError(err), 'error');
  }
}

/* =========================================================================
   2.4 — Assistant view
   ========================================================================= */

function renderAssistant() {
  const wrapper = h('div', { class: 'assistant-view' });
  dom.view.appendChild(wrapper);
  const conversations = assistantConversations();
  const active = state.assistantActive;
  const detail = activeAssistantDetail();

  wrapper.appendChild(h('div', { class: 'view-head' },
    h('div', {},
      h('h1', { class: 'view-title', text: 'Assistant' }),
      h('p', { class: 'view-sub', text: conversations.length + ' conversation(s) · questions are answered by the configured provider in the background' })),
    h('div', { class: 'view-actions' },
      canWrite() ? h('button', {
        class: 'btn btn-sm btn-primary', type: 'button', text: 'New conversation',
        on: {
          click: () => {
            state.assistantActive = null;
            state.assistantDetail = null;
            state.assistantDraft = '';
            state.assistantError = null;
            state.assistantApplyResult = null;
            renderView();
            focusAssistantInput();
          }
        }
      }) : null,
      h('button', {
        class: 'btn btn-sm', type: 'button', text: 'Refresh',
        on: {
          click: async () => {
            await loadAssistantList();
            ensureAssistantActive();
            if (state.assistantActive) await loadAssistantConversation(state.assistantActive, true);
            renderView();
          }
        }
      }))));

  const grid = h('div', { class: 'assistant' });
  wrapper.appendChild(grid);

  /* sidebar */
  const sidebar = h('aside', { class: 'assistant-sidebar' });
  const listCard = h('section', { class: 'card-panel assistant-side-card' },
    h('div', { class: 'panel-head' },
      h('span', { class: 'panel-title', text: 'Conversations' }),
      h('span', { class: 'pill', text: String(conversations.length) })),
    h('div', { class: 'assistant-conv-list' }));
  const listHost = listCard.querySelector('.assistant-conv-list');
  if (!state.assistantLoaded && !conversations.length) {
    listHost.appendChild(loadingRow('Loading conversations…'));
  } else if (!conversations.length) {
    listHost.appendChild(h('div', { class: 'hint', style: { padding: '8px' }, text: 'No conversations yet. Ask the first question.' }));
  } else {
    for (const conversation of conversations) {
      const pending = Boolean(conversation.pending);
      listHost.appendChild(h('div', { class: 'assistant-conv' + (conversation.id === active ? ' is-active' : '') },
        h('button', {
          class: 'assistant-conv', type: 'button',
          style: { padding: '0', background: 'none' },
          title: conversation.title,
          on: { click: () => openAssistantConversation(conversation.id) }
        },
          h('span', { class: 'assistant-conv-title', text: conversation.title || conversation.id }),
          h('span', { class: 'assistant-conv-meta' },
            h('span', { text: (conversation.messages || 0) + ' msg' }),
            h('span', { text: relTime(conversation.updated) }),
            pending ? h('span', { class: 'badge bg-blue st-blue', text: 'thinking' }) : null)),
        h('div', { class: 'row', style: { gap: '2px', marginTop: '2px' } },
          h('button', {
            class: 'btn btn-sm btn-ghost', type: 'button', text: 'Delete',
            disabled: !canWrite(),
            on: {
              click: (event) => {
                event.stopPropagation();
                deleteAssistantConversation(conversation.id);
              }
            }
          }))));
    }
  }
  sidebar.appendChild(listCard);
  grid.appendChild(sidebar);

  /* main */
  const main = h('section', { class: 'assistant-main' });
  grid.appendChild(main);

  if (state.assistantError) {
    main.appendChild(h('div', { class: 'assistant-error' }, errorCallout(state.assistantError)));
  }

  if (!active) {
    main.appendChild(h('div', { class: 'assistant-head' },
      h('span', { class: 'panel-title', text: 'New conversation' })));
    main.appendChild(h('div', { class: 'assistant-empty' },
      emptyState('Ask the project a question',
        'The assistant reads the board, runs, reviews and docs, then answers in the configured provider session. It never writes by itself — proposals need your confirmation.',
        null)));
    main.appendChild(renderAssistantComposer());
    return;
  }

  main.appendChild(h('div', { class: 'assistant-head' },
    h('span', { class: 'panel-title', text: (detail && detail.title) || 'Conversation' }),
    h('span', { class: 'session-id', text: active }),
    detail && detail.updated ? h('span', { class: 'hint', text: 'updated ' + relTime(detail.updated) }) : null,
    h('div', { style: { marginLeft: 'auto', display: 'flex', gap: '4px' } },
      canWrite() ? h('button', {
        class: 'btn btn-sm btn-danger', type: 'button', text: 'Delete',
        on: { click: () => deleteAssistantConversation(active) }
      }) : null)));

  if (state.assistantLoading && !detail) {
    main.appendChild(h('div', { class: 'assistant-empty' }, loadingRow('Loading the conversation…')));
    return;
  }

  const transcript = h('div', { class: 'assistant-transcript' });
  const messages = (detail && detail.messages) || [];
  if (!messages.length) {
    transcript.appendChild(h('div', { class: 'assistant-empty', text: 'Ask the first question below.' }));
  }
  messages.forEach((message, messageIndex) => {
    const isUser = message.role === 'user';
    const bubble = h('div', { class: 'assistant-bubble ' + (isUser ? 'is-user' : 'is-assistant') });
    if (!isUser) {
      bubble.appendChild(h('div', { class: 'md' }, mdFragment(message.content || '', { linkBase: '' })));
      const proposals = (message.proposals || []).filter((proposal, proposalIndex) => !proposalDismissed(messageIndex, proposalIndex));
      if (proposals.length) {
        const host = h('div', { class: 'assistant-proposals' });
        (message.proposals || []).forEach((proposal, proposalIndex) => {
          if (proposalDismissed(messageIndex, proposalIndex)) return;
          const tone = assistantProposalKindTone(proposal.kind);
          host.appendChild(h('div', { class: 'proposal-card' },
            h('div', { class: 'proposal-head' },
              h('span', { class: 'badge bg-' + tone + ' st-' + tone }, h('span', { class: 'dot' }), proposal.kind),
              h('span', { class: 'proposal-title', text: proposal.title || '' })),
            proposal.reason ? h('div', { class: 'proposal-reason', text: proposal.reason }) : null,
            h('pre', { class: 'proposal-payload', text: JSON.stringify(proposal.payload || {}, null, 2) }),
            h('div', { class: 'proposal-actions' },
              h('button', {
                class: 'btn btn-sm btn-primary', type: 'button', text: 'Apply',
                disabled: !canWrite() || Boolean(state.assistantApplying),
                on: { click: () => applyAssistantProposal(proposal, messageIndex, proposalIndex) }
              }),
              h('button', {
                class: 'btn btn-sm btn-ghost', type: 'button', text: 'Dismiss',
                on: { click: () => dismissAssistantProposal(messageIndex, proposalIndex) }
              }))));
        });
        bubble.appendChild(host);
      }
    } else {
      bubble.appendChild(h('div', { class: 'md' }, mdFragment(message.content || '', { linkBase: '' })));
    }
    bubble.appendChild(h('div', { class: 'assistant-bubble-meta' },
      h('span', { text: message.role }),
      h('span', { text: relTime(message.at) }),
      message.status ? h('span', { class: 'chip', text: message.status }) : null));
    transcript.appendChild(bubble);
  });

  if (detail && detail.pending) {
    const pending = detail.pending;
    transcript.appendChild(h('div', { class: 'assistant-pending' },
      h('span', { class: 'spinner' }),
      h('span', { text: 'Thinking… (' + (pending.status || 'running') + ')' }),
      h('span', { class: 'session-id', text: pending.session || '' }),
      canWrite() ? h('button', {
        class: 'btn btn-sm btn-ghost', type: 'button', text: 'Cancel',
        on: { click: () => cancelAssistantAnswer() }
      }) : null));
  }

  main.appendChild(transcript);

  if (state.assistantApplyResult) {
    const applied = state.assistantApplyResult;
    main.appendChild(h('div', { class: 'assistant-apply-result' },
      h('span', { class: 'badge bg-green st-green', text: 'applied' }),
      ' ' + ((applied.proposal && (applied.proposal.title || applied.proposal.kind)) || 'proposal'),
      h('span', { class: 'hint', text: ' at ' + relTime(applied.at) })));
  }

  main.appendChild(renderAssistantComposer());

  focusSoonIfRequested();
  if (transcript) {
    window.setTimeout(() => { transcript.scrollTop = transcript.scrollHeight; }, 0);
  }
}

function renderAssistantComposer() {
  const detail = activeAssistantDetail();
  const pending = detail && detail.pending;
  const readOnly = !canWrite();
  const input = h('textarea', {
    class: 'textarea', rows: '3',
    placeholder: readOnly ? 'The dashboard is read-only.' : 'Ask about tasks, gates, reviews, docs… (Ctrl/Cmd+Enter sends)',
    value: assistantDraft(),
    disabled: readOnly || Boolean(pending) || state.assistantSending,
    'data-fkey': 'assistant-input',
    'aria-label': 'Question for the assistant',
    on: {
      input: (event) => { state.assistantDraft = event.target.value; },
      keydown: (event) => {
        if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
          event.preventDefault();
          sendAssistantMessage(event.target.value);
        }
      }
    }
  });
  const composer = h('div', { class: 'assistant-composer' }, input);
  const foot = h('div', { class: 'assistant-composer-foot' },
    h('span', { class: 'hint', text: readOnly
      ? 'Read-only dashboard: questions are disabled.'
      : 'Enter adds a newline · Ctrl/Cmd+Enter sends · conversations stay in the local runtime folder.' }),
    h('button', {
      class: 'btn btn-primary', type: 'button',
      text: state.assistantSending ? 'Sending…' : 'Send',
      disabled: readOnly || Boolean(pending) || state.assistantSending,
      on: { click: () => sendAssistantMessage(input.value) }
    }));
  composer.appendChild(foot);
  return composer;
}

function focusAssistantInput() {
  state.focusAssistantInput = true;
  renderView();
}

function focusSoonIfRequested() {
  if (!state.focusAssistantInput) return;
  state.focusAssistantInput = false;
  const input = document.querySelector('[data-fkey="assistant-input"]');
  focusSoon(input);
}

/* =========================================================================
   2.4 — Automations view
   ========================================================================= */

function automationActionLabel(action) {
  if (!action) return 'Action';
  if (action.type === 'state') return 'Set ' + (action.status || 'status');
  if (action.type === 'session') return 'Start ' + (action.role || 'worker') + ' session';
  if (action.type === 'open') return 'Open';
  if (action.type === 'note') return 'Copy note';
  return action.type;
}

function automationActionChip(action) {
  const type = action && action.type;
  if (type === 'state') return 'state → ' + (action.status || '?');
  if (type === 'session') return 'session → ' + (action.role || 'worker');
  if (type === 'open') return 'open';
  if (type === 'note') return 'note';
  return type;
}

function renderAutomations() {
  const view = h('div', { class: 'automations' });
  dom.view.appendChild(view);
  const automations = state.automations;
  const rules = automationRuleList();
  const enabledCount = rules.filter((rule) => rule.enabled !== false).length;

  view.appendChild(h('div', { class: 'view-head' },
    h('div', {},
      h('h1', { class: 'view-title', text: 'Automations' }),
      h('p', { class: 'view-sub', text: rules.length + ' rule(s) · ' + enabledCount + ' enabled · dry run only, nothing executes automatically' })),
    h('div', { class: 'view-actions' },
      h('button', {
        class: 'btn btn-sm btn-primary', type: 'button',
        text: state.automationsRunning ? 'Running…' : 'Run dry run',
        disabled: state.automationsRunning || Boolean(state.automationsError && !automations),
        on: { click: () => runAutomations() }
      }),
      rules.length === 0 ? h('button', {
        class: 'btn btn-sm', type: 'button', text: 'Load example',
        disabled: !canWrite(),
        on: { click: () => saveAutomations(loadExampleAutomations()) }
      }) : null,
      h('button', {
        class: 'btn btn-sm', type: 'button', text: 'Refresh',
        on: { click: () => loadAutomations().then(() => renderView()) }
      }))));

  if (!state.automationsLoaded && !automations) {
    if (state.automationsError) {
      view.appendChild(errorCallout(state.automationsError));
      view.appendChild(h('div', { style: { marginTop: '10px' } },
        h('button', { class: 'btn', type: 'button', text: 'Retry', on: { click: () => loadAutomations().then(() => renderView()) } })));
    } else {
      view.appendChild(loadingRow('Reading automations.json…'));
    }
    return;
  }
  if (state.automationsError) view.appendChild(errorCallout(state.automationsError));
  if (state.automationsEditorError) view.appendChild(errorCallout(state.automationsEditorError));
  if (automations && (automations.errors || []).length) {
    const box = h('div', { class: 'callout callout-warn' },
      h('div', { class: 'callout-stack' },
        h('div', { text: 'automations.json has validation problems (fix them in the editor):' }),
        h('ul', {}, automations.errors.map((message) => h('li', { text: message })))));
    view.appendChild(box);
  }

  /* rules */
  const rulesCard = h('section', { class: 'card-panel' },
    h('div', { class: 'panel-head' },
      h('div', { class: 'row' },
        h('span', { class: 'panel-title', text: 'Rules' }),
        h('span', { class: 'pill', text: String(rules.length) })),
      h('span', { class: 'hint', text: 'Committed in automations.json; toggling saves the file.' })),
    h('div', { class: 'panel-body' }));
  if (!rules.length) {
    rulesCard.querySelector('.panel-body').appendChild(emptyState('No automation rules yet',
      'Rules turn project state into suggestions. Load the example set or edit automations.json below.',
      canWrite() ? h('button', {
        class: 'btn btn-primary', type: 'button', text: 'Load example rules',
        disabled: !canWrite(),
        on: { click: () => saveAutomations(loadExampleAutomations()) }
      }) : null));
  } else {
    const list = h('div', { class: 'rule-list' });
    for (const rule of rules) {
      const when = rule.when || {};
      const actions = rule.actions || [];
      list.appendChild(h('div', { class: 'rule-card' },
        h('div', { class: 'rule-head' },
          h('label', { class: 'switch', title: 'Enable or disable this rule' },
            h('input', {
              type: 'checkbox', checked: rule.enabled !== false,
              disabled: !canWrite(),
              'aria-label': 'Enable rule ' + (rule.name || rule.id),
              on: { change: (event) => toggleAutomationRule(rule.id, event.target.checked) }
            })),
          h('span', { class: 'rule-name', text: rule.name || rule.id }),
          h('span', { class: 'rule-id', text: rule.id }),
          rule.description ? h('span', { class: 'hint', text: rule.description }) : null,
          h('span', { class: 'pill', style: { marginLeft: 'auto' }, text: rule.enabled === false ? 'disabled' : 'enabled' })),
        h('div', { class: 'rule-chips' },
          h('span', { class: 'chip kind-idea', title: 'Event kind', text: 'when: ' + (when.kind || '?') }),
          actions.map((action) => h('span', { class: 'chip', title: 'Action', text: '→ ' + automationActionChip(action) })))));
    }
    rulesCard.querySelector('.panel-body').appendChild(list);
  }
  view.appendChild(rulesCard);

  /* dry-run results */
  const run = state.automationsRun;
  const resultsCard = h('section', { class: 'card-panel' },
    h('div', { class: 'panel-head' },
      h('div', { class: 'row' },
        h('span', { class: 'panel-title', text: 'Dry run' }),
        run ? h('span', { class: 'pill', text: run.total + ' match(es)' }) : null),
      h('span', { class: 'hint', text: 'Suggestions only — apply one explicitly.' })),
    h('div', { class: 'panel-body' }));
  const resultsHost = resultsCard.querySelector('.panel-body');
  if (!run) {
    resultsHost.appendChild(h('p', { class: 'dry-run-note', text: 'Run the dry run to see which rules match right now. No action is executed.' }));
  } else if (!run.matches || !run.matches.length) {
    resultsHost.appendChild(h('div', { class: 'dry-run-note' },
      h('span', { class: 'badge bg-green st-green', text: 'no matches' }),
      h('span', { text: 'Nothing to do right now. Ran at ' + relTime(run.generated_at) + '.' })));
  } else {
    resultsHost.appendChild(h('p', { class: 'dry-run-note' },
      h('span', { class: 'badge bg-amber st-amber', text: run.total + ' suggestion(s)' }),
      h('span', { text: 'dry run at ' + relTime(run.generated_at) + ' · grouped by rule' })));
    const byRule = new Map();
    for (const match of run.matches) {
      if (!byRule.has(match.rule)) byRule.set(match.rule, []);
      byRule.get(match.rule).push(match);
    }
    for (const [ruleId, matches] of byRule) {
      const group = h('div', { class: 'match-group', style: { marginTop: '8px' } },
        h('div', { class: 'match-head' },
          h('span', { class: 'rule-name', text: (matches[0] && matches[0].name) || ruleId }),
          h('span', { class: 'rule-id', text: ruleId }),
          h('span', { class: 'pill', text: matches.length + ' match(es)' }),
          h('span', { class: 'hint', text: 'suggestions from actions[]' })));
      for (const match of matches) {
        const row = h('div', { class: 'queue-row', style: { alignItems: 'flex-start', cursor: 'default' } },
          h('div', { class: 'queue-main' },
            h('div', { class: 'queue-title', text: automationEventText(match.event) }),
            h('div', { class: 'queue-sub', text: 'key: ' + match.key })));
        const actions = h('div', { class: 'match-actions' });
        for (const action of match.actions || []) {
          actions.appendChild(h('button', {
            class: 'btn btn-sm' + (action.type === 'state' ? ' btn-primary' : ''),
            type: 'button', text: automationActionLabel(action),
            disabled: !canWrite() && action.type !== 'open',
            title: action.type === 'open' ? 'Open the related view' : 'Confirm, then run the existing API action',
            on: { click: () => applyAutomationAction(match, action) }
          }));
        }
        row.appendChild(actions);
        group.appendChild(row);
      }
      resultsHost.appendChild(group);
    }
  }
  view.appendChild(resultsCard);

  /* JSON editor */
  const editorCard = h('section', { class: 'card-panel automation-editor' },
    h('div', { class: 'panel-head' },
      h('div', { class: 'row' },
        h('span', { class: 'panel-title', text: 'automations.json' }),
        h('span', { class: 'pill mono', text: 'project file' })),
      h('div', { class: 'row' },
        h('button', {
          class: 'btn btn-sm', type: 'button', text: 'Reset',
          on: { click: () => { state.automationsEditor = JSON.stringify(automations && automations.automations ? automations.automations : { version: 1, rules: [] }, null, 2); state.automationsEditorError = null; renderView(); } }
        }),
        h('button', {
          class: 'btn btn-sm btn-primary', type: 'button', text: 'Save',
          disabled: !canWrite(),
          on: {
            click: (event) => {
              const area = document.getElementById('automations-editor');
              saveAutomationsEditor(area ? area.value : state.automationsEditor);
            }
          }
        }))),
    h('div', { class: 'panel-body' },
      h('textarea', {
        id: 'automations-editor', value: state.automationsEditor,
        'aria-label': 'automations.json editor', spellcheck: 'false',
        on: { input: (event) => { state.automationsEditor = event.target.value; } }
      }),
      h('p', { class: 'hint', style: { marginTop: '6px' },
        text: 'The whole file is validated on save. Known kinds: ' + automationKinds().join(', ') + '.' })));
  view.appendChild(editorCard);
}

/* =========================================================================
   2.4 — GitHub view (read-only)
   ========================================================================= */

function renderGithub() {
  const view = h('div', { class: 'github' });
  dom.view.appendChild(view);
  const data = state.github;

  view.appendChild(h('div', { class: 'view-head' },
    h('div', {},
      h('h1', { class: 'view-title', text: 'GitHub' }),
      h('p', { class: 'view-sub', text: data && data.available
        ? (data.repo || 'repository') + ' · read-only via the gh CLI'
        : 'Pull requests and CI, read-only via the gh CLI' })),
    h('div', { class: 'view-actions' },
      h('button', {
        class: 'btn btn-sm', type: 'button', text: 'Refresh',
        disabled: state.githubLoading,
        title: 'GET /api/github?force=1',
        on: { click: () => loadGithub(true) }
      }))));

  if (state.githubLoading && !data) {
    view.appendChild(loadingRow('Asking gh for pull requests and runs…'));
    return;
  }
  if (state.githubError) {
    view.appendChild(errorCallout(state.githubError));
    return;
  }
  if (!data) {
    view.appendChild(loadingRow('Loading GitHub status…'));
    return;
  }

  if (!data.available) {
    const card = h('div', { class: 'card-panel panel-pad github-unavailable' });
    card.appendChild(h('div', { class: 'row-wrap' },
      h('span', { class: 'badge bg-neutral st-neutral', text: 'unavailable' }),
      h('span', { class: 'text-sm muted', text: data.reason || 'GitHub is not configured for this project.' })));
    card.appendChild(h('p', { class: 'hint', text: 'The panel is read-only and never changes the project. It becomes available when the repository has a GitHub remote and the gh CLI is installed and authenticated.' }));
    const hints = h('div', { class: 'github-hints' });
    hints.appendChild(h('div', { class: 'github-hint' },
      h('span', { text: '1. Add a GitHub origin:' }),
      h('code', { text: 'git remote add origin git@github.com:<owner>/<repo>.git' })));
    hints.appendChild(h('div', { class: 'github-hint' },
      h('span', { text: '2. Install the GitHub CLI:' }),
      h('code', { text: 'brew install gh' })));
    hints.appendChild(h('div', { class: 'github-hint' },
      h('span', { text: '3. Authenticate:' }),
      h('code', { text: 'gh auth login' })));
    hints.appendChild(h('div', { class: 'github-hint' },
      h('span', { text: '4. Refresh this panel.' })));
    card.appendChild(hints);
    card.appendChild(h('div', { class: 'row-wrap' },
      h('button', { class: 'btn btn-sm', type: 'button', text: 'Refresh', on: { click: () => loadGithub(true) } }),
      data.repo ? h('span', { class: 'hint', text: 'remote: ' + data.repo }) : null));
    view.appendChild(card);
    return;
  }

  const counts = data.counts || { prs: 0, runs: 0, failing_checks: 0 };
  view.appendChild(h('div', { class: 'tile-row' },
    statTile('Repository', data.repo || '—', { tone: 'tile-blue', sub: data.remote || '' }),
    statTile('Open PRs', counts.prs || 0, { tone: 'tile-accent', sub: 'pull requests' }),
    statTile('Failing checks', counts.failing_checks || 0, { tone: counts.failing_checks ? 'tile-red' : 'tile-green', sub: 'PRs with failing CI' }),
    statTile('Recent runs', counts.runs || 0, { tone: 'tile-violet', sub: 'workflow runs' })));

  /* PRs */
  const prCard = h('section', { class: 'card-panel' },
    h('div', { class: 'panel-head' },
      h('div', { class: 'row' },
        h('span', { class: 'panel-title', text: 'Open pull requests' }),
        h('span', { class: 'pill', text: String((data.prs || []).length) })),
      h('span', { class: 'hint', text: 'Checks come from GitHub’s status rollup.' })),
    h('div', { class: 'panel-body' }));
  const prs = data.prs || [];
  if (!prs.length) {
    prCard.querySelector('.panel-body').appendChild(h('div', { class: 'hint', text: 'No open pull requests.' }));
  } else {
    const grid = h('div', { class: 'pr-grid' });
    for (const pr of prs) {
      grid.appendChild(h('a', {
        class: 'pr-card', href: pr.url || '#', target: '_blank', rel: 'noopener noreferrer',
        title: pr.url || '',
        style: { color: 'inherit', textDecoration: 'none' }
      },
        h('div', { class: 'row-wrap' },
          h('span', { class: 'pr-title', text: '#' + pr.number + ' · ' + (pr.title || '') }),
          pr.isDraft ? h('span', { class: 'pill', text: 'draft' }) : null),
        h('div', { class: 'pr-meta' },
          githubCheckBadge(pr.checks),
          h('span', { class: 'mono', text: pr.headRefName || '' }),
          pr.updatedAt ? h('span', { text: 'updated ' + relTime(pr.updatedAt) }) : null)));
    }
    prCard.querySelector('.panel-body').appendChild(grid);
  }
  view.appendChild(prCard);

  /* runs */
  const runsCard = h('section', { class: 'card-panel' },
    h('div', { class: 'panel-head' },
      h('div', { class: 'row' },
        h('span', { class: 'panel-title', text: 'Recent workflow runs' }),
        h('span', { class: 'pill', text: String((data.runs || []).length) })),
      h('span', { class: 'hint', text: 'Read-only snapshot from gh run list.' })),
    h('div', { class: 'panel-body' }));
  const runs = data.runs || [];
  if (!runs.length) {
    runsCard.querySelector('.panel-body').appendChild(h('div', { class: 'hint', text: 'No workflow runs reported.' }));
  } else {
    const table = h('table', { class: 'github-runs' });
    const head = h('tr');
    for (const heading of ['Workflow', 'Status', 'Conclusion', 'Branch', 'Event', 'When', '']) head.appendChild(h('th', { text: heading }));
    table.appendChild(h('thead', {}, head));
    const body = h('tbody');
    for (const run of runs) {
      const tone = githubRunTone(run);
      body.appendChild(h('tr', {},
        h('td', { text: run.name || 'workflow' }),
        h('td', { text: run.status || '—' }),
        h('td', {}, h('span', { class: 'ci-badge ci-' + tone, text: run.conclusion || run.status || '—' })),
        h('td', { class: 'mono', text: run.headBranch || '—' }),
        h('td', { text: run.event || '—' }),
        h('td', { text: run.createdAt ? relTime(run.createdAt) : '—' }),
        h('td', {}, run.url ? h('a', { href: run.url, target: '_blank', rel: 'noopener noreferrer', text: 'Open' }) : null)));
    }
    table.appendChild(body);
    runsCard.querySelector('.panel-body').appendChild(table);
  }
  view.appendChild(runsCard);

  /* task mapping */
  const mapped = Object.keys(data.tasks || {});
  const taskCard = h('section', { class: 'card-panel' },
    h('div', { class: 'panel-head' },
      h('div', { class: 'row' },
        h('span', { class: 'panel-title', text: 'Task mapping' }),
        h('span', { class: 'pill', text: String(mapped.length) })),
      h('span', { class: 'hint', text: 'Tasks with a branch, PR or CI run. Click a chip to open the task.' })),
    h('div', { class: 'panel-body' }));
  if (!mapped.length) {
    taskCard.querySelector('.panel-body').appendChild(h('div', { class: 'hint', text: 'No task branch is linked to a pull request or run yet.' }));
  } else {
    const host = h('div', { class: 'task-map' });
    for (const taskId of mapped) {
      const entry = data.tasks[taskId];
      const pr = entry.pr;
      const ci = entry.ci;
      host.appendChild(h('button', {
        class: 'chip chip-link', type: 'button',
        title: (entry.branch || '') + (pr ? ' · PR #' + pr.number : '') + (ci ? ' · CI ' + (ci.conclusion || ci.status) : ''),
        on: { click: () => openTask(taskId) }
      },
        h('span', { class: 'mono', text: taskId }),
        pr ? h('span', { class: 'ci-badge ci-' + (pr.checks || 'none'), text: 'PR #' + pr.number }) : null,
        ci ? h('span', { class: 'ci-badge ci-' + githubRunTone(ci), text: 'CI ' + (ci.conclusion || ci.status || '') }) : null,
        !pr && !ci ? h('span', { class: 'hint', text: 'branch only' }) : null));
    }
    taskCard.querySelector('.panel-body').appendChild(host);
  }
  view.appendChild(taskCard);
  view.appendChild(h('p', { class: 'hint', style: { marginTop: '8px' }, text: 'GitHub is read-only: Polier never posts, merges or reruns anything.' }));
}

/* =========================================================================
   2.4 — Bulk operations and the command palette
   ========================================================================= */

/* ---------- bulk selection ---------- */

function bulkState() {
  if (!state.bulk) state.bulk = { selected: [], status: 'blocked', note: '', labels: [], estimate: '', labelsOpen: false, busy: false };
  return state.bulk;
}

function bulkSelected() {
  return bulkState().selected;
}

function bulkIsSelected(taskId) {
  return bulkSelected().indexOf(taskId) !== -1;
}

function toggleBulkTask(taskId, checked) {
  const bulk = bulkState();
  if (checked) {
    if (bulk.selected.indexOf(taskId) === -1) bulk.selected.push(taskId);
  } else {
    bulk.selected = bulk.selected.filter((entry) => entry !== taskId);
  }
  renderView();
}

function selectAllVisibleBulk(checked) {
  const bulk = bulkState();
  if (checked) bulk.selected = visibleTasks().map((task) => task.id);
  else bulk.selected = [];
  renderView();
}

function clearBulkSelection() {
  bulkState().selected = [];
  renderView();
}

function bulkCheckbox(task) {
  if (!canWrite()) return null;
  return h('input', {
    class: 'bulk-check', type: 'checkbox', checked: bulkIsSelected(task.id),
    'aria-label': 'Select task ' + task.id,
    title: 'Select ' + task.id + ' for a bulk action',
    on: {
      click: (event) => event.stopPropagation(),
      change: (event) => { event.stopPropagation(); toggleBulkTask(task.id, event.target.checked); }
    }
  });
}

function renderBulkBar() {
  if (!canWrite()) return null;
  const bulk = bulkState();
  const visible = visibleTasks();
  const selected = bulk.selected.filter((taskId) => visible.some((task) => task.id === taskId));
  const allSelected = visible.length > 0 && visible.every((task) => bulk.selected.indexOf(task.id) !== -1);
  const disabled = !selected.length || bulk.busy;

  const bar = h('div', { class: 'bulk-bar' + (selected.length ? ' is-active' : '') });
  bar.appendChild(h('label', { class: 'checkbox', title: 'Select every task visible with the current filters' },
    h('input', {
      type: 'checkbox', checked: allSelected, 'aria-label': 'Select all visible tasks',
      on: { change: (event) => selectAllVisibleBulk(event.target.checked) }
    }),
    h('span', { class: 'bulk-count', text: selected.length ? selected.length + ' selected' : 'Select tasks' })));
  bar.appendChild(h('button', {
    class: 'btn btn-sm btn-ghost', type: 'button', text: 'Clear',
    disabled: !selected.length,
    on: { click: () => clearBulkSelection() }
  }));
  bar.appendChild(h('span', { class: 'bulk-divider' }));

  /* state */
  const statusSelect = h('select', { class: 'select', 'aria-label': 'Bulk status', disabled: disabled }, statusOrder().map((status) => {
    const option = h('option', { value: status, text: stMeta(status).label });
    if (bulk.status === status) option.selected = true;
    return option;
  }));
  statusSelect.value = bulk.status || 'blocked';
  statusSelect.addEventListener('change', (event) => { bulkState().status = event.target.value; });
  const noteInput = h('input', {
    class: 'input is-note', type: 'text', placeholder: 'note (required for rework/blocked/failed)',
    'aria-label': 'Bulk note', value: bulk.note || '',
    on: { input: (event) => { bulkState().note = event.target.value; } }
  });
  bar.appendChild(h('div', { class: 'bulk-group' },
    h('span', { class: 'hint', text: 'Status' }), statusSelect, noteInput,
    h('button', {
      class: 'btn btn-sm btn-primary', type: 'button', text: 'Apply',
      disabled: disabled,
      on: { click: () => runBulk('state', { status: bulkState().status, note: bulkState().note || undefined }) }
    })));

  bar.appendChild(h('span', { class: 'bulk-divider' }));
  bar.appendChild(h('div', { class: 'bulk-group' },
    h('button', {
      class: 'btn btn-sm', type: 'button', text: 'Claim', disabled: disabled,
      title: 'Claim the selected tasks', on: { click: () => runBulk('claim', {}) }
    }),
    h('button', {
      class: 'btn btn-sm', type: 'button', text: 'Release', disabled: disabled,
      title: 'Release the selected tasks', on: { click: () => runBulk('release', {}) }
    })));

  bar.appendChild(h('span', { class: 'bulk-divider' }));
  const labelsButton = h('button', {
    class: 'btn btn-sm', type: 'button',
    text: 'Labels' + (bulk.labels && bulk.labels.length ? ' (' + bulk.labels.length + ')' : ''),
    disabled: disabled,
    on: { click: () => { bulkState().labelsOpen = !bulkState().labelsOpen; renderView(); } }
  });
  bar.appendChild(h('div', { class: 'bulk-group' },
    labelsButton,
    h('button', {
      class: 'btn btn-sm', type: 'button', text: 'Apply labels', disabled: disabled,
      on: { click: () => runBulk('labels', { labels: bulkState().labels || [] }) }
    })));
  if (bulk.labelsOpen) {
    const labelHost = h('div', { class: 'bulk-group', style: { flexBasis: '100%' } });
    const labels = settingsLabels();
    if (!labels.length) labelHost.appendChild(h('span', { class: 'hint', text: 'No labels defined in Settings.' }));
    for (const label of labels) {
      labelHost.appendChild(h('label', { class: 'checkbox' },
        h('input', {
          type: 'checkbox', checked: (bulkState().labels || []).indexOf(label.id) !== -1,
          on: {
            change: (event) => {
              const current = (bulkState().labels || []).slice();
              const index = current.indexOf(label.id);
              if (event.target.checked && index === -1) current.push(label.id);
              if (!event.target.checked && index !== -1) current.splice(index, 1);
              bulkState().labels = current;
            }
          }
        }),
        labelChip(label)));
    }
    bar.appendChild(labelHost);
  }

  bar.appendChild(h('span', { class: 'bulk-divider' }));
  const estimateInput = h('input', {
    class: 'input is-estimate', type: 'number', min: '0', max: '10000', step: '0.5', placeholder: 'hours',
    'aria-label': 'Bulk estimate hours', value: bulk.estimate || '',
    on: { input: (event) => { bulkState().estimate = event.target.value; } }
  });
  bar.appendChild(h('div', { class: 'bulk-group' },
    estimateInput,
    h('button', {
      class: 'btn btn-sm', type: 'button', text: 'Apply estimate', disabled: disabled,
      on: {
        click: () => {
          const text = String(bulkState().estimate || '').trim();
          const value = text === '' ? null : Number(text);
          if (expandedNumberInvalid(text, value)) { toast('Enter a number for the estimate', 'warn'); return; }
          runBulk('estimate', { estimate_hours: value });
        }
      }
    })));
  if (bulk.busy) bar.appendChild(h('span', { class: 'hint', text: 'Working…' }));
  return bar;
}

function expandedNumberInvalid(text, value) {
  return text !== '' && (!isFinite(value) || value < 0);
}

async function runBulk(action, payload) {
  const bulk = bulkState();
  if (!bulk.selected.length) return;
  bulk.busy = true;
  renderView();
  try {
    const result = await api('/api/bulk', {
      method: 'POST',
      body: Object.assign({ action: action, tasks: bulk.selected.slice() }, payload || {})
    });
    const failures = (result.results || []).filter((entry) => !entry.ok);
    const message = 'Bulk ' + action + ': ' + (result.ok_count || 0) + ' applied, ' + (result.failed_count || 0) + ' failed' +
      (failures.length ? '\n' + failures.map((entry) => entry.task + ': ' + (entry.error || 'failed')).join('\n') : '');
    toast(message, failures.length ? 'warn' : 'ok', failures.length ? 9000 : 4000);
    bulk.selected = [];
    bulk.labelsOpen = false;
    await loadSnapshot();
    if (feature('worklog')) loadWorklog();
    renderHeader();
    renderView();
  } catch (err) {
    toast('Bulk action failed: ' + describeError(err), 'error');
  } finally {
    bulk.busy = false;
    renderView();
  }
}

/* ---------- command palette ---------- */

function paletteItems() {
  const items = [];
  for (const view of VIEWS) {
    if (view.feature && !feature(view.feature)) continue;
    items.push({
      id: 'view-' + view.key, group: 'Views', label: view.label, sub: '#' + view.key,
      run: () => navigate(view.key)
    });
  }
  if (canWrite()) items.push({
    id: 'action-new-task', group: 'Actions', label: 'New task', sub: 'plan editor',
    run: async () => {
      navigate('plan');
      await loadViewData('plan');
      await loadTaskTemplates();
      openTaskEditor(null);
    }
  });
  if (feature('intake') && canWrite()) {
    items.push({
      id: 'action-new-intake', group: 'Actions', label: 'New intake proposal', sub: 'intake',
      run: async () => {
        navigate('intake');
        await loadIntake();
        openNewIntakeModal();
      }
    });
  }
  if (feature('assistant') && canWrite()) {
    items.push({
      id: 'action-ask', group: 'Actions', label: 'Ask the assistant', sub: 'assistant',
      run: () => {
        navigate('assistant');
        state.focusAssistantInput = true;
        renderView();
      }
    });
  }
  if (feature('automations')) {
    items.push({
      id: 'action-automations', group: 'Actions', label: 'Run automations dry run', sub: 'automations',
      run: async () => {
        navigate('automations');
        await loadViewData('automations');
        runAutomations();
      }
    });
  }
  items.push({ id: 'action-refresh', group: 'Actions', label: 'Refresh everything', sub: 'snapshot + view', run: () => refreshAll() });
  items.push({ id: 'action-settings', group: 'Actions', label: 'Open Settings', sub: 'settings', run: () => navigate('settings') });
  const tasks = (state.snapshot && state.snapshot.tasks) || [];
  if (tasks.length) {
    items.push({ id: 'group-tasks', group: 'Tasks', label: '', sub: '', header: true });
    for (const task of tasks) {
      items.push({
        id: 'task-' + task.id, group: 'Tasks',
        label: task.id + ' · ' + (task.title || '(untitled)'),
        sub: stMeta(task.status).label + (task.stage_title ? ' · ' + task.stage_title : ''),
        run: () => openTask(task.id)
      });
    }
  }
  return items;
}

function openPalette() {
  const input = h('input', {
    class: 'input', type: 'search', placeholder: 'Search views, actions and tasks…',
    'data-autofocus': '1', 'aria-label': 'Command palette search'
  });
  const list = h('div', { class: 'palette-list' });
  const allItems = paletteItems();
  let filtered = allItems.filter((item) => !item.header);
  let activeIndex = 0;

  const paint = () => {
    clear(list);
    if (!filtered.length) {
      list.appendChild(h('div', { class: 'palette-empty', text: 'No matching command.' }));
      return;
    }
    if (activeIndex >= filtered.length) activeIndex = filtered.length - 1;
    let group = null;
    filtered.forEach((item, index) => {
      if (item.group !== group) {
        group = item.group;
        list.appendChild(h('div', { class: 'palette-group', text: group }));
      }
      list.appendChild(h('button', {
        class: 'palette-item' + (index === activeIndex ? ' is-active' : ''),
        type: 'button', title: item.label,
        on: { click: () => runPaletteItem(item) }
      },
        h('span', { class: 'palette-label', text: item.label }),
        item.sub ? h('span', { class: 'palette-sub', text: item.sub }) : null));
    });
    const active = list.querySelector('.palette-item.is-active');
    if (active && active.scrollIntoView) active.scrollIntoView({ block: 'nearest' });
  };

  input.addEventListener('input', () => {
    const query = input.value.trim().toLowerCase();
    filtered = allItems.filter((item) => !item.header &&
      (item.label + ' ' + (item.sub || '')).toLowerCase().indexOf(query) !== -1);
    activeIndex = 0;
    paint();
  });
  input.addEventListener('keydown', (event) => {
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      activeIndex = Math.min(filtered.length - 1, activeIndex + 1);
      paint();
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      activeIndex = Math.max(0, activeIndex - 1);
      paint();
    } else if (event.key === 'Enter') {
      event.preventDefault();
      if (filtered[activeIndex]) runPaletteItem(filtered[activeIndex]);
    } else if (event.key === 'Escape') {
      event.preventDefault();
      closeModal();
    }
  });

  const palette = h('div', { class: 'palette' }, input, list);
  openModal({
    title: 'Command palette',
    body: palette,
    footer: h('div', { class: 'palette-hint' },
      h('span', {}, h('kbd', { class: 'kbd', text: '↑↓' }), ' navigate'),
      h('span', {}, h('kbd', { class: 'kbd', text: '↵' }), ' run'),
      h('span', {}, h('kbd', { class: 'kbd', text: 'esc' }), ' close'),
      h('span', { style: { marginLeft: 'auto' }, text: 'Ctrl/Cmd+K' }))
  });
  paint();
  focusSoon(input);
}

function runPaletteItem(item) {
  if (!item) return;
  closeModal();
  try {
    const result = item.run();
    if (result && typeof result.catch === 'function') result.catch((err) => toast(describeError(err), 'error'));
  } catch (err) {
    toast(describeError(err), 'error');
  }
}

function bindPaletteShortcut() {
  document.addEventListener('keydown', (event) => {
    if ((event.metaKey || event.ctrlKey) && (event.key === 'k' || event.key === 'K')) {
      event.preventDefault();
      openPalette();
    }
  });
}

/* =========================================================================
   24. Approvals inbox
   ========================================================================= */

function approvalStatusColor(status) {
  if (status === 'granted') return 'green';
  if (status === 'denied') return 'red';
  return 'amber';
}

function renderApprovals() {
  const records = state.approvals || [];
  const counts = { pending: 0, granted: 0, denied: 0, all: records.length };
  for (const record of records) {
    if (counts[record.status] !== undefined) counts[record.status] += 1;
  }
  const filter = state.approvalFilter;
  const filtered = records.filter((record) => filter === 'all' || record.status === filter);

  dom.view.appendChild(h('div', { class: 'view-head' },
    h('div', {},
      h('h1', { class: 'view-title', text: 'Approvals' }),
      h('p', { class: 'view-sub', text: counts.pending + ' pending · ' + records.length + ' ' + plural(records.length, 'record') })),
    h('div', { class: 'view-actions' },
      h('button', {
        class: 'btn btn-primary btn-sm', type: 'button', text: state.approvalFormOpen ? 'Close form' : 'Request approval',
        disabled: !canWrite(),
        title: canWrite() ? 'Request a human approval record' : 'The dashboard is read-only',
        on: { click: () => { state.approvalFormOpen = !state.approvalFormOpen; renderView(); } }
      }),
      h('button', {
        class: 'btn btn-sm', type: 'button', text: 'Refresh',
        on: { click: () => { loadApprovals().then(() => renderView()); } }
      }))));

  if (state.approvalFormOpen) dom.view.appendChild(renderApprovalRequestForm());

  const chips = h('div', { class: 'seg-chips', style: { marginBottom: '14px' } });
  for (const entry of APPROVAL_FILTERS) {
    chips.appendChild(h('button', {
      class: 'seg-chip', type: 'button',
      'aria-pressed': state.approvalFilter === entry.key ? 'true' : 'false',
      on: { click: () => { state.approvalFilter = entry.key; renderView(); } }
    }, entry.label, h('span', { class: 'faint', text: String(counts[entry.key] || 0) })));
  }
  dom.view.appendChild(chips);

  if (!state.approvalsLoaded) {
    dom.view.appendChild(loadingRow('Loading approvals…'));
    return;
  }
  if (!filtered.length) {
    dom.view.appendChild(emptyState(
      filter === 'pending' ? 'Nothing awaits your decision' : 'No approval records',
      filter === 'pending'
        ? 'Approvals are requested before a new dependency, a merge, a release, a reopen or a forced state change.'
        : 'Switch the filter to see records in another state.',
      filter === 'pending' ? h('button', {
        class: 'btn', type: 'button', text: 'Request approval',
        disabled: !canWrite(),
        on: { click: () => { state.approvalFormOpen = true; renderView(); } }
      }) : null));
    return;
  }

  const list = h('div', { class: 'approval-list' });
  for (const record of filtered) list.appendChild(renderApprovalCard(record));
  dom.view.appendChild(list);
}

function renderApprovalRequestForm() {
  const tasks = (state.snapshot && state.snapshot.tasks) || [];
  const actionSelect = h('select', { class: 'select', 'aria-label': 'Approval action' },
    h('option', { value: '', text: 'Choose an action…' }),
    APPROVAL_ACTIONS.map((action) => h('option', { value: action, text: action })));
  const taskSelect = h('select', { class: 'select', 'aria-label': 'Task' },
    h('option', { value: '', text: 'No specific task' }),
    tasks.map((task) => h('option', { value: task.id, text: task.id + ' · ' + (task.title || '') })));
  const byInput = h('input', { class: 'input', type: 'text', value: 'owner', 'aria-label': 'Requested by' });
  const noteInput = h('textarea', { class: 'textarea', rows: '2', placeholder: 'Why is this approval needed?', 'aria-label': 'Approval note' });

  const form = h('div', { class: 'card-panel panel-pad', style: { marginBottom: '14px' } },
    h('div', { class: 'between', style: { marginBottom: '10px' } },
      h('div', { class: 'panel-title', text: 'Request an approval' }),
      h('button', {
        class: 'btn btn-ghost btn-sm', type: 'button', text: 'Cancel',
        on: { click: () => { state.approvalFormOpen = false; renderView(); } }
      })),
    h('div', { class: 'form-grid' },
      h('label', { class: 'field' }, h('span', { class: 'field-label', text: 'Action' }), actionSelect),
      h('label', { class: 'field' }, h('span', { class: 'field-label', text: 'Task' }), taskSelect),
      h('label', { class: 'field' }, h('span', { class: 'field-label', text: 'Requested by' }), byInput),
      h('label', { class: 'field span-2' }, h('span', { class: 'field-label', text: 'Note' }), noteInput)),
    h('div', { class: 'form-actions', style: { marginTop: '12px' } },
      h('button', {
        class: 'btn btn-primary', type: 'button', text: 'Request approval',
        on: {
          click: async (event) => {
            const button = event.currentTarget;
            const action = actionSelect.value;
            if (!action) { toast('Choose an approval action', 'warn'); return; }
            button.disabled = true;
            try {
              await api('/api/approvals/request', {
                method: 'POST',
                body: {
                  action: action,
                  task: taskSelect.value || null,
                  by: byInput.value.trim() || 'owner',
                  note: noteInput.value.trim()
                }
              });
              toast('Approval requested', 'ok');
              state.approvalFormOpen = false;
              await loadApprovals();
              await loadSnapshot();
              renderTabs();
              renderView();
            } catch (err) {
              toast('Request failed: ' + describeError(err), 'error');
              button.disabled = false;
            }
          }
        }
      })));

  if (state.approvalBusy) form.appendChild(loadingRow(state.approvalBusy));
  return form;
}

function renderApprovalCard(record) {
  const color = approvalStatusColor(record.status);
  const card = h('div', { class: 'approval', dataset: { approvalId: record.id } });

  const top = h('div', { class: 'approval-top' },
    h('span', { class: 'approval-id', text: record.id }),
    h('span', { class: 'approval-action', text: record.action || '—' }),
    h('span', { class: 'badge bg-' + color + ' st-' + color }, h('span', { class: 'dot' }), record.status || 'unknown'));
  if (record.task) top.appendChild(taskChip(record.task));
  top.appendChild(h('span', {
    class: 'hint',
    text: 'requested by ' + (record.requested_by || '—') + ' · ' + relTime(record.requested_at)
  }));
  card.appendChild(top);

  if (record.note) card.appendChild(h('div', { class: 'approval-note', text: record.note }));

  const meta = h('div', { class: 'approval-meta' });
  if (record.approved_by) meta.appendChild(h('span', { text: 'decided by ' + record.approved_by + ' · ' + relTime(record.approved_at) }));
  meta.appendChild(h('span', { text: 'action ' + (record.action || '—') }));
  if (record.task) meta.appendChild(h('span', { text: 'task ' + record.task }));
  card.appendChild(meta);

  if (record.status === 'pending') {
    const noteInput = h('input', {
      class: 'input', type: 'text', placeholder: 'Decision note (optional)', 'aria-label': 'Decision note',
      on: { input: (event) => { state.approvalNotes = state.approvalNotes || {}; state.approvalNotes[record.id] = event.target.value; } }
    });
    const actions = h('div', { class: 'approval-actions' },
      noteInput,
      h('button', {
        class: 'btn btn-sm btn-primary', type: 'button', text: 'Grant',
        disabled: !canWrite() || Boolean(state.approvalBusy),
        title: canWrite() ? 'POST /api/approvals/' + record.id + '/grant' : 'The dashboard is read-only',
        on: { click: () => decideApproval(record.id, 'grant') }
      }),
      h('button', {
        class: 'btn btn-sm btn-danger', type: 'button', text: 'Deny',
        disabled: !canWrite() || Boolean(state.approvalBusy),
        title: canWrite() ? 'POST /api/approvals/' + record.id + '/deny' : 'The dashboard is read-only',
        on: { click: () => decideApproval(record.id, 'deny') }
      }));
    card.appendChild(actions);
  }
  return card;
}

async function decideApproval(approvalId, verb) {
  const note = (state.approvalNotes && state.approvalNotes[approvalId]) || '';
  state.approvalBusy = verb === 'grant' ? 'Granting ' + approvalId + '…' : 'Denying ' + approvalId + '…';
  renderView();
  try {
    await api('/api/approvals/' + encodeURIComponent(approvalId) + '/' + verb, {
      method: 'POST',
      body: { by: 'owner', note: note }
    });
    toast(approvalId + ' ' + (verb === 'grant' ? 'granted' : 'denied'), 'ok');
    if (state.approvalNotes) delete state.approvalNotes[approvalId];
    await loadApprovals();
    await loadSnapshot();
    renderTabs();
    renderView();
  } catch (err) {
    toast(verb + ' failed: ' + describeError(err), 'error');
  } finally {
    state.approvalBusy = null;
    renderView();
  }
}

/* =========================================================================
   25. Dispatch view
   ========================================================================= */

function renderDispatch() {
  const snapshot = state.snapshot;
  const dispatch = state.dispatch || (snapshot && snapshot.dispatch) || {};
  const running = dispatch.running || [];
  const waves = dispatch.waves || [];
  const blocked = dispatch.blocked || [];
  const conflicts = dispatch.conflicts || [];
  const pending = dispatch.approvals_pending || [];

  dom.view.appendChild(h('div', { class: 'view-head' },
    h('div', {},
      h('h1', { class: 'view-title', text: 'Dispatch' }),
      h('p', { class: 'view-sub', text: 'What the board lets run now, in parallel, and what blocks it.' })),
    h('div', { class: 'view-actions' },
      h('button', {
        class: 'btn btn-sm', type: 'button', text: 'Refresh', disabled: state.dispatchLoading,
        on: {
          click: async () => {
            await loadDispatch();
            renderView();
          }
        }
      }))));

  if (state.dispatchLoading && !state.dispatch) {
    dom.view.appendChild(loadingRow('Computing the dispatch plan…'));
    return;
  }

  const grid = h('div', { class: 'dispatch-grid' });

  /* next wave + waves */
  const waveCard = h('div', { class: 'card-panel dispatch-card' },
    h('div', { class: 'panel-head' }, h('span', { class: 'panel-title', text: 'Waves' })),
    h('div', { class: 'panel-body' }));
  if (!waves.length) {
    waveCard.querySelector('.panel-body').appendChild(h('div', { class: 'hint', text: 'No wave is ready. Every ready task may already be running or blocked.' }));
  } else {
    for (let index = 0; index < waves.length; index += 1) {
      const wave = waves[index] || [];
      const row = h('div', { class: 'wave' },
        h('span', { class: 'wave-no', text: 'W' + (index + 1) }),
        h('div', { class: 'wave-tasks' }, wave.map((entry) => taskChip(entry.id, entry.title))));
      waveCard.querySelector('.panel-body').appendChild(row);
    }
  }
  grid.appendChild(waveCard);

  /* running */
  const runCard = h('div', { class: 'card-panel dispatch-card' },
    h('div', { class: 'panel-head' },
      h('span', { class: 'panel-title', text: 'Running attempts' }),
      h('span', { class: 'pill', text: String(running.length) })),
    h('div', { class: 'panel-body' }));
  if (!running.length) {
    runCard.querySelector('.panel-body').appendChild(h('div', { class: 'hint', text: 'Nothing is in progress right now.' }));
  } else {
    for (const entry of running) {
      const row = h('div', { class: 'dispatch-row' },
        statusDot(entry.status),
        h('div', { class: 'dispatch-row-main' },
          h('div', { class: 'dispatch-row-title' },
            taskChip(entry.id, entry.title),
            statusPill(entry.status),
            entry.claim ? h('span', { class: 'claim-badge' }, h('span', { class: 'dot' }), 'claimed') : null),
          h('div', { class: 'dispatch-reason', text: [
            'attempt ' + (entry.attempt || 0) + (entry.max_attempts ? '/' + entry.max_attempts : ''),
            'tokens ' + fmtTokens(entry.tokens || 0) + (entry.max_tokens ? '/' + fmtTokens(entry.max_tokens) : ''),
            entry.claim ? 'holder ' + (entry.claim.harness || '?') : ''
          ].filter(Boolean).join(' · ') })));
      runCard.querySelector('.panel-body').appendChild(row);
    }
  }
  grid.appendChild(runCard);

  /* blocked */
  const blockedCard = h('div', { class: 'card-panel dispatch-card' },
    h('div', { class: 'panel-head' },
      h('span', { class: 'panel-title', text: 'Blocked' }),
      h('span', { class: 'pill', text: String(blocked.length) })),
    h('div', { class: 'panel-body' }));
  if (!blocked.length) {
    blockedCard.querySelector('.panel-body').appendChild(h('div', { class: 'hint', text: 'No pending task is blocked.' }));
  } else {
    for (const entry of blocked) {
      const row = h('div', { class: 'dispatch-row' },
        h('span', { class: 'dot st-orange' }),
        h('div', { class: 'dispatch-row-main' },
          h('div', { class: 'dispatch-row-title' }, taskChip(entry.id)),
          h('div', { class: 'dispatch-reason', text: entry.reason || '' }),
          entry.action ? h('div', { class: 'dispatch-action cmd-row' },
            h('span', { class: 'cmd', text: entry.action }),
            h('button', {
              class: 'btn btn-sm', type: 'button', text: 'Copy',
              on: { click: () => copyText(entry.action) }
            })) : null));
      blockedCard.querySelector('.panel-body').appendChild(row);
    }
  }
  grid.appendChild(blockedCard);

  /* conflicts + approvals */
  const sideCard = h('div', { class: 'card-panel dispatch-card' },
    h('div', { class: 'panel-head' }, h('span', { class: 'panel-title', text: 'Conflicts' })),
    h('div', { class: 'panel-body' }));
  if (!conflicts.length) {
    sideCard.querySelector('.panel-body').appendChild(h('div', { class: 'hint', text: 'No overlapping write scopes in this plan.' }));
  } else {
    for (const conflict of conflicts) {
      sideCard.querySelector('.panel-body').appendChild(h('div', { class: 'dispatch-row' },
        h('span', { class: 'dot st-orange' }),
        h('div', { class: 'dispatch-row-main' },
          h('div', { class: 'dispatch-row-title' },
            taskChip(conflict.a), h('span', { class: 'faint', text: '↔' }), taskChip(conflict.b)),
          h('div', { class: 'row-wrap', style: { marginTop: '4px' } },
            (conflict.paths || []).map((path) => h('span', { class: 'chip mono', text: String(path) }))))));
    }
  }
  dom.view.appendChild(grid);

  const footer = h('div', { class: 'card-panel panel-pad', style: { marginTop: '14px' } },
    h('div', { class: 'limits-row' },
      h('span', {}, 'max attempts / task ', h('strong', { text: String((dispatch.limits && dispatch.limits.max_attempts_per_task) || '—') })),
      h('span', {}, 'max in progress ', h('strong', { text: String((dispatch.limits && dispatch.limits.max_in_progress) || '—') })),
      h('span', {}, 'pending approvals ', h('strong', { text: String(pending.length) }))),
    pending.length
      ? h('div', { class: 'row-wrap', style: { marginTop: '8px' } },
        pending.map((record) => h('button', {
          class: 'chip chip-link', type: 'button', title: 'Open the approvals inbox',
          on: { click: () => navigate('approvals') }
        }, record.id + ' · ' + (record.action || '') + (record.task ? ' · ' + record.task : ''))))
      : null);
  dom.view.appendChild(footer);

  const generated = snapshot && snapshot.generated_at ? relTime(snapshot.generated_at) : 'just now';
  dom.view.appendChild(h('p', { class: 'hint', style: { marginTop: '10px' }, text: 'Snapshot generated ' + generated + '.' }));
}

/* =========================================================================
   26. Activity view
   ========================================================================= */

function renderActivity() {
  const items = state.activity || [];
  const taskIds = [];
  for (const item of items) {
    if (item.task && taskIds.indexOf(item.task) === -1) taskIds.push(item.task);
  }
  taskIds.sort();

  dom.view.appendChild(h('div', { class: 'view-head' },
    h('div', {},
      h('h1', { class: 'view-title', text: 'Activity' }),
      h('p', { class: 'view-sub', text: items.length + ' recent ' + plural(items.length, 'event') + ' · newest first' })),
    h('div', { class: 'view-actions' },
      h('select', {
        class: 'select', style: { width: 'auto' }, 'aria-label': 'Filter activity by task',
        on: {
          change: (event) => {
            state.activityTask = event.target.value;
            renderView();
          }
        }
      }, h('option', { value: '', text: 'All tasks' }), taskIds.map((id) => {
        const option = h('option', { value: id, text: id });
        if (state.activityTask === id) option.selected = true;
        return option;
      })),
      h('button', {
        class: 'btn btn-sm', type: 'button', text: 'Refresh',
        on: { click: () => { loadActivity().then(() => renderView()); } }
      }))));

  if (!state.activityLoaded) {
    dom.view.appendChild(loadingRow('Loading activity…'));
    return;
  }

  const filtered = state.activityTask ? items.filter((item) => item.task === state.activityTask) : items;
  if (!filtered.length) {
    dom.view.appendChild(emptyState('No activity yet',
      'State changes, gate runs, reviews and approvals appear here as soon as they are recorded.',
      null));
    return;
  }

  const feed = h('div', { class: 'activity card-panel panel-pad' });
  let currentDay = null;
  for (const item of filtered) {
    const key = dayKey(item.at);
    if (key !== currentDay) {
      currentDay = key;
      feed.appendChild(h('div', { class: 'activity-day', text: dayLabel(item.at) }));
    }
    const color = activityColor(item.kind);
    feed.appendChild(h('div', { class: 'activity-item' },
      h('span', { class: 'activity-time', title: item.at || '', text: relTime(item.at) }),
      h('span', { class: 'activity-icon bg-' + color + ' st-' + color, text: eventIcon(item.kind) }),
      h('div', { class: 'activity-main' },
        h('div', { class: 'activity-line' },
          item.task ? taskChip(item.task) : null,
          h('span', { class: 'chip', text: String(item.kind || 'event') }),
          h('span', { class: 'activity-summary', text: String(item.summary || '') })),
        activityDetail(item))));
  }
  dom.view.appendChild(feed);
}

function activityColor(kind) {
  switch (kind) {
    case 'gate': return 'green';
    case 'state': return 'blue';
    case 'review': return 'violet';
    case 'approval': return 'amber';
    default: return 'neutral';
  }
}

function activityDetail(item) {
  const data = item.data || {};
  const note = data.note || (item.kind === 'gate' ? data.command : '');
  if (!note) return null;
  return h('div', { class: 'activity-note', text: truncate(String(note), 220) });
}
/* =========================================================================
   27. Dependency graph
   ========================================================================= */

const GRAPH_NODE_W = 178;
const GRAPH_NODE_H = 42;
const GRAPH_COL_GAP = 64;
const GRAPH_ROW_GAP = 12;
const GRAPH_PAD = 18;

function buildGraphLayout(tasks) {
  const byId = new Map();
  for (const task of tasks) byId.set(task.id, task);

  const depthCache = new Map();
  let cycles = 0;
  let guard = 0;

  function depth(id, stack) {
    if (depthCache.has(id)) return depthCache.get(id);
    if (stack.has(id)) { cycles += 1; return 0; }
    if (stack.size > 200 || guard > 20000) return 0;
    guard += 1;
    const task = byId.get(id);
    if (!task) return 0;
    stack.add(id);
    let value = 0;
    const deps = Array.isArray(task.depends_on) ? task.depends_on : [];
    for (const dep of deps) {
      if (!byId.has(dep)) continue;
      value = Math.max(value, depth(dep, stack) + 1);
    }
    stack.delete(id);
    depthCache.set(id, value);
    return value;
  }

  const stageOrder = new Map();
  const stages = (state.snapshot && state.snapshot.stages) || [];
  stages.forEach((stage, index) => stageOrder.set(String(stage.id), index));
  stageOrder.set('undefined', 999);
  stageOrder.set('null', 999);

  const rows = tasks.slice().sort((a, b) => {
    const sa = stageOrder.has(String(a.stage)) ? stageOrder.get(String(a.stage)) : 999;
    const sb = stageOrder.has(String(b.stage)) ? stageOrder.get(String(b.stage)) : 999;
    if (sa !== sb) return sa - sb;
    return String(a.id).localeCompare(String(b.id));
  });

  const positions = new Map();
  let maxDepth = 0;
  rows.forEach((task, rowIndex) => {
    const value = depth(task.id, new Set());
    if (value > maxDepth) maxDepth = value;
    positions.set(task.id, { row: rowIndex, depth: value });
  });

  return { positions: positions, rows: rows, maxDepth: maxDepth, cycles: cycles, byId: byId };
}

function renderGraph() {
  dom.view.appendChild(h('div', { class: 'view-head' },
    h('div', {},
      h('h1', { class: 'view-title', text: 'Dependency graph' }),
      h('p', { class: 'view-sub', text: 'Columns are DAG depth, rows are grouped by stage. Click a node to open it.' })),
    h('div', { class: 'view-actions' },
      h('div', { class: 'graph-zoom' },
        h('button', {
          class: 'btn btn-sm', type: 'button', text: '−', 'aria-label': 'Zoom out',
          on: { click: () => { state.graph.zoom = Math.max(0.6, Math.round((state.graph.zoom - 0.2) * 10) / 10); renderView(); } }
        }),
        h('button', {
          class: 'btn btn-sm', type: 'button', text: 'Reset', 'aria-label': 'Reset zoom',
          on: { click: () => { state.graph.zoom = 1; renderView(); } }
        }),
        h('button', {
          class: 'btn btn-sm', type: 'button', text: '+', 'aria-label': 'Zoom in',
          on: { click: () => { state.graph.zoom = Math.min(1.8, Math.round((state.graph.zoom + 0.2) * 10) / 10); renderView(); } }
        })))));

  const graphFilterNote = renderGraphFilterNote();
  if (graphFilterNote) dom.view.appendChild(graphFilterNote);

  const tasks = visibleTasks();
  if (!tasks.length) {
    dom.view.appendChild(emptyState('No tasks to graph', 'Adjust the filters or add tasks in the Plan view.', null));
    return;
  }

  const layout = buildGraphLayout(tasks);
  const legend = h('div', { class: 'graph-legend' });
  for (const status of Object.keys(STATUS)) {
    legend.appendChild(h('span', { class: 'graph-legend-item' },
      h('span', { class: 'dot st-' + STATUS[status].color }), STATUS[status].label));
  }
  dom.view.appendChild(legend);

  if (layout.cycles) {
    dom.view.appendChild(h('div', { class: 'callout callout-warn', style: { marginBottom: '10px' } },
      h('div', { text: 'Dependency cycle detected (' + layout.cycles + ' back edge' + (layout.cycles === 1 ? '' : 's') + '); those nodes are drawn at depth 0 so the view stays usable.' })));
  }

  const svg = buildGraphSvg(layout);
  const panel = h('div', { class: 'graph-panel' }, svg);
  dom.view.appendChild(panel);

  const stageCounts = new Map();
  for (const task of tasks) {
    const key = String(task.stage);
    stageCounts.set(key, (stageCounts.get(key) || 0) + 1);
  }
  const stats = h('div', { class: 'graph-stats', style: { marginTop: '10px' } },
    h('span', { text: tasks.length + ' ' + plural(tasks.length, 'node') }),
    h('span', { text: (layout.maxDepth + 1) + ' ' + plural(layout.maxDepth + 1, 'column') }),
    h('span', { text: 'stage groups: ' + Array.from(stageCounts.values()).length }),
    h('span', { text: 'zoom ' + Math.round(state.graph.zoom * 100) + '%' }));
  dom.view.appendChild(stats);
}

function buildGraphSvg(layout) {
  const rows = layout.rows;
  const columns = layout.maxDepth + 1;
  const width = GRAPH_PAD * 2 + columns * GRAPH_NODE_W + Math.max(0, columns - 1) * GRAPH_COL_GAP;
  const height = GRAPH_PAD * 2 + rows.length * GRAPH_NODE_H + Math.max(0, rows.length - 1) * GRAPH_ROW_GAP;
  const zoom = state.graph.zoom || 1;

  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('class', 'graph-svg');
  svg.setAttribute('viewBox', '0 0 ' + width + ' ' + height);
  svg.setAttribute('width', String(Math.round(width * zoom)));
  svg.setAttribute('height', String(Math.round(height * zoom)));
  svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', 'Task dependency graph with ' + rows.length + ' tasks');

  const edges = document.createElementNS('http://www.w3.org/2000/svg', 'g');
  const nodes = document.createElementNS('http://www.w3.org/2000/svg', 'g');

  const positionOf = (taskId) => {
    const entry = layout.positions.get(taskId);
    if (!entry) return null;
    return {
      x: GRAPH_PAD + entry.depth * (GRAPH_NODE_W + GRAPH_COL_GAP),
      y: GRAPH_PAD + entry.row * (GRAPH_NODE_H + GRAPH_ROW_GAP)
    };
  };

  for (const task of rows) {
    const target = positionOf(task.id);
    if (!target) continue;
    for (const dep of (Array.isArray(task.depends_on) ? task.depends_on : [])) {
      const source = positionOf(dep);
      if (!source) continue;
      const x1 = source.x + GRAPH_NODE_W;
      const y1 = source.y + GRAPH_NODE_H / 2;
      const x2 = target.x;
      const y2 = target.y + GRAPH_NODE_H / 2;
      const bend = Math.max(24, (x2 - x1) * 0.5);
      const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      path.setAttribute('class', 'g-edge');
      path.setAttribute('d', 'M' + x1 + ' ' + y1 + ' C' + (x1 + bend) + ' ' + y1 + ', ' + (x2 - bend) + ' ' + y2 + ', ' + x2 + ' ' + y2);
      edges.appendChild(path);
    }
  }

  for (const task of rows) {
    const position = positionOf(task.id);
    if (!position) continue;
    const group = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    group.setAttribute('class', 'g-node');
    group.setAttribute('data-task-id', task.id);
    group.setAttribute('data-status', task.status || 'pending');
    group.setAttribute('tabindex', '0');
    group.setAttribute('role', 'button');
    group.setAttribute('aria-label', task.id + ': ' + (task.title || 'untitled') + ' — ' + stMeta(task.status).label);
    group.addEventListener('click', () => openTask(task.id));
    group.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); openTask(task.id); }
    });

    const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    rect.setAttribute('class', 'g-rect');
    rect.setAttribute('x', String(position.x));
    rect.setAttribute('y', String(position.y));
    rect.setAttribute('width', String(GRAPH_NODE_W));
    rect.setAttribute('height', String(GRAPH_NODE_H));
    rect.setAttribute('rx', '8');
    group.appendChild(rect);

    const title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
    title.textContent = task.id + ' · ' + (task.title || 'untitled') + ' · ' + stMeta(task.status).label +
      ' · ' + (task.stage_title || task.stage || '') + (task.owner ? ' · ' + task.owner : '');
    group.appendChild(title);

    const idText = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    idText.setAttribute('class', 'g-label');
    idText.setAttribute('x', String(position.x + 10));
    idText.setAttribute('y', String(position.y + 16));
    idText.textContent = task.id;
    group.appendChild(idText);

    const nameText = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    nameText.setAttribute('class', 'g-title');
    nameText.setAttribute('x', String(position.x + 10));
    nameText.setAttribute('y', String(position.y + 31));
    nameText.textContent = truncate(task.title || '(untitled)', 26);
    group.appendChild(nameText);

    nodes.appendChild(group);
  }

  svg.appendChild(edges);
  svg.appendChild(nodes);
  return svg;
}

/* =========================================================================
   28. Sessions view
   ========================================================================= */

function sessionById(sessionId) {
  return (state.sessions || []).find((session) => session.id === sessionId) || null;
}

function renderSessions() {
  const sessions = state.sessions || [];
  const running = sessions.filter((session) => SESSION_ACTIVE.has(session.status));

  dom.view.appendChild(h('div', { class: 'view-head' },
    h('div', {},
      h('h1', { class: 'view-title', text: 'Sessions' }),
      h('p', { class: 'view-sub', text: sessions.length + ' ' + plural(sessions.length, 'session') + ' · ' + running.length + ' running' })),
    h('div', { class: 'view-actions' },
      h('button', {
        class: 'btn btn-sm', type: 'button', text: 'Refresh',
        on: { click: () => { loadSessions().then(() => renderView()); } }
      }))));

  dom.view.appendChild(renderSessionStartForm());

  if (!state.sessionsLoaded) {
    dom.view.appendChild(loadingRow('Loading sessions…'));
    return;
  }

  const listWrap = h('div', { class: 'card-panel', style: { marginBottom: '14px' } },
    h('div', { class: 'panel-head' },
      h('span', { class: 'panel-title', text: 'Headless sessions' }),
      h('span', { class: 'pill', text: String(sessions.length) })),
    h('div', { class: 'panel-body', id: 'session-list-wrap' }));
  dom.view.appendChild(listWrap);
  paintSessionList();

  const consoleWrap = h('div', { id: 'session-console-wrap' });
  dom.view.appendChild(consoleWrap);
  paintSessionConsole();
}

function renderSessionStartForm() {
  const tasks = (state.snapshot && state.snapshot.tasks) || [];
  const form = state.sessionStartForm || (state.sessionStartForm = { task: '', role: 'worker', worktree: false, note: '' });

  const taskSelect = h('select', {
    class: 'select', 'aria-label': 'Task for the session',
    on: { change: (event) => { form.task = event.target.value; } }
  }, h('option', { value: '', text: 'No task (free session)' }),
    tasks.map((task) => {
      const option = h('option', { value: task.id, text: task.id + ' · ' + (task.title || '') });
      if (form.task === task.id) option.selected = true;
      return option;
    }));

  const roleSelect = h('select', {
    class: 'select', 'aria-label': 'Session role',
    on: { change: (event) => { form.role = event.target.value; } }
  }, SESSION_ROLES.map((role) => {
    const option = h('option', { value: role, text: role });
    if (form.role === role) option.selected = true;
    return option;
  }));

  const noteInput = h('textarea', {
    class: 'textarea', rows: '2', placeholder: 'Optional operator note added to the prompt',
    'data-fkey': 'session-start-note',
    on: { input: (event) => { form.note = event.target.value; } }
  });
  noteInput.value = form.note || '';

  return h('div', { class: 'card-panel panel-pad', style: { marginBottom: '14px' } },
    h('div', { class: 'panel-title', style: { marginBottom: '10px' }, text: 'Start a session' }),
    h('div', { class: 'form-grid' },
      h('label', { class: 'field' }, h('span', { class: 'field-label', text: 'Task' }), taskSelect),
      h('label', { class: 'field' }, h('span', { class: 'field-label', text: 'Role' }), roleSelect),
      h('label', { class: 'field span-2' }, h('span', { class: 'field-label', text: 'Note' }), noteInput)),
    h('div', { class: 'form-actions', style: { marginTop: '10px' } },
      h('label', { class: 'checkbox' },
        h('input', {
          type: 'checkbox', checked: form.worktree,
          on: { change: (event) => { form.worktree = event.target.checked; } }
        }),
        'Run in a task worktree'),
      h('button', {
        class: 'btn btn-primary', type: 'button', text: 'Start session',
        disabled: !canWrite(),
        title: canWrite() ? 'POST /api/sessions' : 'The dashboard is read-only',
        on: { click: () => startSessionFromView() }
      }),
      h('span', { class: 'hint', text: 'A session runs the configured provider headlessly; its log is polled every 700 ms.' })));
}

function paintSessionList() {
  const host = document.getElementById('session-list-wrap');
  if (!host) return;
  clear(host);
  const sessions = state.sessions || [];
  if (!sessions.length) {
    host.appendChild(h('div', { class: 'session-empty', text: 'No sessions yet. Start one above, or from a task drawer.' }));
    return;
  }
  for (const session of sessions) {
    const active = SESSION_ACTIVE.has(session.status);
    const selected = state.sessionSelected === session.id;
    const watching = selected && state.viewWatch && state.viewWatch.timer;
    const row = h('div', { class: 'session-row' + (selected ? ' is-active' : '') },
      h('span', { class: 'session-id', text: session.id }),
      statusPill(session.status),
      session.task ? taskChip(session.task) : h('span', { class: 'chip', text: 'no task' }),
      h('span', { class: 'hint', text: session.role || 'worker' }),
      h('span', { class: 'hint', text: fmtTokens(session.tokens || 0) + ' tokens' }),
      session.worktree ? h('span', { class: 'chip', text: 'worktree' }) : null,
      h('span', { class: 'hint', text: relTime(session.started) }),
      h('div', { class: 'job-actions' },
        h('button', {
          class: 'btn btn-sm', type: 'button', text: watching ? 'Watching' : 'Watch',
          disabled: Boolean(watching),
          on: { click: () => { state.sessionSelected = session.id; startViewSessionWatch(session.id); paintSessionList(); paintSessionConsole(); } }
        }),
        h('button', {
          class: 'btn btn-sm', type: 'button', text: 'Log',
          on: { click: () => openSessionLog(session.id) }
        }),
        active ? h('button', {
          class: 'btn btn-sm btn-danger', type: 'button', text: 'Stop',
          on: { click: () => stopSession(session.id) }
        }) : null));
    host.appendChild(row);
  }
}

function paintSessionConsole() {
  const host = document.getElementById('session-console-wrap');
  if (!host) return;
  clear(host);
  const selected = state.sessionSelected ? sessionById(state.sessionSelected) : null;
  const watch = state.viewWatch;
  if (!selected && !watch) {
    host.appendChild(h('div', { class: 'card-panel panel-pad hint', text: 'Select a session and press Watch to stream its log.' }));
    return;
  }
  const sessionId = (watch && watch.sessionId) || (selected && selected.id);
  const session = sessionId ? sessionById(sessionId) : null;
  const status = session ? session.status : (watch && watch.status);
  const consoleNode = h('div', { class: 'session-console' },
    h('div', { class: 'session-console-head' },
      h('span', { class: 'panel-title', text: 'Session console' }),
      h('span', { class: 'session-id', text: sessionId || '' }),
      h('span', { id: 'session-console-status' }, status ? statusPill(status) : null),
      watch && SESSION_ACTIVE.has(status) ? h('span', { class: 'console-live' }, h('span', { class: 'dot' }), 'live · 700ms') : null,
      h('div', { style: { marginLeft: 'auto', display: 'flex', gap: '4px' } },
        h('button', {
          class: 'btn btn-sm', type: 'button', text: 'Copy log',
          on: { click: () => copyText((watch && watch.text) || '') }
        }),
        session && SESSION_ACTIVE.has(session.status) ? h('button', {
          class: 'btn btn-sm btn-danger', type: 'button', text: 'Stop',
          on: { click: () => stopSession(session.id) }
        }) : null)),
    h('div', { class: 'session-console-body' },
      h('pre', { class: 'log-pre', id: 'session-console', text: (watch && watch.text) || '' })));
  host.appendChild(consoleNode);
  if (session && session.last_message) {
    host.appendChild(h('p', { class: 'hint', style: { marginTop: '8px' },
      text: 'Last message: ' + truncate(session.last_message, 400) }));
  }
}

function renderSessionConsoleOnly() {
  if (state.route.view !== 'sessions') return;
  paintSessionList();
  const pre = document.getElementById('session-console');
  if (pre && state.viewWatch) {
    pre.textContent = state.viewWatch.text;
    pre.scrollTop = pre.scrollHeight;
  }
  const statusHost = document.getElementById('session-console-status');
  if (statusHost) {
    const session = state.viewWatch ? sessionById(state.viewWatch.sessionId) : null;
    const status = session ? session.status : (state.viewWatch ? state.viewWatch.status : null);
    clear(statusHost);
    if (status) statusHost.appendChild(statusPill(status));
  }
}

function startViewSessionWatch(sessionId) {
  if (!sessionId) return;
  if (state.viewWatch && state.viewWatch.timer) window.clearInterval(state.viewWatch.timer);
  state.viewWatch = { sessionId: sessionId, offset: 0, text: '', status: null, timer: null };
  paintSessionConsole();
  const tick = async () => {
    const watch = state.viewWatch;
    if (!watch || watch.sessionId !== sessionId) return;
    try {
      const chunk = await api('/api/sessions/' + encodeURIComponent(sessionId) + '/log?offset=' + watch.offset);
      if (state.viewWatch !== watch) return;
      if (chunk && typeof chunk.text === 'string' && chunk.text) watch.text += chunk.text;
      if (chunk && typeof chunk.next === 'number') watch.offset = chunk.next;
      const session = sessionById(sessionId);
      if (session) {
        watch.status = session.status;
        watch.missing = 0;
      } else {
        watch.missing = (watch.missing || 0) + 1;
        if (watch.missing >= 3) watch.status = 'unknown';
      }
      const pre = document.getElementById('session-console');
      if (pre) { pre.textContent = watch.text; pre.scrollTop = pre.scrollHeight; }
      const statusHost = document.getElementById('session-console-status');
      if (statusHost) {
        clear(statusHost);
        if (watch.status) statusHost.appendChild(statusPill(watch.status));
      }
      if (watch.status && !SESSION_ACTIVE.has(watch.status)) {
        if (watch.timer) window.clearInterval(watch.timer);
        watch.timer = null;
        paintSessionList();
      }
    } catch (err) {
      watch.text += '\n[dashboard] ' + describeError(err) + '\n';
      if (watch.timer) window.clearInterval(watch.timer);
      watch.timer = null;
    }
  };
  state.viewWatch.timer = window.setInterval(tick, 700);
  viewTimers.push(state.viewWatch.timer);
  tick();
}

async function startSessionFromView() {
  const form = state.sessionStartForm || {};
  try {
    const session = await api('/api/sessions', {
      method: 'POST',
      body: {
        task: form.task || null,
        role: form.role || 'worker',
        note: form.note || '',
        worktree: Boolean(form.worktree)
      }
    });
    toast('Session ' + session.id + ' started', 'ok');
    state.sessionSelected = session.id;
    await loadSessions({ quiet: true });
    startViewSessionWatch(session.id);
    renderView();
  } catch (err) {
    toast('Session failed to start: ' + describeError(err), 'error');
  }
}

async function openSessionLog(sessionId) {
  const pre = h('pre', { class: 'log-pre', text: 'Loading session log…' });
  openModal({
    title: 'Session log · ' + sessionId,
    body: [pre],
    footer: [
      h('button', { class: 'btn', type: 'button', text: 'Copy', on: { click: () => copyText(pre.textContent) } }),
      h('button', { class: 'btn btn-primary', type: 'button', text: 'Close', on: { click: () => closeModal() } })
    ]
  });
  try {
    const chunk = await api('/api/sessions/' + encodeURIComponent(sessionId) + '/log?offset=0');
    pre.textContent = (chunk && chunk.text) || '(empty log)';
    pre.scrollTop = pre.scrollHeight;
  } catch (err) {
    pre.textContent = describeError(err);
  }
}
/* =========================================================================
   29. Plan view: interview wizard, saved answers and plan editing
   ========================================================================= */

function renderPlanView() {
  if (!state.plan && !state.planError) {
    dom.view.appendChild(loadingRow('Loading the plan…'));
    return;
  }
  if (!state.plan) {
    dom.view.appendChild(h('div', { class: 'card-panel panel-pad' },
      h('div', { class: 'view-title', text: 'Plan' }),
      h('div', { style: { marginTop: '10px' } }, errorCallout(state.planError)),
      h('div', { style: { marginTop: '12px' } },
        h('button', {
          class: 'btn btn-primary', type: 'button', text: 'Retry',
          on: { click: () => loadPlan().then(() => renderView()) }
        }))));
    return;
  }
  if (state.plan.board_present) renderPlanBoard();
  else renderPlanWizard();
}

function planSteps(boardPresent, generatorSession) {
  const step = boardPresent ? 3 : (generatorSession ? 2 : 1);
  const items = [
    { no: 1, label: 'Interview', state: step > 1 ? 'is-done' : 'is-active' },
    { no: 2, label: 'Generate', state: step === 2 ? 'is-active' : (step > 2 ? 'is-done' : '') },
    { no: 3, label: 'Approve', state: step === 3 ? 'is-active' : '' }
  ];
  const row = h('div', { class: 'steps' });
  items.forEach((item, index) => {
    if (index) row.appendChild(h('span', { class: 'step-sep' }));
    row.appendChild(h('span', { class: 'step ' + item.state },
      h('span', { class: 'step-no', text: String(item.no) }),
      h('span', { text: item.label })));
  });
  return row;
}

function renderPlanWizard() {
  const plan = state.plan;
  const generatorSession = plan.prompt && plan.prompt.session ? plan.prompt.session : null;

  dom.view.appendChild(h('div', { class: 'wizard' },
    h('div', { class: 'wizard-hero' },
      h('div', { class: 'wizard-kicker', text: 'Plan a project' }),
      h('h1', { class: 'wizard-title', text: 'From idea to a dispatchable board' }),
      h('p', {
        class: 'wizard-lede',
        text: 'Answer the interview once. A headless generator writes ARCHITECTURE.md, board.json, policy.json and the task briefs; you approve the plan and the normal task loop starts.'
      })),
    planSteps(false, generatorSession)));

  const wizard = dom.view.querySelector('.wizard');
  if (state.planError) wizard.appendChild(errorCallout(state.planError, { class: 'inline-error' }));
  if (state.planBusy) wizard.appendChild(loadingRow(state.planBusy));

  const fields = plan.fields || [];
  const answers = plan.answers || {};
  const form = h('div', { class: 'card-panel panel-pad wizard-section', id: 'interview-form' },
    h('div', { class: 'between', style: { marginBottom: '12px' } },
      h('span', { class: 'panel-title', text: 'Interview' }),
      h('span', { class: 'pill', text: state.plan.status === 'approved' ? 'approved' : 'draft' })),
    buildInterviewFields(fields, answers),
    h('div', { class: 'form-actions', style: { marginTop: '14px' } },
      h('button', {
        class: 'btn', type: 'button', text: 'Save answers',
        disabled: !canWrite() || Boolean(state.planBusy),
        title: 'PUT /api/plan/answers',
        on: { click: () => saveInterviewAnswers() }
      }),
      h('button', {
        class: 'btn btn-primary', type: 'button', text: 'Generate plan',
        disabled: !canWrite() || Boolean(state.planBusy),
        title: 'POST /api/plan/generator — starts a headless generator session',
        on: { click: () => generatePlan() }
      }),
      h('span', { class: 'hint grow', text: 'Generate stores the answers, writes the prompt and starts the generator session.' })));
  wizard.appendChild(form);

  /* generator console */
  const generatorCard = h('div', { class: 'card-panel panel-pad wizard-section' },
    h('div', { class: 'between', style: { marginBottom: '10px' } },
      h('span', { class: 'panel-title', text: 'Generator session' }),
      generatorSession ? h('span', { class: 'session-id', text: generatorSession }) : h('span', { class: 'pill', text: 'not started' })));
  if (generatorSession) {
    const status = state.generator && state.generator.status;
    generatorCard.appendChild(h('div', { class: 'console-bar' },
      h('span', { id: 'plan-generator-status' }, status ? statusPill(status) : null),
      h('span', { class: 'hint', text: 'Prompt: ' + (plan.prompt && plan.prompt.path ? plan.prompt.path : 'kept in the runtime folder') }),
      h('div', { style: { marginLeft: 'auto', display: 'flex', gap: '4px' } },
        h('button', {
          class: 'btn btn-sm', type: 'button', text: 'Log',
          on: { click: () => openSessionLog(generatorSession) }
        }),
        h('button', {
          class: 'btn btn-sm btn-danger', type: 'button', text: 'Stop',
          disabled: !canWrite(),
          on: { click: () => stopSession(generatorSession) }
        }))));
    generatorCard.appendChild(h('pre', {
      class: 'log-pre', id: 'plan-generator-console',
      text: (state.generator && state.generator.text) || 'Waiting for the first output…'
    }));
    generatorCard.appendChild(h('p', { class: 'hint', style: { marginTop: '8px' },
      text: 'The board appears automatically when the generator writes board.json; the view refreshes on every state event.' }));
    if (!state.generator) watchPlanGenerator(generatorSession);
  } else {
    generatorCard.appendChild(h('p', { class: 'hint', text: 'Answer the interview and press "Generate plan" to start a headless generator session.' }));
  }
  wizard.appendChild(generatorCard);

  /* approve */
  const boardPresent = Boolean(plan.board_present);
  const approveCard = h('div', { class: 'card-panel panel-pad wizard-section' },
    h('div', { class: 'between', style: { marginBottom: '10px' } },
      h('span', { class: 'panel-title', text: 'Approve the plan' }),
      boardPresent ? h('span', { class: 'pill pill-ok', text: 'board.json found' }) : h('span', { class: 'pill', text: 'waiting for board.json' })),
    h('div', { class: 'row-wrap' },
      h('button', {
        class: 'btn btn-primary', type: 'button', text: 'Approve plan',
        disabled: !boardPresent || !canWrite() || Boolean(state.planBusy),
        title: boardPresent ? 'POST /api/plan/approve' : 'The generator must write a valid board.json first',
        on: { click: () => approvePlan() }
      }),
      h('button', {
        class: 'btn', type: 'button', text: 'Refresh',
        on: {
          click: async () => {
            await Promise.all([loadPlan(), loadSnapshot()]);
            renderHeader();
            renderTabs();
            renderView();
          }
        }
      }),
      h('span', { class: 'hint grow', text: boardPresent
        ? 'Approving records that the owner accepted this plan.'
        : 'Approval needs a valid board.json from the generator session.' })));
  wizard.appendChild(approveCard);
}

function buildInterviewFields(fields, answers) {
  const wrap = h('div', { class: 'col', style: { gap: '12px' } });
  for (const field of fields) {
    const value = answers[field.key];
    let control;
    if (field.kind === 'choice') {
      const seg = h('div', { class: 'seg', role: 'radiogroup', 'aria-label': field.label });
      for (const choice of field.choices || []) {
        const inputId = 'choice-' + field.key + '-' + choice;
        seg.appendChild(h('label', { class: 'seg-option' },
          h('input', {
            type: 'radio', name: 'field-' + field.key, id: inputId, value: choice,
            checked: (value || (field.choices || [])[0]) === choice
          }),
          h('span', { text: choice })));
      }
      control = seg;
    } else if (field.kind === 'pairs') {
      control = pairsEditor(field.key, Array.isArray(value) ? value : []);
    } else if (field.key === 'name') {
      control = h('input', { class: 'input', type: 'text', value: value || '' });
      control.setAttribute('data-field-key', field.key);
      control.setAttribute('data-fkey', 'plan-field-' + field.key);
    } else {
      control = h('textarea', { class: 'textarea', rows: field.key === 'goal' ? '3' : '2' });
      control.value = value || '';
      control.setAttribute('data-field-key', field.key);
      control.setAttribute('data-fkey', 'plan-field-' + field.key);
    }
    wrap.appendChild(h('label', { class: 'field' },
      h('span', { class: 'field-label' },
        field.label || field.key,
        field.required ? h('span', { class: 'faint', text: ' *' }) : null),
      control,
      field.help ? h('span', { class: 'field-help', text: field.help }) : null));
  }
  return wrap;
}

function pairsEditor(key, pairs) {
  const wrap = h('div', { class: 'pairs', dataset: { pairs: key } });
  const addButton = h('button', {
    class: 'btn btn-sm', type: 'button', text: 'Add question',
    on: { click: () => addPairRow(wrap, '', '') }
  });
  wrap.appendChild(addButton);
  for (const pair of pairs) addPairRow(wrap, pair.question || '', pair.answer || '');
  return wrap;
}

function addPairRow(wrap, question, answer) {
  const row = h('div', { class: 'pair-row' },
    h('input', { class: 'input', type: 'text', placeholder: 'Question', value: question, 'data-pair-q': '1' }),
    h('input', { class: 'input', type: 'text', placeholder: 'Answer (optional)', value: answer, 'data-pair-a': '1' }),
    h('button', {
      class: 'btn btn-ghost btn-sm', type: 'button', text: '×', 'aria-label': 'Remove question pair',
      on: { click: () => row.remove() }
    }));
  const addButton = wrap.querySelector('button');
  wrap.insertBefore(row, addButton);
  return row;
}

function readInterviewAnswers(root) {
  const plan = state.plan;
  if (!plan) return null;
  const answers = {};
  const missing = [];
  for (const field of plan.fields || []) {
    if (field.kind === 'pairs') {
      const host = root.querySelector('[data-pairs="' + field.key + '"]');
      const pairs = [];
      if (host) {
        for (const row of host.querySelectorAll('.pair-row')) {
          const question = row.querySelector('[data-pair-q]');
          const answer = row.querySelector('[data-pair-a]');
          if (question && question.value.trim()) {
            pairs.push({ question: question.value.trim(), answer: answer ? answer.value.trim() : '' });
          }
        }
      }
      answers[field.key] = pairs;
    } else if (field.kind === 'choice') {
      const selected = root.querySelector('input[name="field-' + field.key + '"]:checked');
      answers[field.key] = selected ? selected.value : '';
    } else {
      const input = root.querySelector('[data-field-key="' + field.key + '"]');
      answers[field.key] = input ? input.value : '';
    }
    if (field.required && !String(answers[field.key] || '').trim()) missing.push(field.label || field.key);
  }
  if (missing.length) {
    toast('Required answers: ' + missing.join(', '), 'warn', 5000);
    return null;
  }
  return answers;
}

async function saveInterviewAnswers() {
  const root = document.getElementById('interview-form');
  if (!root) return;
  const answers = readInterviewAnswers(root);
  if (!answers) return;
  state.planBusy = 'Saving answers…';
  state.planError = null;
  renderView();
  let saved = false;
  try {
    await api('/api/plan/answers', { method: 'PUT', body: { answers: answers, mode: answers.mode } });
    saved = true;
    toast('Interview answers saved', 'ok');
    await loadPlan();
    renderView();
  } catch (err) {
    state.planError = err;
    toast('Save failed: ' + describeError(err), 'error');
  } finally {
    state.planBusy = null;
    renderView();
  }
  return saved;
}

async function generatePlan() {
  const root = document.getElementById('interview-form');
  if (!root) return;
  const answers = readInterviewAnswers(root);
  if (!answers) return;
  state.planBusy = 'Starting the generator session…';
  state.planError = null;
  renderView();
  try {
    const result = await api('/api/plan/generator', { method: 'POST', body: { answers: answers } });
    toast('Generator session started', 'ok');
    await loadPlan();
    if (result && result.session && result.session.id) watchPlanGenerator(result.session.id);
    renderView();
  } catch (err) {
    state.planError = err;
    toast('Generate failed: ' + describeError(err), 'error');
  } finally {
    state.planBusy = null;
    renderView();
  }
}

function watchPlanGenerator(sessionId) {
  if (!sessionId) return;
  if (!state.generator || state.generator.sessionId !== sessionId) {
    state.generator = { sessionId: sessionId, offset: 0, text: '', status: null, timer: null, ticks: 0 };
  }
  if (state.generator.timer) return;
  const tick = async () => {
    const generator = state.generator;
    if (!generator || generator.sessionId !== sessionId) return;
    generator.ticks = (generator.ticks || 0) + 1;
    try {
      const chunk = await api('/api/sessions/' + encodeURIComponent(sessionId) + '/log?offset=' + generator.offset);
      if (state.generator !== generator) return;
      if (chunk && typeof chunk.text === 'string' && chunk.text) generator.text += chunk.text;
      if (chunk && typeof chunk.next === 'number') generator.offset = chunk.next;
      if (generator.ticks % 4 === 0) {
        try {
          const sessions = await api('/api/sessions');
          const session = (sessions || []).find((item) => item.id === sessionId);
          if (session) {
            generator.status = session.status;
            generator.missing = 0;
          } else {
            generator.missing = (generator.missing || 0) + 1;
            if (generator.missing >= 2) generator.status = 'unknown';
          }
        } catch (err) { /* keep the console alive */ }
      }
      paintPlanGeneratorConsole();
      if (generator.status && !SESSION_ACTIVE.has(generator.status)) {
        if (generator.timer) window.clearInterval(generator.timer);
        generator.timer = null;
        paintPlanGeneratorConsole();
        await Promise.all([loadPlan(), loadSnapshot()]);
        renderHeader();
        renderTabs();
        renderView();
      }
    } catch (err) {
      generator.text += '\n[dashboard] ' + describeError(err) + '\n';
      paintPlanGeneratorConsole();
    }
  };
  state.generator.timer = window.setInterval(tick, 850);
  viewTimers.push(state.generator.timer);
  paintPlanGeneratorConsole();
  tick();
}

function paintPlanGeneratorConsole() {
  const pre = document.getElementById('plan-generator-console');
  if (pre && state.generator) {
    pre.textContent = state.generator.text || 'Waiting for the first output…';
    pre.scrollTop = pre.scrollHeight;
  }
  const statusHost = document.getElementById('plan-generator-status');
  if (statusHost) {
    clear(statusHost);
    if (state.generator && state.generator.status) statusHost.appendChild(statusPill(state.generator.status));
  }
}

async function approvePlan() {
  state.planBusy = 'Approving the plan…';
  state.planError = null;
  renderView();
  try {
    const result = await api('/api/plan/approve', { method: 'POST', body: {} });
    toast('Plan approved' + (result && result.tasks !== undefined ? ' · ' + result.tasks + ' tasks' : ''), 'ok');
    await Promise.all([loadConfig(), loadSnapshot(), loadPlan()]);
    renderHeader();
    renderTabs();
    if (state.snapshot) {
      state.route = { view: 'board', taskId: null };
      try { history.replaceState(null, '', '#/board'); } catch (err) { location.hash = '#/board'; }
    }
    renderView();
  } catch (err) {
    state.planError = err;
    toast('Approve failed: ' + describeError(err), 'error');
  } finally {
    state.planBusy = null;
    renderView();
  }
}

/* ---------- plan of an existing board ---------- */

function renderPlanBoard() {
  const plan = state.plan;
  const snapshot = state.snapshot;
  const stages = (snapshot && snapshot.stages) || [];
  const tasks = (snapshot && snapshot.tasks) || [];

  dom.view.appendChild(h('div', { class: 'view-head' },
    h('div', {},
      h('h1', { class: 'view-title', text: 'Plan' }),
      h('p', {
        class: 'view-sub',
        text: [
          'mode ' + (plan.mode || 'greenfield'),
          plan.status === 'approved' ? 'approved ' + relTime(plan.approved_at) : 'draft',
          'updated ' + relTime(plan.updated)
        ].filter(Boolean).join(' · ')
      })),
    h('div', { class: 'view-actions' },
      h('button', {
        class: 'btn btn-primary btn-sm', type: 'button', text: 'New task',
        disabled: !canWrite() || !snapshot,
        title: canWrite() ? 'POST /api/plan/tasks' : 'The dashboard is read-only',
        on: { click: () => openTaskEditor(null) }
      }),
      h('button', {
        class: 'btn btn-sm', type: 'button', text: 'Refresh',
        on: {
          click: async () => {
            await Promise.all([loadPlan(), loadSnapshot()]);
            renderHeader();
            renderTabs();
            renderView();
          }
        }
      }))));

  if (state.planError) dom.view.appendChild(errorCallout(state.planError, { class: 'inline-error' }));
  if (state.planBusy) dom.view.appendChild(loadingRow(state.planBusy));

  /* interview answers */
  const fields = plan.fields || [];
  const answers = plan.answers || {};
  const interviewCard = h('div', { class: 'card-panel', style: { marginBottom: '14px' } },
    h('div', { class: 'panel-head' },
      h('div', {},
        h('span', { class: 'panel-title', text: 'Interview answers' }),
        h('span', { class: 'pill', style: { marginLeft: '8px' }, text: state.interviewOpen ? 'editing' : (plan.status || 'draft') })),
      h('div', { class: 'row' },
        h('button', {
          class: 'btn btn-sm', type: 'button', text: state.interviewOpen ? 'Cancel' : 'Edit answers',
          disabled: !canWrite(),
          on: { click: () => { state.interviewOpen = !state.interviewOpen; renderView(); } }
        }),
        h('button', {
          class: 'btn btn-sm', type: 'button', text: 'Approve plan',
          disabled: !canWrite() || plan.status === 'approved',
          title: 'POST /api/plan/approve',
          on: { click: () => approvePlan() }
        })),
    ),
    h('div', { class: 'panel-body' }));
  if (state.interviewOpen) {
    const form = h('div', { id: 'interview-form' }, buildInterviewFields(fields, answers));
    interviewCard.querySelector('.panel-body').appendChild(form);
    interviewCard.querySelector('.panel-body').appendChild(h('div', { class: 'form-actions', style: { marginTop: '14px' } },
      h('button', {
        class: 'btn btn-primary', type: 'button', text: 'Save answers',
        disabled: !canWrite() || Boolean(state.planBusy),
        on: { click: () => saveInterviewAnswersFromPlan() }
      }),
      h('span', { class: 'hint', text: 'Saving the answers resets an approved plan to draft.' })));
  } else {
    const list = h('dl', { class: 'kv' });
    for (const field of fields) {
      let value = answers[field.key];
      if (field.kind === 'pairs') {
        const pairs = Array.isArray(value) ? value : [];
        value = pairs.length ? pairs.map((pair) => 'Q: ' + pair.question + (pair.answer ? ' — A: ' + pair.answer : '')).join('\n') : '—';
      }
      if (value === null || value === undefined || value === '') value = '—';
      list.appendChild(h('dt', { text: field.label || field.key }));
      list.appendChild(h('dd', { text: String(value) }));
    }
    interviewCard.querySelector('.panel-body').appendChild(list);
  }
  dom.view.appendChild(interviewCard);

  /* stages */
  const stageCard = h('div', { class: 'card-panel', style: { marginBottom: '14px' } },
    h('div', { class: 'panel-head' },
      h('span', { class: 'panel-title', text: 'Stages' }),
      h('span', { class: 'pill', text: String(stages.length) })),
    h('div', { class: 'panel-body' }));
  if (!stages.length) {
    stageCard.querySelector('.panel-body').appendChild(h('div', { class: 'hint', text: 'This board declares no stages.' }));
  } else {
    for (const stage of stages) {
      const total = Array.isArray(stage.tasks) ? stage.tasks.length : 0;
      const open = Array.isArray(stage.tasks_open) ? stage.tasks_open.length : 0;
      const done = Math.max(0, total - open);
      const decision = stage.owner_decision || 'continue';
      const decisionSelect = h('select', {
        class: 'select', 'aria-label': 'Owner decision for ' + (stage.title || stage.id),
        disabled: !canWrite(),
        on: { change: (event) => setStageDecision(stage.id, event.target.value) }
      }, ['pending', 'continue', 'stop'].map((value) => {
        const option = h('option', { value: value, text: value });
        if (decision === value) option.selected = true;
        return option;
      }));
      stageCard.querySelector('.panel-body').appendChild(h('div', { class: 'stage-row' },
        h('div', { class: 'stage-row-main' },
          h('div', { class: 'stage-row-title' },
            h('span', { class: 'chip mono', text: '#' + stage.index }),
            h('span', { text: stage.title || stage.id }),
            h('span', { class: 'pill', text: done + '/' + total + ' tasks' }),
            stage.complete ? h('span', { class: 'pill pill-ok', text: 'complete' }) : null,
            stage.stopped ? h('span', { class: 'pill pill-danger', text: 'stopped' }) : null,
            stage.owner_pending ? h('span', { class: 'pill pill-warn', text: 'owner pending' }) : null),
          stage.goal ? h('div', { class: 'stage-row-goal', text: stage.goal }) : null,
          h('div', { class: 'stage-row-flags' },
            (stage.exit_gates || []).map((gate) => h('span', {
              class: 'chip ' + ((stage.missing_gates || []).indexOf(gate) === -1 ? 'chip-pass' : 'chip-miss'),
              text: gate
            })),
            (stage.tasks && stage.tasks.length) ? h('span', { class: 'chip', text: stage.tasks.join(', ') }) : null)),
        h('div', { class: 'stage-controls' },
          h('button', {
            class: 'btn btn-sm btn-icon', type: 'button', text: '↑', 'aria-label': 'Move stage earlier',
            disabled: !canWrite() || stage.index <= 1,
            title: 'POST /api/plan/stages/<id>/move',
            on: { click: () => moveStage(stage.id, -1) }
          }),
          h('button', {
            class: 'btn btn-sm btn-icon', type: 'button', text: '↓', 'aria-label': 'Move stage later',
            disabled: !canWrite() || stage.index >= stages.length,
            on: { click: () => moveStage(stage.id, 1) }
          }),
          decisionSelect)));
    }
  }
  dom.view.appendChild(stageCard);

  /* tasks */
  const taskCard = h('div', { class: 'card-panel' },
    h('div', { class: 'panel-head' },
      h('span', { class: 'panel-title', text: 'Tasks' }),
      h('span', { class: 'pill', text: String(tasks.length) })),
    h('div', { class: 'panel-body' }));
  if (!tasks.length) {
    taskCard.querySelector('.panel-body').appendChild(emptyState('No tasks yet', 'Create the first task to start planning.', null));
  } else {
    for (const task of tasks) {
      const editable = task.status !== 'done';
      const deletable = ['pending', 'blocked', 'failed'].indexOf(task.status) !== -1;
      taskCard.querySelector('.panel-body').appendChild(h('div', { class: 'plan-task-row' },
        h('div', { class: 'plan-task-main' },
          h('div', { class: 'row-wrap' },
            h('span', { class: 'mono', style: { fontSize: '11px', color: 'var(--muted)' }, text: task.id }),
            statusPill(task.status),
            h('span', { class: 'plan-task-title', text: task.title || '(untitled)' })),
          h('div', { class: 'plan-task-meta' },
            h('span', { class: 'chip', text: task.stage_title || String(task.stage || '') }),
            h('span', { class: 'chip', text: 'complexity ' + (task.complexity !== undefined ? task.complexity : '—') }),
            (task.depends_on || []).length ? h('span', { class: 'chip', text: 'deps ' + task.depends_on.join(', ') }) : null,
            (task.gates || []).length ? h('span', { class: 'chip', text: 'gates ' + task.gates.join(', ') }) : null)),
        h('div', { class: 'plan-task-actions' },
          h('button', {
            class: 'btn btn-sm', type: 'button', text: 'Template',
            disabled: !canWrite(),
            title: canWrite() ? 'Save this task shape as a template' : 'The dashboard is read-only',
            on: { click: () => openSaveTemplateModal(task.id) }
          }),
          h('button', {
            class: 'btn btn-sm', type: 'button', text: 'Edit',
            disabled: !canWrite() || !editable,
            title: editable ? 'PATCH /api/plan/tasks/' + task.id : 'A done task is reopened before its plan is edited',
            on: { click: () => openTaskEditor(task.id) }
          }),
          h('button', {
            class: 'btn btn-sm btn-danger', type: 'button', text: 'Delete',
            disabled: !canWrite() || !deletable,
            title: deletable ? 'DELETE /api/plan/tasks/' + task.id : 'Only pending, blocked or failed tasks can be deleted',
            on: { click: () => deleteTask(task.id) }
          }))));
    }
  }
  dom.view.appendChild(taskCard);
}

async function saveInterviewAnswersFromPlan() {
  const saved = await saveInterviewAnswers();
  if (!saved) return;
  state.interviewOpen = false;
  renderView();
}

async function setStageDecision(stageId, decision) {
  try {
    await api('/api/plan/stages/' + encodeURIComponent(stageId) + '/decision', {
      method: 'POST', body: { decision: decision }
    });
    toast('Stage ' + stageId + ' decision: ' + decision, 'ok');
    await loadSnapshot();
    await loadPlan();
    renderView();
  } catch (err) {
    toast('Stage decision failed: ' + describeError(err), 'error');
    await loadSnapshot();
    renderView();
  }
}

async function moveStage(stageId, delta) {
  try {
    await api('/api/plan/stages/' + encodeURIComponent(stageId) + '/move', {
      method: 'POST', body: { delta: delta }
    });
    toast('Stage moved', 'ok');
    await loadSnapshot();
    await loadPlan();
    renderView();
  } catch (err) {
    toast('Move failed: ' + describeError(err), 'error');
  }
}

/* ---------- plan task editor ---------- */

function openTaskEditor(taskId) {
  const isCreate = !taskId;
  const task = taskId ? taskById(taskId) : null;
  if (!isCreate && !task) { toast('Unknown task ' + taskId, 'error'); return; }
  const stages = (state.snapshot && state.snapshot.stages) || [];
  const allTasks = ((state.snapshot && state.snapshot.tasks) || []).filter((item) => item.id !== taskId);
  const templates = state.templates || [];

  const titleInput = h('input', { class: 'input', type: 'text', value: (task && task.title) || '', 'data-autofocus': '1' });
  const goalInput = h('textarea', { class: 'textarea', rows: '3' });
  goalInput.value = (task && task.goal) || '';
  const whyInput = h('textarea', { class: 'textarea', rows: '2' });
  whyInput.value = (task && task.why) || '';
  const scopeInput = h('textarea', { class: 'textarea', rows: '4', placeholder: 'One path per line' });
  scopeInput.value = ((task && task.scope_write) || []).join('\n');
  const acceptanceInput = h('textarea', { class: 'textarea', rows: '3', placeholder: 'One acceptance criterion per line' });
  acceptanceInput.value = ((task && task.acceptance) || []).join('\n');
  const gatesInput = h('input', { class: 'input', type: 'text', placeholder: 'layout, tests' });
  gatesInput.value = ((task && task.gates) || []).join(', ');
  const packageInput = h('input', { class: 'input', type: 'text', placeholder: 'optional package path' });
  packageInput.value = (task && task.package) || '';
  const groupInput = h('input', { class: 'input', type: 'text', placeholder: 'optional parallel group' });
  groupInput.value = (task && task.parallel_group) || '';
  const complexityInput = h('input', { class: 'input', type: 'number', min: '1', max: '10', value: String((task && task.complexity) || 2) });
  const estimateInput = h('input', {
    class: 'input', type: 'number', min: '0', max: '10000', step: '0.5',
    placeholder: 'hours',
    value: task && task.estimate_hours !== null && task.estimate_hours !== undefined ? String(task.estimate_hours) : ''
  });
  const ownerInput = h('input', { class: 'input', type: 'text', placeholder: 'optional owner', value: (task && task.owner) || '' });
  const idInput = h('input', { class: 'input', type: 'text', placeholder: 'auto (e.g. T-01)', value: (task && task.id) || '', disabled: !isCreate });
  const labelsHost = labelCheckboxHost(task, null);

  const stageSelect = h('select', { class: 'select', 'aria-label': 'Stage' });
  const stageIds = stages.map((stage) => stage.id);
  for (const stage of stages) {
    const option = h('option', { value: stage.id, text: stage.title ? stage.title + ' (' + stage.id + ')' : stage.id });
    if ((task && task.stage === stage.id) || (!task && stageIds.length && stage.id === stageIds[0])) option.selected = true;
    stageSelect.appendChild(option);
  }

  const depGrid = h('div', { class: 'dep-grid', 'aria-label': 'Depends on' });
  const currentDeps = (task && task.depends_on) || [];
  if (!allTasks.length) depGrid.appendChild(h('span', { class: 'hint', text: 'No other tasks yet.' }));
  for (const other of allTasks) {
    depGrid.appendChild(h('label', { class: 'checkbox' },
      h('input', { type: 'checkbox', value: other.id, checked: currentDeps.indexOf(other.id) !== -1 }),
      h('span', { class: 'truncate', title: other.title || '', text: other.id + ' · ' + (other.title || '') })));
  }

  /* template picker (create only) */
  let templateSelect = null;
  let templatePreview = null;
  if (isCreate) {
    templateSelect = h('select', { class: 'select', 'aria-label': 'Task template' },
      h('option', { value: '', text: 'No template' }),
      templates.map((template) => h('option', { value: template.id, text: (template.name || template.id) + ' (' + template.id + ')' })));
    templatePreview = h('div', { class: 'template-preview', text: 'Pick a template to pre-fill scope, acceptance, gates, effort, package, owner and labels.' });
    templateSelect.addEventListener('change', () => {
      const template = templateById(templateSelect.value);
      if (!template) { templatePreview.textContent = 'Pick a template to pre-fill the task shape.'; return; }
      if (template.title) titleInput.value = template.title;
      if (template.goal) goalInput.value = template.goal;
      if (template.why) whyInput.value = template.why;
      if (template.stage && stageIds.indexOf(template.stage) !== -1) stageSelect.value = template.stage;
      if (template.package) packageInput.value = template.package;
      if (template.parallel_group) groupInput.value = template.parallel_group;
      if (template.owner) ownerInput.value = template.owner;
      if (template.complexity !== null && template.complexity !== undefined) complexityInput.value = String(template.complexity);
      estimateInput.value = template.estimate_hours !== null && template.estimate_hours !== undefined ? String(template.estimate_hours) : '';
      scopeInput.value = (template.scope_write || []).join('\n');
      acceptanceInput.value = (template.acceptance || []).join('\n');
      gatesInput.value = (template.gates || []).join(', ');
      for (const box of labelsHost.querySelectorAll('input[type="checkbox"]')) {
        box.checked = (template.labels || []).indexOf(box.value) !== -1;
      }
      templatePreview.replaceChildren(templateChips(template));
    });
  }

  const errorBox = h('div');
  const footer = [];
  const saveButton = h('button', {
    class: 'btn btn-primary', type: 'button', text: isCreate ? 'Create task' : 'Save changes',
    on: {
      click: () => saveTaskFromEditor({
        isCreate, taskId, idInput, titleInput, goalInput, whyInput, scopeInput, acceptanceInput,
        gatesInput, packageInput, groupInput, complexityInput, estimateInput, ownerInput,
        labelsHost, stageSelect, depGrid, errorBox, saveButton, templateSelect
      })
    }
  });
  if (!isCreate) {
    footer.push(h('button', {
      class: 'btn btn-danger', type: 'button', text: 'Delete task',
      on: { click: async () => { closeModal(); await deleteTask(taskId); } }
    }));
  }
  footer.push(h('button', { class: 'btn', type: 'button', text: 'Cancel', on: { click: () => closeModal() } }));
  footer.push(saveButton);

  const body = h('div', { class: 'plan-editor' },
    errorBox,
    isCreate && templateSelect
      ? h('div', { class: 'editor-template-bar' },
        h('label', { class: 'field' },
          h('span', { class: 'field-label', text: 'Start from a template' }), templateSelect,
          h('span', { class: 'field-help', text: 'Pre-fills the shape; fields you edit win. The template id is sent to the server too.' })),
        templatePreview)
      : null,
    h('div', { class: 'form-grid' },
      h('label', { class: 'field' },
        h('span', { class: 'field-label', text: 'Task ID' }), idInput,
        h('span', { class: 'field-help', text: isCreate ? 'Leave empty to let the server pick the next free ID.' : 'The ID is stable once created.' })),
      h('label', { class: 'field' }, h('span', { class: 'field-label', text: 'Stage' }), stageSelect),
      h('label', { class: 'field' }, h('span', { class: 'field-label', text: 'Owner' }), ownerInput),
      h('label', { class: 'field' },
        h('span', { class: 'field-label', text: 'Title' }), titleInput),
      h('label', { class: 'field span-2' },
        h('span', { class: 'field-label', text: 'Goal' }), goalInput),
      h('label', { class: 'field span-2' },
        h('span', { class: 'field-label', text: 'Why' }), whyInput),
      h('label', { class: 'field' },
        h('span', { class: 'field-label', text: 'Scope (write)' }), scopeInput,
        h('span', { class: 'field-help', text: 'One repository path per line.' })),
      h('label', { class: 'field' },
        h('span', { class: 'field-label', text: 'Acceptance' }), acceptanceInput,
        h('span', { class: 'field-help', text: 'One criterion per line.' })),
      h('label', { class: 'field' },
        h('span', { class: 'field-label', text: 'Gates' }), gatesInput,
        h('span', { class: 'field-help', text: 'Comma-separated gate names.' })),
      h('label', { class: 'field' }, h('span', { class: 'field-label', text: 'Complexity' }), complexityInput),
      h('label', { class: 'field' },
        h('span', { class: 'field-label', text: 'Estimate (hours)' }), estimateInput,
        h('span', { class: 'field-help', text: 'Empty clears the estimate.' })),
      h('label', { class: 'field' }, h('span', { class: 'field-label', text: 'Package' }), packageInput),
      h('label', { class: 'field' }, h('span', { class: 'field-label', text: 'Parallel group' }), groupInput),
      h('div', { class: 'field span-2' },
        h('span', { class: 'field-label', text: 'Labels' }), labelsHost),
      h('div', { class: 'field span-2' },
        h('span', { class: 'field-label', text: 'Depends on' }), depGrid)),
  );

  openModal({ title: isCreate ? 'Create a task' : 'Edit ' + taskId, body: body, footer: footer });
}

async function saveTaskFromEditor(context) {
  const lines = (value) => String(value || '').split('\n').map((line) => line.trim()).filter(Boolean);
  const comma = (value) => String(value || '').split(',').map((part) => part.trim()).filter(Boolean);
  const deps = [];
  for (const box of context.depGrid.querySelectorAll('input[type="checkbox"]')) {
    if (box.checked) deps.push(box.value);
  }
  const labels = [];
  for (const box of context.labelsHost.querySelectorAll('input[type="checkbox"]')) {
    if (box.checked) labels.push(box.value);
  }
  const estimateText = String(context.estimateInput.value || '').trim();
  const payload = {
    title: context.titleInput.value.trim(),
    goal: context.goalInput.value.trim(),
    why: context.whyInput.value.trim() || null,
    scope_write: lines(context.scopeInput.value),
    acceptance: lines(context.acceptanceInput.value),
    gates: comma(context.gatesInput.value),
    stage: context.stageSelect.value,
    complexity: Number(context.complexityInput.value) || 2,
    depends_on: deps,
    package: context.packageInput.value.trim() || null,
    parallel_group: context.groupInput.value.trim() || null,
    owner: context.ownerInput.value.trim() || null,
    labels: labels,
    estimate_hours: estimateText === '' ? null : Number(estimateText)
  };
  if (estimateText !== '' && (!isFinite(Number(estimateText)) || Number(estimateText) < 0)) {
    context.errorBox.replaceChildren(errorCallout(new ApiError('Estimate must be a number.', 400, null)));
    return;
  }
  if (context.isCreate) {
    const explicitId = context.idInput && context.idInput.value ? context.idInput.value.trim() : '';
    if (explicitId) payload.id = explicitId;
    if (context.templateSelect && context.templateSelect.value) payload.template = context.templateSelect.value;
  }

  if (!payload.title) { context.errorBox.replaceChildren(errorCallout(new ApiError('A title is required.', 400, null))); return; }
  if (!payload.goal) { context.errorBox.replaceChildren(errorCallout(new ApiError('A goal is required.', 400, null))); return; }

  context.saveButton.disabled = true;
  context.errorBox.replaceChildren();
  try {
    if (context.isCreate) {
      const created = await api('/api/plan/tasks', { method: 'POST', body: payload });
      toast('Task ' + ((created && created.id) || payload.id || '') + ' created', 'ok');
    } else {
      await api('/api/plan/tasks/' + encodeURIComponent(context.taskId), { method: 'PATCH', body: payload });
      toast('Task ' + context.taskId + ' updated', 'ok');
    }
    closeModal();
    await Promise.all([loadSnapshot(), loadPlan()]);
    renderHeader();
    renderTabs();
    renderView();
  } catch (err) {
    context.errorBox.replaceChildren(errorCallout(err));
    toast('Save failed: ' + describeError(err), 'error');
    context.saveButton.disabled = false;
  }
}

async function deleteTask(taskId) {
  const allowed = await confirmDialog({
    title: 'Delete task ' + taskId + '?',
    message: 'The task is removed from board.json. Only pending, blocked or failed tasks can be deleted, and nothing may depend on it.',
    confirmLabel: 'Delete task'
  });
  if (!allowed) return;
  try {
    await api('/api/plan/tasks/' + encodeURIComponent(taskId), { method: 'DELETE' });
    toast('Task ' + taskId + ' deleted', 'ok');
    await Promise.all([loadSnapshot(), loadPlan()]);
    renderHeader();
    renderTabs();
    renderView();
  } catch (err) {
    state.planError = err;
    toast('Delete failed: ' + describeError(err), 'error');
    renderView();
  }
}
/* =========================================================================
   30. Start
   ========================================================================= */

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', boot);
} else {
  boot();
}
