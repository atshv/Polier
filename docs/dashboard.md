# The dashboard (2.0)

A local, zero-dependency control plane for a Polier project: one page that shows
the plan, the execution state and the decisions, and can drive the same actions
the CLI offers. It is optional — every command still works without it, the
files stay the source of truth and nothing runs in the background unless you
start it.

```bash
git clone https://github.com/atshv/Polier && cd Polier
python3 tools/serve.py /path/to/project --port 8765 --open
```

The server binds to `127.0.0.1` by default, needs Python 3.9+ only, and serves
one self-contained page from `server/assets/`. Stop it with Ctrl+C.

![The board](images/dashboard.png)

## What the page can do

| View | What it shows / does |
|---|---|
| Board | Kanban columns for every status (`pending`, `in_progress`, `verifying`, `review`, `rework`, `blocked`, `failed`, `done`), gate progress, tokens against the budget, live claims; table view and stage/package/owner filters |
| Task drawer | brief, gates and records, run events, review verdict, evidence logs, handoff; status transitions, claim/release, gate runs, a worker/reviewer session |
| Approvals | pending/granted/denied records; request, grant and deny with a note |
| Dispatch | next wave, running attempts, blocked tasks with reasons, scope conflicts |
| Activity | run events, gate results, reviews and approvals, newest first |
| Graph | dependency DAG as SVG (column = depth, row = stage, colour = status) |
| Sessions | start a headless agent session for a task, watch its transcript, record tokens, stop it |
| Plan | the interview wizard for a greenfield project; plan editing for an existing board (tasks, dependencies, scopes, stage decisions) |
| Jobs | gate/check/audit runs with live logs and stop buttons |

![Task drawer](images/dashboard-detail.png)

## The project cockpit (2.1)

- **Settings** (`Settings` tab) edits the committed `dashboard.json` next to `board.json`: feature flags for optional views (future views default off), the label definitions (id, title, palette colour, group) and the owner handle used by "Your Work". Machine-local settings — session provider, gate commands, theme, read state — stay in the runtime folder. The CLI is `python3 tools/settings.py show|init|feature|me|label …`.
- **Labels** are optional task fields of board schema 1.1 (`labels: [ids]`); they never change the write scope. Add or edit definitions in Settings, then assign them in the task drawer or the plan editor; the plan editor upgrades a 0.9/1.0 board to 1.1 on first use. `tools/plan.py` accepts `--labels`.
- **Filters and views**: the filter bar builds bounded conditions (field, operator, value) for text, status, label, number, boolean and budget fields. The result can be saved as a committed `views/<id>.json` with grouping, sorting and columns; built-in views ("Ready now", "Blocked", "Review queue", "Over budget", "No estimate", "Mine") come from the code and never overwrite files. CLI: `python3 tools/views.py list|builtin|show|save|delete`.
- **Your Work** (`Your Work` tab) is the owner cockpit: my tasks, review queue, approvals, claims, blocked tasks, budget warnings, ready tasks and running sessions. The **inbox** (header bell, same tab) is one actionable feed — approvals, failed gates, blocked tasks, budget, review requests, failed sessions — with a local read/unread state. Nothing is project state; only read marks are stored (runtime).
- **Worklog**: the task drawer's Worklog tab shows attempts, gate records, sessions, token usage and durations; `estimate_hours` (schema 1.1) is compared with the actual hours (session time when sessions exist, otherwise the attempt window). Project and stage sums are available from `/api/worklog` and `polier_worklog`.

Reading the page without live updates: add `?noevents=1` (static mode) and
`?theme=light|dark` to freeze the theme; deep links are `#/board`, `#/table`,
`#/graph`, `#/dispatch`, `#/approvals`, `#/activity`, `#/sessions`, `#/plan`
and `#/board/<ID>` to open a task.

The page is read-only when you pass `--read-only` (or `--role viewer`); the
badge in the header shows it.

## Connecting your own Claude Code

The dashboard can drive headless sessions itself, and it can also let your
normal Claude Code session see the board through MCP.

**MCP (recommended first step).** Add the server to Claude Code:

```bash
claude mcp add polier -- python3 /path/to/Polier/tools/mcp.py --root /path/to/project
```

The tools are `polier_snapshot`, `polier_tasks`, `polier_task`,
`polier_dispatch`, `polier_show`, `polier_activity`, `polier_approvals`,
`polier_claims` (read) and `polier_state_set`, `polier_gate`, `polier_claim`,
`polier_release` (write; refused with `--read-only`). This is the smallest
integration: your interactive session stays your session, and the board is one
tool call away.

**Headless sessions.** The dashboard starts a provider command for a task in
the project (or in a fresh worktree) and streams its JSON events into the
session console:

```
python3 tools/session.py run M03 --role worker [--worktree] [--note "…"]
python3 tools/session.py list|show|stop …
```

Provider settings live in the dashboard config (see below). The default is the
Claude Code CLI in non-interactive mode:

```
claude -p --output-format stream-json --verbose --permission-mode acceptEdits \
  --allowedTools "Bash Read Write Edit Glob Grep TodoWrite" \
  --settings <generated settings.json> "<composed prompt>"
```

The generated settings file installs the shipped hooks
(`adapters/claude-code/hook.py`) with `POLIER_ROLE` and `POLIER_TASK` in the
environment, so a headless run is guarded like an interactive one: writes
outside the task scope are denied, the stop check runs, denied commands are
refused. The session records the token use reported by the provider in
`runs/<ID>.json`; a task with a running session keeps its claim until the run
ends.

Roles: `worker` (implements the task), `reviewer` (writes `reviews/<ID>.md`
with a `verdict:` line), `lead` (runs gates and status changes), `generator`
(the planning session below).

**Security.** Sessions run arbitrary agent commands in your project; they are
started explicitly by you from the dashboard or the CLI, with the same hooks and
scope rules as an interactive session. The dashboard itself binds to loopback,
needs the `X-Polier-Action: 1` header for writes, rejects cross-origin writes and
can require a bearer token:

```bash
POLIER_DASHBOARD_TOKEN=… python3 tools/serve.py . --port 8765
```

Never expose the dashboard to a network without a token and a reverse proxy.

## The interview wizard and plan editing

For a project without `board.json`, the page offers **Plan a project**: the
Phase-A questions (mode, name, goal, stack, hosting, …) as a form. Saving writes
a draft into the runtime folder; **Generate plan** composes
`prompt/generator.md` plus the answers into one prompt and starts a generator
session (no interactive questions are possible in a headless run — missing
answers become `open_questions` on the board). When the session has written
`ARCHITECTURE.md`, `board.json`, `tasks/` and `policy.json`, **Approve plan**
validates the board and records that you accepted it.

For an existing project the Plan view edits the board through the same rules as
the CLI: create, edit and delete tasks (only `pending`/`blocked`/`failed` tasks
can be deleted, done tasks are reopened through the state machine first), change
dependencies (cycles are refused), scopes, gates, stages and owner decisions.
`board.json` is written atomically under `board.json.lock` and validated with
`core.board.board_errors` before it is replaced.

## API

All routes return JSON. Mutations need `X-Polier-Action: 1`; with a token, send
`Authorization: Bearer <token>` (or `?token=`). Errors have the shape
`{"error": "…", "details": …}`; a refused state transition answers `409` with
the `errors`/`actions` the CLI would print.

| Method and path | Purpose |
|---|---|
| `GET /api/health` | version, role, board presence |
| `GET /api/config` | dashboard config, suggested gate commands, session settings |
| `GET /api/snapshot` | whole project: tasks with derived fields, dispatch, stages, counts, git |
| `GET /api/tasks/<id>` | task detail: brief, review, gate records, events, approvals |
| `GET /api/tasks/<id>/logs/<log>` | one gate log from `reviews/evidence/` |
| `GET /api/dispatch`, `/api/activity`, `/api/approvals`, `/api/claims` | plan, feed, decisions, live claims |
| `POST /api/tasks/<id>/state` | lead-only status transition (`status`, `note`, `force`) |
| `POST/DELETE /api/tasks/<id>/claim` | take/release the claim |
| `POST /api/approvals/request`, `/api/approvals/<id>/grant\|deny` | owner decisions |
| `POST /api/jobs/gate`, `/api/jobs/check`, `/api/jobs/audit` | start a streaming job |
| `GET /api/jobs`, `/api/jobs/<id>`, `/api/jobs/<id>/log`, `POST /api/jobs/<id>/stop` | jobs and live logs |
| `POST /api/sessions`, `GET /api/sessions`, `/api/sessions/<id>/log`, `POST /api/sessions/<id>/stop` | headless sessions |
| `GET/PUT /api/plan`, `POST /api/plan/answers` | interview draft |
| `POST /api/plan/generator`, `/api/plan/approve` | planning session, approval |
| `POST /api/plan/tasks`, `PATCH/DELETE /api/plan/tasks/<id>` | plan editing |
| `POST /api/plan/stages/<id>/decision`, `/move` | stage owner decision, order |
| `GET/PUT /api/settings`, `POST /api/settings/labels`, `PUT/DELETE /api/settings/labels/<id>` | project settings, feature flags, labels |
| `GET /api/filters/fields` | filter field/operator metadata for the builder |
| `GET /api/views`, `PUT/DELETE /api/views/<id>` | built-in and saved views |
| `GET /api/worklog[?task=<id>]` | per-task or project worklog and estimate comparison |
| `GET /api/me`, `GET /api/inbox`, `POST /api/inbox/read` | Your Work, inbox items and read state |
| `GET /api/events` | Server-Sent Events (`state`, `job`, `session`, `approval`, `claim`, `plan`, `inbox`, `views`, `settings`, `ready`, `lag`) |

The dashboard also reads gate commands from the project's own table in
`docs/quality.md` (columns: gate, command) so the gate runner prefills the
documented command. Saved overrides live in the dashboard config.

## Configuration and runtime files

Nothing of the dashboard is committed. Runtime files live in
`<git-common-dir>/polier/dashboard/` (shared by all worktrees; outside git the
page falls back to `.polier-dashboard/`):

| Path | Contents |
|---|---|
| `dashboard.json` (project root, committed) | feature flags, label definitions, defaults (`me`) |
| `views/<id>.json` (project root, committed) | saved filters, grouping, sorting and columns |
| `config.json` (runtime) | provider command/settings, gate-command overrides, UI preferences |
| `plan.json`, `plan/` | interview answers and the last generator prompt |
| `jobs/<id>.log` | full output of gate/check/audit jobs |
| `sessions/<id>/` | prompt, generated Claude settings, transcript, session log, meta |
| `inbox.json` | read state of the inbox items |

Deleting the folder loses transcripts, job logs and read marks only; `dashboard.json` and `views/` are project files and survive.

## Limits and design notes

- The server is a local operator tool, not a hosted service: one project per
  process, no authentication beyond the optional token, no multi-user roles.
- It calls the same `core` functions as the CLI; it never re-implements the
  state machine, the policy or the evidence rules. `board.json` is never written
  by the server except through `core.state.set_status` and the validated plan
  editor.
- `STATUS.html` from `render_status.py --html` stays the zero-server page for
  archives and CI. The dashboard is for the working session.
- Sessions are opt-in and provider-specific. Only the Claude Code CLI defaults
  are shipped; a custom provider is a command list in the config (tests use a
  fake provider). The adapter layer stays thin because CLI flags and event
  formats change.
- Headless runs inherit the local Claude Code login; token use is recorded but
  cost control remains `policy.json` → `budget`.
- "Worklog actual hours" are derived, not tracked: an attempt window or the
  session span. It is a comparison aid for estimates, not payroll time.
- The inbox is a derived feed, not a store; only its read marks are local.
