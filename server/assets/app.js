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
  { key: 'board', label: 'Board' },
  { key: 'table', label: 'Table' },
  { key: 'graph', label: 'Graph' },
  { key: 'dispatch', label: 'Dispatch' },
  { key: 'approvals', label: 'Approvals' },
  { key: 'activity', label: 'Activity' },
  { key: 'sessions', label: 'Sessions' },
  { key: 'plan', label: 'Plan' }
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

function inlineNodes(text) {
  const nodes = [];
  const source = String(text);
  const pattern = /(`[^`]+`|\*\*[^*]+\*\*|\*[^*\s][^*]*\*)/g;
  let last = 0;
  let match = pattern.exec(source);
  while (match) {
    if (match.index > last) nodes.push(document.createTextNode(source.slice(last, match.index)));
    const token = match[0];
    if (token.charAt(0) === '`') {
      nodes.push(h('code', { class: 'md-inline-code', text: token.slice(1, -1) }));
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

function mdFragment(text) {
  const fragment = document.createDocumentFragment();
  if (text === null || text === undefined || String(text) === '') return fragment;
  const lines = String(text).replace(/\r\n?/g, '\n').split('\n');
  let index = 0;
  let paragraph = [];

  const flush = () => {
    if (!paragraph.length) return;
    const node = h('p');
    append(node, inlineNodes(paragraph.join(' ')));
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
      append(node, inlineNodes(heading[2].trim()));
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
        append(item, inlineNodes(lines[index].replace(/^\s*[-*+]\s+/, '')));
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
        append(item, inlineNodes(lines[index].replace(/^\s*\d+[.)]\s+/, '')));
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
      append(quote, inlineNodes(buffer.join(' ')));
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

    if (line.trim() === '') {
      flush();
      index += 1;
      continue;
    }

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
  packageOptions: null
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
  if (!raw.startsWith('#/')) return { view: 'board', taskId: null };
  const parts = raw.slice(2).split('/').filter(Boolean);
  const known = VIEWS.some((view) => view.key === parts[0]);
  const view = known ? parts[0] : 'board';
  let taskId = null;
  if (parts[1]) {
    try { taskId = decodeURIComponent(parts[1]); } catch (err) { taskId = parts[1]; }
  }
  return { view, taskId };
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
  renderView();

  if (parsed.taskId) ensureDrawer(parsed.taskId);
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
}

/* =========================================================================
   12. Header, tabs, live indicator
   ========================================================================= */

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
  if (config && config.version) dom.projectName.title = 'Polier dashboard ' + config.version;
  const writable = canWrite();
  dom.checkButton.disabled = !writable;
  dom.auditButton.disabled = !writable;
  dom.checkButton.title = writable ? 'Run the board check job (POST /api/jobs/check)' : 'The dashboard is read-only';
  dom.auditButton.title = writable ? 'Run the project audit job (POST /api/jobs/audit)' : 'The dashboard is read-only';
  paintJobsButtonState();
}

function renderTabs() {
  clear(dom.tabs);
  const snapshot = state.snapshot;
  const counts = {
    approvals: snapshot && snapshot.approvals && snapshot.approvals.pending ? snapshot.approvals.pending.length : 0
  };
  for (const view of VIEWS) {
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
  // `?noevents=1` freezes live updates: useful for screenshots, print views and
  // reading a page on a static host. Explicit "Refresh" buttons still refetch.
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
  if (!state.packageOptions) await loadPackageOptions();
  renderHeader();
  renderTabs();
  if (state.route.taskId) loadDrawer(state.route.taskId, true);
  const view = state.route.view;
  if (view === 'dispatch') await loadDispatch();
  else if (view === 'approvals') await loadApprovals();
  else if (view === 'activity') await loadActivity();
  else if (view === 'plan') await loadPlan();
  else if (view === 'sessions') await loadSessions({ quiet: true });
  renderView();
  renderJobsTray();
  if (state.jobsOpen) loadJobs();
}

async function loadViewData(view) {
  const startedView = view;
  if (view === 'dispatch') {
    await loadDispatch();
    if (state.route.view === startedView) renderView();
    return;
  }
  if (view === 'approvals') {
    await Promise.all([(!state.snapshot && !state.noBoard && !state.snapshotError) ? loadSnapshot() : Promise.resolve(), loadApprovals()]);
    if (state.route.view === startedView) renderView();
    return;
  }
  if (view === 'activity') {
    await loadActivity();
    if (state.route.view === startedView) renderView();
    return;
  }
  if (view === 'sessions') {
    await loadSessions();
    if (state.route.view === startedView) renderView();
    return;
  }
  if (view === 'plan') {
    await Promise.all([loadPlan(), loadSnapshot()]);
    if (state.route.view === startedView) renderView();
    return;
  }
  if (!state.snapshot && !state.noBoard && !state.snapshotError) {
    await loadSnapshot();
    if (state.route.view === startedView) renderView();
  }
  if (!state.packageOptions && !state.noBoard) {
    await loadPackageOptions();
    if (state.route.view === startedView) renderView();
  }
}

/* =========================================================================
   15. View dispatch
   ========================================================================= */

function renderView() {
  if (!dom.view) return;
  const focus = captureFocus();
  clear(dom.view);
  const view = state.route.view;

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
    case 'board': renderBoard(); break;
    case 'table': renderTable(); break;
    case 'graph': renderGraph(); break;
    case 'dispatch': renderDispatch(); break;
    case 'approvals': renderApprovals(); break;
    case 'activity': renderActivity(); break;
    case 'sessions': renderSessions(); break;
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
  return applyFilters((state.snapshot && state.snapshot.tasks) || []);
}

function renderFilters(options) {
  const opts = options || {};
  const wrap = h('div', { class: 'filters' });
  const textInput = h('input', {
    class: 'input filter-text', type: 'search', placeholder: 'Filter by id, title, owner…',
    value: state.filters.text, 'aria-label': 'Filter tasks', 'data-fkey': 'filter-text',
    on: {
      input: (event) => {
        state.filters.text = event.target.value;
        scheduleFilterRender();
      }
    }
  });
  wrap.appendChild(textInput);

  const stageSelect = filterSelect('stage', 'All stages', filterValues('stage'), (value) => {
    state.filters.stage = value;
    rerenderWithFocus();
  });
  if (stageSelect) wrap.appendChild(stageSelect);

  const packageOptions = filterValues('package');
  if (packageOptions.length) {
    wrap.appendChild(filterSelect('package', 'All packages', packageOptions, (value) => {
      state.filters.package = value;
      rerenderWithFocus();
    }));
  }

  const ownerOptions = filterValues('owner');
  if (ownerOptions.length > 1) {
    wrap.appendChild(filterSelect('owner', 'All owners', ownerOptions, (value) => {
      state.filters.owner = value;
      rerenderWithFocus();
    }));
  }

  const active = Boolean(state.filters.text || state.filters.stage || state.filters.package || state.filters.owner);
  if (active) {
    wrap.appendChild(h('button', {
      class: 'btn btn-ghost btn-sm', type: 'button', text: 'Clear',
      on: {
        click: () => {
          state.filters = { text: '', stage: '', package: '', owner: '' };
          syncSearchInput();
          rerenderWithFocus();
        }
      }
    }));
  }

  if (opts.count !== false) {
    const total = (state.snapshot && state.snapshot.tasks ? state.snapshot.tasks.length : 0);
    const shown = visibleTasks().length;
    wrap.appendChild(h('span', {
      class: 'filter-count',
      text: active ? shown + ' of ' + total + ' tasks' : total + ' ' + plural(total, 'task')
    }));
  }
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
  bindStatic();
  renderTabs();
  renderHeader();

  await loadConfig();
  await loadSnapshot();
  if (!state.noBoard) await loadPackageOptions();

  const known = location.hash && location.hash.startsWith('#/');
  if (!known) {
    const startView = state.config && state.config.board_present === false ? 'plan' : (state.noBoard ? 'plan' : 'board');
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

  dom.view.appendChild(h('div', { class: 'view-head' },
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

  dom.view.appendChild(renderFilters());

  if (!tasks.length) {
    dom.view.appendChild(emptyState('No tasks on the board',
      'The board exists but has no tasks yet. Add tasks in the Plan view.',
      h('button', { class: 'btn btn-primary', type: 'button', text: 'Open plan', on: { click: () => navigate('plan') } })));
    return;
  }

  const filtered = visibleTasks();
  if (!filtered.length) {
    dom.view.appendChild(emptyState('No matching tasks', 'Adjust the filters or clear them to see the whole board.',
      h('button', {
        class: 'btn', type: 'button', text: 'Clear filters',
        on: {
          click: () => {
            state.filters = { text: '', stage: '', package: '', owner: '' };
            syncSearchInput();
            renderView();
          }
        }
      })));
    return;
  }

  const wrap = h('div', { class: 'board-wrap' });
  const board = h('div', { class: 'board' });
  for (const column of COLUMNS) {
    board.appendChild(renderColumn(column, filtered));
  }
  wrap.appendChild(board);
  wrap.appendChild(renderStagePanel());
  dom.view.appendChild(wrap);
}

function refreshSnapshotButton() {
  loadSnapshot({ fresh: true }).then(() => {
    renderHeader();
    renderView();
  });
}

function renderColumn(column, tasks) {
  const members = tasks.filter((task) => column.statuses.indexOf(task.status) !== -1);
  const collapsed = column.key === 'done' ? !state.boardDoneOpen : false;
  const node = h('section', {
    class: 'column',
    dataset: { collapsed: collapsed ? 'true' : 'false', column: column.key },
    'aria-label': column.label + ' column'
  });

  const header = h('header', { class: 'column-head' },
    statusDot(column.statuses[0]),
    h('span', { class: 'column-name', text: column.label }),
    h('span', { class: 'column-count', text: String(members.length) }));
  node.appendChild(header);

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
  if (!members.length) {
    list.appendChild(h('div', { class: 'column-empty', text: '—' }));
  } else {
    for (const task of members) list.appendChild(renderTaskCard(task));
  }
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

function renderTaskCard(task) {
  const meta = stMeta(task.status);
  const gates = task.gates || [];
  const passed = (task.gates_passed || []).length;
  const claim = task.claim;
  const ownerText = task.owner || 'unassigned';

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

  card.appendChild(h('div', { class: 'task-card-top' },
    h('span', { class: 'task-card-id', text: task.id }),
    h('span', { class: 'badge bg-' + meta.color + ' st-' + meta.color }, h('span', { class: 'dot' }), meta.label),
    claim ? h('span', {
      class: 'claim-badge',
      title: 'Claimed by ' + (claim.harness || 'session') + (claim.session ? ' · ' + claim.session : '')
    }, h('span', { class: 'dot' }), 'claimed') : null));

  card.appendChild(h('div', { class: 'task-card-title', text: task.title || '(untitled)' }));

  card.appendChild(h('div', { class: 'task-card-meta' },
    h('span', { text: task.stage_title || String(task.stage || '—') }),
    h('span', { class: 'sep', text: '·' }),
    h('span', { text: ownerText }),
    task.wave !== null && task.wave !== undefined ? h('span', { class: 'sep', text: '·' }) : null,
    task.wave !== null && task.wave !== undefined ? h('span', { text: 'wave ' + (task.wave + 1) }) : null));

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

  dom.view.appendChild(h('div', { class: 'view-head' },
    h('div', {},
      h('h1', { class: 'view-title', text: 'Table' }),
      h('p', {
        class: 'view-sub',
        text: [tasks.length + ' ' + plural(tasks.length, 'task'),
          project.profile ? 'profile ' + project.profile : ''].filter(Boolean).join(' · ')
      })),
    h('div', { class: 'view-actions' },
      h('button', { class: 'btn btn-sm', type: 'button', text: 'Refresh', on: { click: () => refreshSnapshotButton() } }))));

  dom.view.appendChild(renderFilters());

  if (!tasks.length) {
    dom.view.appendChild(emptyState('No tasks on the board', 'Add tasks in the Plan view.', null));
    return;
  }

  const filtered = visibleTasks();
  const table = h('table', { class: 'table' });
  const thead = h('thead');
  const headRow = h('tr');
  for (const label of ['Task', 'Status', 'Stage', 'Owner', 'Gates', 'Tokens', 'Attempts', 'Depends on', 'Package']) {
    headRow.appendChild(h('th', { text: label }));
  }
  thead.appendChild(headRow);
  table.appendChild(thead);

  const tbody = h('tbody');
  if (!filtered.length) {
    tbody.appendChild(h('tr', { class: 'empty-row' },
      h('td', { colspan: '9', text: 'No tasks match the current filters.' })));
  }
  for (const task of filtered) {
    const meta = stMeta(task.status);
    const gates = task.gates || [];
    const passed = (task.gates_passed || []).length;
    const maxTokens = task.budget && task.budget.max ? Number(task.budget.max) : 0;
    const used = Number(task.tokens) || 0;
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
    row.appendChild(h('td', { class: 'cell-task' },
      h('div', { class: 'cell-task-title', text: task.title || '(untitled)' }),
      h('div', { class: 'cell-mono', text: task.id })));
    row.appendChild(h('td', {}, statusPill(task.status)));
    row.appendChild(h('td', { class: 'nowrap', text: task.stage_title || String(task.stage || '—') }));
    row.appendChild(h('td', { class: 'nowrap', text: task.owner || '—' }));
    row.appendChild(h('td', { class: 'cell-gates' },
      gates.length
        ? h('div', { class: 'gate-mini' },
          h('span', { class: 'mini-num', text: passed + '/' + gates.length }),
          progressBar(passed, gates.length, passed === gates.length ? 'is-ok' : ''))
        : h('span', { class: 'faint', text: '—' })));
    row.appendChild(h('td', {},
      h('span', { class: 'cell-mono', text: maxTokens ? fmtTokens(used) + ' / ' + fmtTokens(maxTokens) : fmtTokens(used) }),
      maxTokens ? progressBar(used, maxTokens, task.budget && task.budget.over ? 'is-over' : (task.budget && task.budget.warn ? 'is-warn' : '')) : null));
    row.appendChild(h('td', { class: 'cell-mono', text: String(task.attempt || 0) + (task.max_attempts ? ' / ' + task.max_attempts : '') }));
    const deps = task.depends_on || [];
    row.appendChild(h('td', { class: 'cell-dep' },
      deps.length
        ? h('div', { class: 'row-wrap', style: { gap: '3px' } }, deps.map((dep) => taskChip(dep)))
        : h('span', { class: 'faint', text: '—' })));
    row.appendChild(h('td', { class: 'nowrap', text: task.package || '—' }));
    tbody.appendChild(row);
  }
  table.appendChild(tbody);

  const wrap = h('div', { class: 'table-wrap' }, table);
  dom.view.appendChild(wrap);
  if (filtered.length) {
    dom.view.appendChild(h('p', {
      class: 'hint', style: { marginTop: '8px' },
      text: 'Click a row to open the task drawer; gates, tokens, attempts and dependencies come straight from the snapshot.'
    }));
  }
}
/* =========================================================================
   23. Task detail drawer
   ========================================================================= */

const DRAWER_TABS = [
  { key: 'brief', label: 'Brief' },
  { key: 'gates', label: 'Gates' },
  { key: 'run', label: 'Run' },
  { key: 'review', label: 'Review' },
  { key: 'evidence', label: 'Evidence' },
  { key: 'handoff', label: 'Handoff' },
  { key: 'session', label: 'Session' }
];

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
  if (updateHash) navigate(state.route.view, null);
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
  const focusSnapshot = captureFocus();
  const task = currentDrawerTask();
  const detail = state.drawer.detail;
  const meta = stMeta(task.status);
  clear(dom.drawer);

  const head = h('div', { class: 'drawer-head' });

  /* top row */
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

  /* meta pills */
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
  for (const tab of DRAWER_TABS) {
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
  switch (state.drawer.tab) {
    case 'gates': return drawerGatesTab(task, detail);
    case 'run': return drawerRunTab(task, detail);
    case 'review': return drawerReviewTab(task, detail);
    case 'evidence': return drawerEvidenceTab(task, detail);
    case 'handoff': return drawerHandoffTab(task, detail);
    case 'session': return drawerSessionTab(task, detail);
    default: return drawerBriefTab(task, detail);
  }
}

function drawerBriefTab(task, detail) {
  const body = h('div');
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

  dom.view.appendChild(renderFilters({ count: false }));

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
  const idInput = h('input', { class: 'input', type: 'text', placeholder: 'auto (e.g. T-01)', value: (task && task.id) || '', disabled: !isCreate });

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
    const box = h('label', { class: 'checkbox' },
      h('input', { type: 'checkbox', value: other.id, checked: currentDeps.indexOf(other.id) !== -1 }),
      h('span', { class: 'truncate', title: other.title || '', text: other.id + ' · ' + (other.title || '') }));
    depGrid.appendChild(box);
  }

  const errorBox = h('div');
  const footer = [];
  const saveButton = h('button', {
    class: 'btn btn-primary', type: 'button', text: isCreate ? 'Create task' : 'Save changes',
    on: { click: () => saveTaskFromEditor({ isCreate, taskId, idInput, titleInput, goalInput, whyInput, scopeInput, acceptanceInput, gatesInput, packageInput, groupInput, complexityInput, stageSelect, depGrid, errorBox, saveButton }) }
  });
  if (!isCreate) {
    footer.push(h('button', {
      class: 'btn btn-danger', type: 'button', text: 'Delete task',
      on: {
        click: async () => {
          closeModal();
          await deleteTask(taskId);
        }
      }
    }));
  }
  footer.push(h('button', { class: 'btn', type: 'button', text: 'Cancel', on: { click: () => closeModal() } }));
  footer.push(saveButton);

  const body = h('div', { class: 'plan-editor' },
    errorBox,
    h('div', { class: 'form-grid' },
      h('label', { class: 'field' },
        h('span', { class: 'field-label', text: 'Task ID' }), idInput,
        h('span', { class: 'field-help', text: isCreate ? 'Leave empty to let the server pick the next free ID.' : 'The ID is stable once created.' })),
      h('label', { class: 'field' },
        h('span', { class: 'field-label', text: 'Stage' }), stageSelect),
      h('label', { class: 'field span-2' },
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
      h('label', { class: 'field' },
        h('span', { class: 'field-label', text: 'Complexity' }), complexityInput),
      h('label', { class: 'field' },
        h('span', { class: 'field-label', text: 'Package' }), packageInput),
      h('label', { class: 'field' },
        h('span', { class: 'field-label', text: 'Parallel group' }), groupInput),
      h('div', { class: 'field span-2' },
        h('span', { class: 'field-label', text: 'Depends on' }), depGrid)),
  );

  openModal({
    title: isCreate ? 'Create a task' : 'Edit ' + taskId,
    body: body,
    footer: footer
  });
}

async function saveTaskFromEditor(context) {
  const lines = (value) => String(value || '').split('\n').map((line) => line.trim()).filter(Boolean);
  const comma = (value) => String(value || '').split(',').map((part) => part.trim()).filter(Boolean);
  const deps = [];
  for (const box of context.depGrid.querySelectorAll('input[type="checkbox"]')) {
    if (box.checked) deps.push(box.value);
  }
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
    parallel_group: context.groupInput.value.trim() || null
  };
  if (context.isCreate) {
    const explicitId = context.idInput && context.idInput.value ? context.idInput.value.trim() : '';
    if (explicitId) payload.id = explicitId;
  }

  if (!payload.title) { context.errorBox.replaceChildren(errorCallout(new ApiError('A title is required.', 400, null))); return; }
  if (!payload.goal) { context.errorBox.replaceChildren(errorCallout(new ApiError('A goal is required.', 400, null))); return; }

  context.saveButton.disabled = true;
  context.errorBox.replaceChildren();
  try {
    if (context.isCreate) {
      await api('/api/plan/tasks', { method: 'POST', body: payload });
      toast('Task ' + (payload.id || '') + ' created', 'ok');
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
