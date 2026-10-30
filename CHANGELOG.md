# Changelog

Each release lists what a running project must do to adopt it. Update between stages, never during a task (see `guide/cheatsheet.md`). The current version is in `VERSION`; projects record theirs in `board.json` → `generator_version`.

## 2.7.0

**German as a second language, a new look and a short README.**

**Dashboard in German.** The whole dashboard can run in German: navigation, views, the task drawer, dialogs, toasts, tooltips and dates. It follows the browser language; *Settings → General → Language*, the command palette (*Sprache: Deutsch* / *Language: English*) or `?lang=de|en` switch it, and the choice is remembered per browser. Translations live in `server/assets/i18n.js` (exact strings, fragments of composed strings, nouns in counts and patterns); `app.js` passes every UI string through `tr()` in `h()`, toasts and the static header. Project content is never translated: Markdown is rendered with translation paused, and commands, paths and long server messages are left alone. The handbook stays English. New suite `tests/test_i18n.py`.

**New look.** A new logo (the board's four tiles, the last one checked) in the header, the favicon and `docs/images/logo.svg`; new banners in English and German (`banner.png`, `banner.de.png`); new screenshots of every view; two animated GIFs per language — a dashboard tour (`tour.gif`) and "proof, not promises" (`flow.gif`): a gate run is recorded, and moving to review is refused until every gate has a passing record.

**README.** Rewritten short, with a German version (`README.de.md`). The list of the guard's known gaps moved to [`docs/guard-limits.md`](docs/guard-limits.md); unused images were removed.

**Compatibility.** No API, file or rule changes. The select-mode button now reads *Done selecting*. Restart the dashboard to load the new assets. Plugin users: `git pull`, `dsh plugin --profile <name> add ./polier` again, restart. Claude Code users: replace the package copy. Skill-only users: `./update.sh`.

## 2.6.0

**Knowledge, AI and integrations.** 2.5 made the dashboard calmer; 2.6 fills it: the knowledge view becomes a documentation site with a handbook that ships with Polier, an AI area turns headless sessions into assignable agents with skills and MCP connectors, Polier's own MCP server gets a setup page, and GitHub can be connected from the dashboard. The README is rewritten around a quick start.

**Knowledge, rebuilt as a documentation site.** Pages becomes a docs-style reader: a navigation tree with sections (Overview, Documentation, Packages, Task briefs, Reviews) and collapsible groups, the article in a readable column with breadcrumbs, reading time and an "On this page" outline that follows the scroll, *Referenced by*, a folded *Page history* and previous/next links. `#/pages` without a path is an overview with start cards, the project's sections and recently updated pages. Markdown gains real tables, GitHub-style callouts (`> [!NOTE]`, `[!TIP]`, `[!WARNING]`), code blocks with a copy button, adjacent code blocks in different languages as one tabbed example (the chosen language is remembered across the page), and `METHOD /path` headings and inline code as method badges.

**A handbook ships with the dashboard.** 39 pages in `server/handbook/` (ordered by `index.json`, served by `GET /api/handbook`, loaded by `core/handbook.py`) appear next to the project documents as two more areas: **Guides** — getting started, one page per dashboard area, tutorials (plan a project, run a task end to end, headless agents, reviews and approvals, intake and templates, labels/filters/views, timeline and cycles, automations, Claude Code via MCP) and reference (shortcuts, project files, CLI, troubleshooting) — and the **API reference**: introduction with a small client, authentication and safety, errors, live events and every endpoint group with parameters and cURL/Python/JavaScript examples. The search covers the handbook too. A test keeps the reference complete: every `/api/…` route of the server must be named in it.

**AI and MCP.** The sidebar gets an **AI** group (Assistant, Agents, Sessions, Skills, MCP, Automations) and an **Integrations** group (GitHub).
- **Agents** — reusable profiles with a role, an optional model, standing instructions, skills and MCP connectors, committed in `agents.json` (`core/agents.py`; built-in Builder, Reviewer and Lead until the file exists). *Assign to a task* starts a headless session with the profile; the task drawer and the Sessions view offer the agent as well. `GET/PUT /api/agents`, `POST /api/sessions` with `agent`, MCP `polier_agents`.
- **Skills** — reusable instructions in the Agent Skills layout `.claude/skills/<id>/SKILL.md` (name, description, body), so interactive Claude Code finds them too; headless sessions inline the skills of their agent into the prompt. Five examples ship in `templates/skills/` (test first, stay in scope, review checklist, prove it with gates, handoff). `core/skills.py`; `GET /api/skills`, `PUT/DELETE /api/skills/<id>`, `POST /api/skills/examples`, MCP `polier_skills`.
- **MCP server page** — ready-to-paste configuration for Claude Code, Claude Desktop, Cursor and VS Code with this machine's paths, a read-only switch, the tool list with read/write access, and a handshake test. `GET /api/mcp`.
- **MCP connectors** — other MCP servers (stdio command or HTTP URL) that sessions and the assistant may use, per role or per agent; stored machine-locally with masked secrets, tested with initialize + tools/list, passed to Claude Code with `--mcp-config` and `mcp__<name>` in the allowed tools. Polier's own server is the built-in connector `polier`, read-only unless a lead session is allowed to write. `core/mcp_connectors.py`; `PUT/DELETE /api/mcp/connectors/<name>`, `POST …/test`.

**GitHub login.** *Connect GitHub* (GitHub view and Settings → Integrations) signs the `gh` CLI in with the device flow — the dashboard shows the one-time code and the device page link and finishes on its own — or with a personal access token; *Disconnect* signs it out. Polier still stores no credential. `GET /api/github/auth`, `POST /api/github/login`, `…/login/cancel`, `…/logout`; CLI `tools/github.py auth`.

**Handbook.** A new *AI and MCP* section (overview and safety model, assistant, agents, skills, MCP server, MCP connectors, GitHub integration) and an API page for agents, skills, MCP and the GitHub connection.

**Compatibility.** Additive. New routes cover the handbook, agents, skills, MCP and the GitHub connection; `agents.json` and `.claude/skills/` are new optional project files, connectors live in the runtime config. Sessions now get the enabled connectors (by default Polier's own read-only MCP server) through `--mcp-config`; switch the built-in connector off under AI → MCP → Connectors to keep the 2.5 behaviour. Restart the dashboard. Plugin users: `git pull`, `dsh plugin --profile <name> add ./polier` again, restart. Claude Code users: replace the package copy; MCP gains `polier_agents` and `polier_skills`. Skill-only users: `./update.sh`.

## 2.5.0

**A calmer dashboard.** 2.0–2.4 added a view per release until the page had twenty tabs in one row, a bulk bar that was always open and a filter toolbar of three lines. 2.5 changes no API, no file and no rule; it reorganises the page so the common work (look at the board, open a task, decide) takes fewer clicks and less reading.

**Navigation.** The tab row becomes a sidebar with five groups — work (Your Work, Board, Table), **Plan** (Plan editor, Timeline, Cycles, Dependencies, Dispatch), **Track** (Approvals, Activity, Coverage, Modules, Analytics), **Agents** (Sessions, Assistant, Automations, GitHub) and **Knowledge** (Pages, Intake) — with Settings at the bottom. Views switched off in `dashboard.json` disappear from it, counts sit next to Your Work and Approvals. Below 900 px the sidebar turns into a scrolling strip. The header gets a visible **Commands** button for the Ctrl/Cmd+K palette, and the search icon no longer overlaps the placeholder.

**Board and table.**
- One toolbar row: view, group, sort, `+ Filter`, the task count, `Select` and a density toggle. Filter chips only appear when there are filters; "Save view" only when the current filters, grouping or sort differ from the default.
- Bulk actions are a mode: `Select` shows the checkboxes and a sticky bulk bar, clicking a card selects it, `Done` or Esc leaves the mode. The note field appears only for Rework/Blocked/Failed; label checkboxes open from a `Labels ▾` button.
- The stage progress moves from a side panel into a strip above the board, so every Kanban column fits. Empty Rework/Blocked/Failed columns fold into slim rails; Done stays folded until opened.
- Cards drop the repeated status badge (it is the column) and the zero lines: gates, effort and tokens are one compact row, and only when there is something to show. The table hides the labels column when the project defines no labels.

**Your Work.** The inbox comes first; queues with items get a card, empty ones are summed up in one "All clear" line, zero tiles are dimmed. Inbox rows show their action inline ("Open task →") and a ✓ to mark them read.

**Task drawer.** Properties (labels, estimate, planning dates) fold into one line with a summary until opened; the transition note only appears when a reachable status needs one; claim and the copyable CLI commands share a row.

**Smaller fixes.** The dependency graph fits the width by default (`Fit`, `−`, `+`). The Settings feature note no longer talks about "planned" views. `tools/plan.py` now accepts the documented comma lists (`--labels bug,risk-low`; also `--depends-on`, `--gates`, `--satisfies`) instead of refusing them as one invalid id. Nine unused helpers were removed from `app.js`. The screenshots in `docs/images/` show the new layout.

**Compatibility.** UI only, plus the CLI fix. Deep links (`#/board`, `#/graph`, `#/board/<ID>`, …), the API, MCP tools and every project file are unchanged. Restart the dashboard to load the new page. Plugin users: `git pull`, `dsh plugin --profile <name> add ./polier` again, restart. Claude Code users: replace the package copy. Skill-only users: `./update.sh`.

## 2.4.0

**Intelligence.** 2.4 puts the project's own evidence to work: an assistant that answers questions about the plan without being able to change it, deterministic automations that turn state into suggestions (dry run, no hidden writes), bulk operations for the owner's repeated actions, a command palette for navigation and a read-only GitHub/CI panel. Everything stays local, file-based and auditable; the assistant runs through the same headless session provider and the same project hooks as every other agent.

**Assistant.** `core/assistant.py` builds a compact read-only briefing (project, stages, next wave, blocked tasks, approvals, claims, sessions, intake, task list), stores conversations in the dashboard runtime and parses answers with an optional structured proposal block (`state`, `plan_task`, `gate`, `session`, `note`). `server/assistant.py` runs one provider session per question in the background and stores the answer and proposals. The UI shows the chat, the proposals and applies them only after confirmation through `POST /api/assistant/apply` (validated state machine, plan editor, gate job or session start). Conversations never touch the project. `GET/POST /api/assistant`, `/api/assistant/chat`, `/api/assistant/<id>`, `/api/assistant/<id>/cancel`, `/api/assistant/apply`; CLI `tools/assistant.py ask|list|show|delete`.

**Automations.** Committed `automations.json` rules with a `when` kind (`gate_failed`, `task_blocked`, `budget_over`, `review_ready`, `session_failed`, `intake_proposed`, `stage_decision_pending`, `task_ready`) and suggested actions (`state`, `session`, `open`, `note`). `core/automations.py` evaluates them on demand — a **dry run** that returns matches and suggested actions; nothing is executed, and applying a suggestion goes through the normal validated API. `GET/PUT /api/automations`, `POST /api/automations/run`; MCP `polier_automations`; CLI `tools/automations.py list|validate|run|save|init`; example rules in `templates/automations.json`.

**Bulk operations.** `POST /api/bulk` performs `state`, `claim`, `release`, `labels` or `estimate` on up to 100 tasks and returns a per-task result (conflicts are reported per task, not silently dropped). The board and table views get multi-select and a bulk bar; every write still goes through the same core functions and the audit trail.

**Command palette.** A client-side Cmd/Ctrl+K palette over all views, the current tasks and the quick actions (new task, new intake, ask the assistant, run the automations dry run, refresh, settings).

**GitHub/CI panel.** `core/github.py` reads the open pull requests and the recent workflow runs through the authenticated `gh` CLI and maps them to tasks by `task/<ID>`/`branch`; results are cached for 30 seconds. Without a GitHub remote, `gh` or auth the panel explains why it is unavailable — it never fails the dashboard and never stores credentials. `GET /api/github`, MCP `polier_github`, CLI `tools/github.py status`.

**Settings.** `dashboard.json` features `assistant`, `automations` and `github` now default to on; all planned views are implemented.

**Compatibility.** Additive: `automations.json` is optional, assistant conversations are local runtime files, and no board/policy/run/review file changes shape. Start the dashboard as before. Plugin users: `git pull`, `dsh plugin --profile <name> add ./polier` again, restart. Claude Code users: replace the package copy; MCP gains the automation and GitHub tools. Skill-only users: `./update.sh`.

## 2.3.0

**Knowledge and intake.** 2.2 put the plan on a time axis; 2.3 connects the two ends of the work: the project's Markdown (architecture, docs, ADRs, briefs, reviews, package docs) becomes a browsable knowledge layer, and ideas reach the plan through an explicit intake with triage. Task templates make recurring shapes reusable. Everything stays file-based, committed and read-only where it can be.

**Pages (wiki).** `core/pages.py` indexes the project's Markdown: root documents (`README`, `AGENTS`, `ARCHITECTURE`, `STATUS`, `CHANGELOG`, …), `docs/**`, `tasks/*.md`, `reviews/*.md` and the package/service/app/tool README/ARCHITECTURE files. The dashboard gets a page browser with collections (root, documentation with subfolders, briefs, reviews, package docs), content rendering, safe relative links, backlinks (pages and tasks that reference the file), **git history** and old revisions (`git show <ref>:<path>`), full-text search, and local favorites. Nothing is written: the viewer only reads. `GET /api/pages`, `/api/page?path=&ref=`, `/api/page/history`, `/api/pages/search`, `/api/pages/favorites`; MCP `polier_pages`, `polier_page`, `polier_pages_search`; CLI `tools/pages.py list|search|show|history|favorite|favorites`.

**Intake and triage.** Proposals live as committed `intake/<id>.json` files with a small lifecycle: `proposed` → `accepted` or `rejected`, plus kind, priority, source, links and the decision trail. Accepting creates a pending board task through the validated plan editor and links it back; a task template can provide the structure. Sources: dashboard form, CLI and MCP. `GET/POST /api/intake`, `PATCH /api/intake/<id>`, `POST /api/intake/<id>/accept|reject`; MCP `polier_intake`, `polier_intake_add`; CLI `tools/intake.py list|show|add|update|accept|reject`.

**Task templates.** Committed `templates/tasks/<id>.json` files carry the reusable shape of a task (scope, acceptance, gates, complexity, labels, estimate). They can be written by hand, saved from an existing task ("save as template") or used as defaults when creating a task from the plan editor, the intake accept form, the API or the CLI. Validation stays with the normal plan editor. `GET/POST /api/task-templates`, `DELETE /api/task-templates/<id>`; MCP `polier_templates`; CLI `tools/templates.py list|show|save|delete`. `POST /api/plan/tasks` accepts `template: <id>` and merges its defaults.

**Settings.** `dashboard.json` features `pages` and `intake` now default to on (the last planned view, `assistant`, stays off).

**Compatibility.** Additive: no board, policy, run or review file changes shape; `intake/`, `templates/tasks/` and the favorites runtime file are new (the first two are committed). Start the dashboard as before. Plugin users: `git pull`, `dsh plugin --profile <name> add ./polier` again, restart. Claude Code users: replace the package copy; MCP gains the knowledge tools. Skill-only users: `./update.sh`.

## 2.2.0

**Planning.** 2.1 made the dashboard the place where the owner works; 2.2 adds the overview: where the plan sits in time (Timeline), how each stage is doing (Cycles), how the packages are doing (Modules), which requirements are really covered (Coverage) and what the evidence says about the project (Analytics). Everything is derived from the files Polier already writes; there is no new store and no required field.

**Timeline.** `core/timeline.py` schedules tasks from their dependencies and estimates at `dashboard.json` → `defaults.hours_per_day` (default 4), inside sequential stage lanes; completed tasks are placed at their run-record finish date, so history is visible. Board schema 1.2 adds optional `planned_start` and `target` (``YYYY-MM-DD``) that override the auto-schedule for one task; the plan editor and `tools/plan.py` set and clear them. The view shows day/week axes, a today line, critical path, explicit-date and overdue markers, and unscheduled work. `GET /api/timeline`, `polier_timeline`.

**Cycles.** Each stage is treated as a cycle with its goal, exit criteria and exit gates, progress, owner decision, effort and a burndown built from run events. The active cycle is the first incomplete stage. Stage decisions can be set from the view. `GET /api/cycles`, `polier_cycles`.

**Modules.** The package map becomes a module view: tasks per package, status breakdown, health (`ok`/`watch`/`attention`/`done`), docs presence (README/ARCHITECTURE), contract versions and effort. Tasks without a package stay visible in a separate section. `GET /api/modules`, `polier_modules`.

**Coverage.** Requirement definitions are read from `docs/quality.md` (`**Dn** …`), joined with task `satisfies` references, statuses and passing evidence; every requirement is `covered`, `partial`, `open` or `missing`, and codes that tasks reference without a definition are reported. `GET /api/coverage`, `polier_coverage`.

**Analytics.** One evidence-based model: completion and status counts, throughput per ISO week (12 weeks), cycle time per stage, gate pass rate, rework rate, blocked age, estimate vs actual effort, tokens per stage and session counts. `GET /api/analytics`, `polier_analytics`.

**Settings.** `dashboard.json` features gain the five planning views (default on); `defaults.hours_per_day` (1–24, default 4) drives the timeline. Pages, Intake and Assistant remain planned (off).

**Compatibility and migration.** Additive and optional: no existing board, policy, run or review file changes shape. Set `"schema_version": "1.2"` (or let the plan editor do it) to use planned dates; `labels`/`estimate_hours` stay 1.1 fields, and 0.9/1.0 boards remain valid. Start the dashboard as before. Plugin users: `git pull`, `dsh plugin --profile <name> add ./polier` again, restart. Claude Code users: replace the package copy; MCP gains the planning tools. Skill-only users: `./update.sh`.

## 2.1.0

**The project cockpit.** 2.0 made the dashboard a control plane; 2.1 turns it into the place where the owner actually works. It adds committed project settings, labels, structured filters with saved views, a personal cockpit ("Your Work" and an inbox), and a worklog that derives real effort from the evidence Polier already writes. All of it is optional and additive: the CLI, the guards and existing projects keep working unchanged.

**Settings (`dashboard.json`).** A new committed file next to `board.json` and `policy.json` holds what the project decides: `features` (which optional dashboard views exist; future views default off), `labels` (the label definitions tasks may use, with a palette name and a group), and `defaults` (`me` = the owner handle for "Your Work"). Machine-local settings (session provider, gate commands, theme, inbox read state) stay in the git-common runtime folder, never in the repository. `tools/settings.py show|init|feature|me|label …` edits it from the CLI; the dashboard Settings view uses the same validation.

**Board schema 1.1 (optional).** Tasks may carry `labels` (lowercase label ids defined in `dashboard.json`) and `estimate_hours` (a planning estimate). Both are additive; every 0.9 and 1.0 board stays valid, and the plan editor upgrades the board to 1.1 automatically when one of them is set. `templates/board.schema.json`, `core/board.py` and the test suite cover the new fields.

**Filters and saved views.** The dashboard's filter builder composes bounded conditions (field, operator, value) instead of a query language: text, status, label, number, boolean and budget fields with explainable operators (`is`, `any_of`, `none_of`, `contains`, `gt`, `empty`, …). Views are committed files in `views/<id>.json` (`name`, `kind`, `filters`, `group_by`, `sort`, `columns`); built-in views ("Ready now", "Blocked", "Review queue", "Over budget", "No estimate", "Mine") are generated and never overwrite user data. `tools/views.py list|builtin|show|save|delete` covers the CLI.

**Your Work and Inbox.** A personal cockpit derives the owner's queue from the board: my tasks, review queue, pending approvals, claims, blocked tasks, budget warnings, ready tasks and running sessions. The inbox is a single feed of actionable items (approvals, failed gates, blocked tasks, budget, reviews, finished sessions) with a local read/unread state; nothing is stored as project state. `GET /api/me`, `GET /api/inbox`, `POST /api/inbox/read` and the MCP tools `polier_me`, `polier_inbox`, `polier_inbox_read` expose it.

**Worklog and estimates.** `core/worklog.py` turns the existing evidence into a worklog: attempts, gate records, sessions, token usage and durations, per task and per stage. `estimate_hours` (schema 1.1) is compared with actual hours (session time when sessions exist, otherwise the attempt window; never both). The task drawer gets a Worklog tab; `GET /api/worklog[?task=ID]`, `polier_worklog` and the table's effort columns read it.

**CLI parity.** `tools/plan.py` (create/update/delete tasks with labels and estimates, stage decisions, `suggest-id`), `tools/settings.py` and `tools/views.py` mirror every dashboard write; labels are validated against `dashboard.json` and a 0.9/1.0 board is upgraded to 1.1 on first use.

**Tests and docs.** New suites cover the board 1.1 fields, settings and label lifecycle, the filter engine, saved views, worklog derivation, Your Work/Inbox, the three CLIs and the 2.1 HTTP API. `docs/dashboard.md`, `guide/cheatsheet.md`, `SKILL.md` and `templates/dashboard.json` document the cockpit.

**Migration.** Additive and optional. To use labels and estimates, set `"schema_version": "1.1"` (or let the plan editor do it) and copy [`templates/dashboard.json`](templates/dashboard.json) to the project root when you want explicit settings; without the file the defaults apply. Commit `dashboard.json` and `views/` with the project. Start the dashboard as before (`python3 tools/serve.py <project>`). Plugin users: `git pull`, `dsh plugin --profile <name> add ./polier` again, restart. Claude Code users: replace the package copy; the MCP server gains the 2.1 tools automatically. Skill-only users: `./update.sh`.

## 2.0.0

**The dashboard.** 1.4 showed the project in a static page; 2.0 makes it a control plane. `tools/serve.py` starts a local HTTP + Server-Sent Events server (Python standard library only, loopback by default) that serves one self-contained page and a small JSON API over the same files the CLI uses. Nothing changes for projects that do not start it: the CLI, the guards and `STATUS.html` keep working, and no board field changes.

**What the page does.**
- Board with Kanban and table views, gate progress, token bars, live claims, stage/package/owner filters and stage progress.
- Task drawer with brief, gates and evidence logs, run events, review verdict, handoff and quick actions: status transitions through `core.state`, claim/release, gate runs and headless sessions.
- Approvals inbox (request, grant, deny), dispatch view (next wave, running, blocked, conflicts), activity feed, dependency graph as inline SVG, jobs tray with live gate/check/audit logs.
- Interview wizard for greenfield projects: the Phase-A questions become a form, the answers compose the generator prompt, a generator session writes the artifacts and "approve plan" validates the board. For existing projects the Plan view edits tasks, dependencies, scopes and stage decisions with the same validation as the CLI.
- Headless sessions: a provider command (Claude Code by default) runs per task or worktree with the shipped hooks installed, the transcript streams into the page, tokens are recorded in `runs/<ID>.json` and the claim is taken and released. `tools/session.py` does the same from the CLI.
- `tools/mcp.py` exposes the board to any MCP host (Claude Code: `claude mcp add polier -- python3 …/tools/mcp.py --root .`), so an interactive session can read the plan and run lead-only actions as tools.

**Server and safety.** Loopback only by default, optional bearer token (`--token`/`POLIER_DASHBOARD_TOKEN`), `X-Polier-Action: 1` and a same-origin check for writes, `--read-only` for a viewer page. State changes still go through `core.state`, plan edits through `core.plan_edit` (atomic board write, schema validation, dependency-cycle refusal), and gate runs through `core.gate`, which writes the same evidence records as `tools/gate.py`.

**Runtime files.** Transcripts, job logs, the interview draft and the dashboard config live in `<git-common-dir>/polier/dashboard/`; nothing is committed.

**Tests.** New suites cover the read models, plan editing, the interview/plan draft, the HTTP API (including token, CSRF and read-only), streaming jobs, the session lifecycle with a fake provider, and the MCP server.

**Compatibility and migration.** Additive and optional; the board schema, `policy.json`, `runs/`, `reviews/` and every existing command are unchanged. Add `server/` to the shipped files (the package manifest covers it). Start it with `python3 tools/serve.py <project>`, read [`docs/dashboard.md`](docs/dashboard.md) for the API and the security model. Plugin users: `git pull`, `dsh plugin --profile <name> add ./polier` again, restart. Claude Code users: replace the package copy; add the MCP server with `claude mcp add`. Skill-only users: `./update.sh`.

## 1.4.0

**Read-only views on the status page.** The page from 1.3 had the facts but only one way to read them. 1.4 adds four read-only views to `STATUS.html` — a Kanban board, a dependency graph, an activity timeline and a token history — with stage, package and owner filters and a table/Kanban switch. The page is still one self-contained file, nothing on it changes a status, and `tools/state.py` stays the only writer.

**The four views.**
- Kanban board: `pending`, `in_progress` (claimed included), `verifying`, `review`, `rework`, `blocked`/`failed` and `done`; a card shows ID, title, stage, owner, gates passed out of total and a token bar.
- Dependency graph: inline SVG built by the renderer from `depends_on`. The column is the DAG depth and the rows are grouped by stage; the node is coloured by status, the critical path of unfinished tasks is highlighted, and a dependency cycle is marked in the graph and reported as a warning instead of crashing the render.
- Activity timeline: run-record events plus recorded usage and approval request/decision records, newest first, the last 50, with failed gates and failed reviews in red.
- Token history: cumulative tokens over time as an inline SVG with a total line and one line per stage, plus a horizontal budget line from `budget.max_tokens_per_task` when a budget is set. The section is omitted when there is no usage data.

**Base page, filters and fallback.**
- The 1.3 page stays: summary tiles, stages, the task table with attempts, gate records, review verdict, tokens and findings, the next wave, blocked tasks and pending approvals.
- Stage, package and owner filters above the table narrow the table and the Kanban. The Table/Kanban switch is a CSS radio toggle. Neither needs a build step.
- The filters use one small inline script; without JavaScript everything stays visible and the CSS switch still works. The page loads no external CSS, script or CDN, has no buttons or write paths, and changes nothing.

**`--watch` and `--interval`.**
- `tools/render_status.py <project> --html --watch [--interval N]` polls the mtimes of `board.json`, `runs/`, `reviews/` and `policy.json` and rewrites `STATUS.html` and `STATUS.md` atomically when one changes. The default interval is 2 seconds; `--watch` implies `--html`.
- A 5-second meta refresh is written only in watch mode; a plain `--html` page is not reloaded by the browser. Ctrl+C stops the watch and exits 0.

**Tests.** New `tests/test_render_status.py` covers every view for `examples/monorepo-mini`, the Kanban card count and dependency edges, a cycle that warns instead of crashing, a title with markup escaped, the token history with and without usage data, the watch snapshot helpers and the CLI output with and without the meta refresh. `tests/test_status_html.py` now allows the one inline filter script but still rejects external scripts and stylesheets.

**Compatibility.** Additive and read-only. `STATUS.md` is unchanged byte for byte and `board.json` keeps its schema; no field is added. The token history reuses the 1.3 budget (`budget.max_tokens_per_task`) and is omitted when a project has no usage data. Existing sections of the page, `--html`, the tools, plugin tools and `/pl` commands behave as before, and `--watch` is opt-in.

**Migration:** set `generator_version` to `1.4.0`. No other change is needed; projects that already ignore `STATUS.html` keep doing so. Plugin users: `git pull`, `dsh plugin --profile <name> add ./polier` again, restart. Claude Code users: replace the package copy. Skill-only users: `./update.sh`.

## 1.3.0

**Token budget and status page.**

**Token budget.**
- `policy.json` gets an optional `budget` section: `max_tokens_per_task` (`null` = off, otherwise 1,000–1,000,000,000) and `warn_at` (0.1–1.0, default 0.8). It caps what one task may spend over all its attempts and sessions.
- `runs/<ID>.json` stores the token use per session under `usage`; a session reports its running total, so a repeated report replaces the older one. New `core.runs.record_usage` and `usage_total`.
- The Claude Code Stop hook reads the session's tokens from the transcript (input, output and cache creation; cache reads are left out) and records them for the bound task. Near the budget it adds a warning; at the budget it tells the agent to stop and report. `POLIER_USAGE=0` switches it off.
- New `tools/usage.py record | show` for every other harness and for manual entries.
- `tools/state.py set <ID> in_progress` refuses a task whose budget is used (continuing needs a granted `state_override`) and warns at `warn_at`; `state.py show` prints the tokens. The dispatch plan lists such a task as blocked, and running entries carry `tokens` and `max_tokens`.
- The DSH guard mirror accepts and validates the new section.

**Status page.** `tools/render_status.py <project> --html` also writes `STATUS.html`: summary tiles, stages, every task with attempts, gate records, review verdict, tokens against the budget and audit findings, the next wave, blocked tasks and pending approvals. One static file, no script, light and dark. It changes with every token report, so keep it out of git.

**README.** Quick links, a recorded demo, a "Why" table, "What Polier is not", a FAQ and the status page.

**Migration:** set `generator_version` to `1.3.0`. Optional: add `"budget": {"max_tokens_per_task": <number>, "warn_at": 0.8}` to `policy.json` and `STATUS.html` to `.gitignore`. Projects without a budget behave as before. Plugin users: `git pull`, `dsh plugin --profile <name> add ./polier` again, restart. Claude Code users: replace the package copy; the hook entries stay the same. Skill-only users: `./update.sh`.

## 1.2.0

**Research, a dependency checkpoint and automatic releases.**

**Research (`tools/research.py`).**
- `deps` lists the dependencies of every `package.json`, `requirements*.txt` and `pyproject.toml` in the project; the project's own workspace packages are left out.
- `versions` compares them with `docs/versions.md`: missing rows, leftover `[VERIFY…]`/`[UNVERIFIED]` markers and versions that differ from the manifest. `--lookup` asks npm and PyPI whether each exact version exists and when it was published; `--write` records the confirmed ones with source URL and date. Ranges and failed lookups stay findings.
- `note "<topic>"` creates `docs/research/<slug>.md` from the new `templates/research-note.md` (question, answer, dated sources); `check` validates every note and the versions table.
- `tools/check.py` reads `docs/versions.md` through the same parser, so a row titled "Next.js" with an npm URL counts for `next`.
- `prompt/generator.md` (phases A, B, H), `prompt/dsh.md`, `SKILL.md`, `templates/versions.md`, `templates/task-brief.md` and the cheatsheet point to the tool.

**Dependency checkpoint.** `tools/state.py set <ID> in_progress` now refuses while a task in `depends_on` is not `done`, the same rule the dispatch plan already used. Without `policy.json` it is a warning.

**Cleanup.**
- Phase 0 is now phase A (A1 tool check, A2 interview, A3 profile); the phases run A to I without a gap.
- `docs/agents/roles.md` and `protocol.md` are no longer required at M/L. No template or check existed for them; roles and the loop live in `AGENTS.md` and `docs/orchestration.md`.
- The task loop is described once, in `prompt/orchestration.md`; `prompt/dsh.md` and the cheatsheet link to it.
- `plans/` (the internal planning record of 1.0 and 1.1) is removed; it stays in the git history.
- `install.sh` no longer copies `.github/`, `docs/`, `package.json`, `install.sh` and `update.sh` into the skill folder.

**Releases.** `.github/workflows/release.yml` publishes a GitHub Release when `VERSION` changes on `main`, with this file's section as notes. The README has screenshots of real tool output.

**Migration:** set `generator_version` to `1.2.0`. Optional: add `python3 <package>/tools/research.py check` to the lint commands in `AGENTS.md`. A task that was started while a dependency was open keeps its status; the new check applies to the next `in_progress`. Plugin users: `git pull`, `dsh plugin --profile <name> add ./polier` again, restart. Skill-only users: `./update.sh`.

## 1.1.0

**Orchestration on top of the plan.** 1.0 planned a project and guarded the writes, but it could not say what had been tried, when a review happened or whether a risky action was approved. The board was the only record, so a status could simply be typed in; attempts, review rounds and emergency stops lived in chat. 1.1 separates plan state from execution state and puts a checkpoint before every transition.

**Policy as code (`policy.json`).**
- New `templates/policy.json` and `core/policy.py`: limits (`max_attempts_per_task`, `max_in_progress`, `max_review_rounds`, with ranges 1–10, 1–64, 1–20), `scope.protected_paths`, `dependencies` (approval switch + manifest list), `approvals` (actions + approver), `commands` (deny, lead_only, warn) and `checks` (review/handoff/run-record/disjoint-scopes).
- Loading deep-merges the defaults; unknown keys, a wrong `version` or out-of-range limits are errors. An absent file means `enabled: false`, which is what keeps 0.9 and 1.0 projects unchanged.
- Path matching is `**`-aware and basename matching applies at any depth; command matching strips quotes, heredocs, assignments and wrappers, joins the shell segments and matches the pattern against them.
- `tools/check.py` validates the policy; a policy that denies a command a gate needs is a planning error, not an approval.

**Checkpoints (`tools/state.py`, `core/state.py`).**
- `tools/state.py show | set | check`: the only writer of a task's status. `show` prints the board status against the run record, gates, review, approvals and attempts; `check` evaluates a transition without writing; `set` refuses with each blocker and an action hint.
- Transition table with hard preconditions: `in_progress` needs a free attempt, a free `in_progress` slot and an unblocked stage; `verifying` an open attempt; `review` a passing record for every gate in the task; `done` the review verdict, handoff, run record and a dependency approval when a manifest is touched; `rework` a note and a free round; `blocked`/`failed` a note; `done → rework` a granted `reopen_done` approval; `--force` a granted `state_override` approval and leaves a warning event.
- Side effects: atomic board write, run-record attempts and events, round increment on `rework`, no other files.

**Run records (`runs/<ID>.json`, `core/runs.py`).**
- One file per task: `state` (`idle | running | done | failed | blocked`), `attempt` counter, `attempts` (`pass | fail | cancelled`) and an append-only `events` list (`start`, `gate`, `review`, `state`, `approval`, `note`, `escalate`; last 500 kept). Written atomically under `<file>.lock`; a missing or broken file reads as a skeleton.
- `tools/gate.py` appends a `gate` event when the policy is enabled; a failure there never changes the gate result. `runs/` is committed with the task.

**Approvals (`reviews/approvals/AP-NNN.json`, `core/approvals.py`).**
- New `tools/approve.py request | grant | deny | list | check`: IDs `AP-` plus three or more digits, allocated under a lock. A granted record is the approval and does not expire; grant and deny append an `approval` event to the task's run record. `check --action ... --task ...` exits 0 only for a granted match.
- Actions: `new_dependency`, `scope_change`, `merge_to_base`, `release`, `reopen_done`, `protected_path`, `state_override` — the list lives in `policy.json`. The guard consumes the dependency approval; a protected path is lead-only, so no approval lets a worker write one.

**Dispatch (`tools/dispatch.py`, `core/dispatch.py`).**
- The board becomes an execution plan: `limits`, `running` with attempt N/M, `waves` of tasks with the same non-empty `parallel_group`, same stage and pairwise disjoint `scope_write` (packed up to `max_in_progress`), `blocked` tasks with the command that records the block, `conflicts`, `approvals_pending` and `next`.
- A task without a group is a wave of its own; an attempt-exhausted task, a task without a brief, a task claimed by another session and a task waiting for a dependency or a stopped stage are listed as blocked, each with the command that records the block. With `checks.disjoint_scopes: false` both overlapping tasks stay in the wave and the conflict is still listed.

**Audit (`tools/audit.py`, `core/audit.py`).**
- Per task: board status, attempts used/limit, gates, review file and verdict, approvals per action, handoff, run record, findings. For a `done` task every check the policy turns on is an error; for other statuses the findings are warnings, and without `policy.json` everything stays a warning. Exit 1 iff any error.

**Checks and status.**
- `tools/check.py`: validates `policy.json`, `reviews/approvals/` and `runs/`, flags two `in_progress` tasks with overlapping scopes and attempts above the limit, reports dispatch conflicts as errors and blocked tasks as warnings, and warns when `policy.json`, `docs/orchestration.md` or `runs/` are not named in `AGENTS.md`/`README.md`.
- `tools/render_status.py`: new "Orchestration" section (limits, next wave, running attempts, blocked tasks with reasons, pending approvals), at most 10 lines.
- `core/board.py`: the stage report gains `tasks_open`; a stage is complete only when no task in it is open.
- `core/scope.py`: `runs/` is lead-owned and a reviewer may not write `reviews/approvals/`.

**Guard and plugin.**
- The DSH guard and the Claude Code `PreToolUse` hook apply the policy after the role and scope rules: a protected path is refused to every session except a lead, a dependency manifest needs a granted `new_dependency` approval, denied commands are refused for every role, lead-only commands for worker and reviewer sessions. Lead sessions bypass the path and dependency checks; nobody bypasses a deny rule.
- New `pl_next` (dispatch plan as JSON) and `pl_state` (`show`/`set` through `tools/state.py`); `/pl next` and `/pl policy`. New `adapters/dsh/lib/policy.mjs`, tested against `core/tests/policy_cases.json` together with `core/policy.py`.

**Docs and templates.**
- New `prompt/orchestration.md`: the shipped model — plan, execution and liveness state, the task loop, the stage loop, checkpoints, attempts versus rounds, approvals, escalation, how board patterns map and what is not covered.
- New `templates/policy.json` and `templates/orchestration.md` (generated as `docs/orchestration.md`); `templates/AGENTS.template.md` gains the state/gate/approval/run rules, `templates/task-brief.md` an "Operating the task" line, `templates/review-feedback.md` the round rule.
- `prompt/generator.md`: limits per profile in phase 0.3, `policy.json` in phase D, the loop, approvals and escalation in phase E, the new files in the G scaffold, `audit.py` and `dispatch.py` in phase H, the orchestrate prompt and state/approval commands in phase I, plus definitions and artifact-map rows.
- `prompt/rubric.md`: criteria 14 (execution state) and 15 (policy and approvals), the 1.1 lint items, critic and cold-start updates. `prompt/dsh.md`, `SKILL.md`, `guide/cheatsheet.md` and `README.md` describe the loop and the new tools.

**Compatibility.** Additive, and a project without `policy.json` is not broken by 1.1. Both 0.9 and 1.0 boards are unchanged, `board.json` keeps its schema (1.1 adds no board field), and `check.py`/`audit.py` warn instead of failing; the guard adds no policy denials. A project that runs `tools/state.py` without a policy still gets the transition table, the note rules and the approvals that guard a reopened done task or a forced change; the gate, review, attempt and concurrency checks become warnings, and the dependency-manifest approval is not checked. Existing tools, plugin tools, `/pl` commands and board fields are unchanged. The core gains `core/policy.py`, `core/runs.py`, `core/approvals.py`, `core/state.py`, `core/dispatch.py` and `core/audit.py`; `tools/` gains `state.py`, `approve.py`, `dispatch.py` and `audit.py`.

**Migration:** 0.9 and 1.0 projects need nothing. To adopt 1.1: copy `policy.json` from `templates/policy.json` and set the limits for the profile (S 3/1/3, M 3/2/3, L 3/3/3 for attempts/in progress/rounds), the project's manifests and its protected paths; copy `docs/orchestration.md` from the template; add the state, gate, approval and runs rules from `templates/AGENTS.template.md` to `AGENTS.md`; name `policy.json`, `runs/` and `docs/orchestration.md` in `AGENTS.md` and `README.md`; commit `runs/` from the next task on. From then on set statuses only with `tools/state.py set` and approve high-risk actions with `tools/approve.py`. Plugin users: `git pull` in the clone, run `dsh plugin --profile <name> add ./polier` again and restart. Claude Code users: replace the package copy; the hook applies the same policy checks. Skill-only users: `./update.sh`.

## 1.0.0

**Parallel projects and monorepos.** 0.9 planned and guarded one project with one active writer well. Running a real project with two harnesses in parallel and planning a monorepo exposed gaps that file-scope guarding cannot catch: shared ports and test databases, gate runs that fail because another session holds a port, snapshots that look like flaky tests, releases from a working folder, missing environment variables, and no common record of who works on what.

**Board 1.0.** `board.json` gets `"schema_version": "1.0"` (opt-in; a 0.9 board omits it and stays valid). Validation is strict per version: a 1.0 field on a 0.9 board is an error that says to set the version, unknown fields are errors.
- Task IDs widen from `M03` to also `P3-02`, `ENG-14`; new optional task fields `package`, `exclusive`, `resources`, `claim` (tooling only), `contract_followups`.
- New board fields: `stages` (exit criteria, exit gates, owner decision, dependencies), `packages` (path, kind, `may_import`), `resources` (slots, port formula, service offsets, `infra_patterns`), `budgets`, `worktrees`, `contracts`.
- `stage` on a task may reference `stages[].id`. `render_status.py` shows per stage: state, exit gates, missing records, owner decision; plus packages and the runtime slot formula. Later-stage tasks are not "ready" while a blocking stage is incomplete, and `check.py` rejects `in_progress` work there.

**Runtime slots and exclusive gates.** Two worktrees can run servers and tests at the same time.
- New `tools/slot.py acquire | release | show | list` and `core/slots.py`: slot 0 is the owner's main checkout, worktrees get the lowest free slot, `.polier-slot` holds ports (`port_base + port_stride·N + service offset`), database name and bucket; registered in `<git-common-dir>/polier/slots.json`.
- `tools/gate.py --exclusive <resource>` (and automatically for a task's `exclusive`) locks the resource in `<git-common-dir>/polier/locks/`; `--lock-wait`/`--lock-ttl`, exit 75 and `result: busy` when it stays held. `pl_gate` honours the same lock.
- Records gain `slot`, `exclusive`, `lock_wait_s`, `result` (`pass | fail | timeout | busy | infra`) and a stale-lock warning. Infrastructure patterns (`ECONNREFUSED`, `EADDRINUSE`, project patterns) are recorded as `infra`; `check.py` rejects `infra`/`busy`/`timeout` records as evidence and says "infrastructure failure, rerun alone" instead of "gate failed".

**Claims and worktrees.** One live session per task, across harnesses.
- New `tools/claim.py take | release | beat | list` and `core/claims.py`: claims in `<git-common-dir>/polier/claims/<task>.json`, live while the heartbeat is younger than 10 minutes. `board.json` is never written by claims. DSH `/pl task` claims and refreshes the heartbeat at most once a minute; `pl_status` lists live claims. Claude Code takes/refreshes the claim when `POLIER_TASK` is set and denies a write while another live session holds the task.
- New `tools/worktree.py start | finish` and `core/scope.py` worktree rule: `worktrees: required` (default at M/L on a 1.0 board; a 0.9 board stays `recommended`) denies a worker write in the main checkout while its task has a worktree ("work in <worktree path>"). `start` creates branch, slot and claim in one step; `finish` refuses uncommitted changes.
- The stop check reports changed files inside another live claim's scope as "foreign changes (task X, harness Y)" instead of blaming the current task. They never block.

**Profile L: monorepo.** Several deployable parts or packages with their own builds, integrated through contracts; L requires `packages`.
- New templates `monorepo-layout.md`, `package-ARCHITECTURE.md`, `package-AGENTS.md`, `contract.md`, `releasing.md`, `environments.md`, `versions.md`, `design-rules.md` and `gates/*.md` (Node/TS, Python, C++/CMake, WASM/Emscripten, Postgres, Playwright, visual diff, load).
- Root `ARCHITECTURE.md` states the system shape; each package gets `ARCHITECTURE.md` (≤ 400 words) and optional `AGENTS.md` (≤ 200); `docs/module-map.md` becomes the package map; briefs list root files plus the package's own files; package files only for packages created in the current stage.
- `check.py` checks package folders, package files, task scopes inside their package (contract paths excepted), a missing or unpinned `docs/versions.md`, and an environment without a smoke URL.
- New `tools/boundaries.py`: import boundaries from `packages[].may_import`, TS/JS/Python/C++ imports, `tsconfig` path aliases; exit 0/1/2; offered as gate `boundaries`.
- New `tools/contracts.py check | list`: JSON Schema 2020-12 contracts with valid/invalid fixtures, SemVer rules (major for a removed or renamed field), dependants and `contract_followups`.
- Profile-dependent budgets replace ad-hoc overrides: architecture 600/700/800, AGENTS 300/350/400, STATUS 300/500/900, briefs 800/800/900, package files 400/200. A board override needs a `reason`.

**Release and smoke.** `templates/releasing.md` and `templates/environments.md` describe trunk-based flow, tags, CI-only release, rollback and the environment × variable checklist (names only). New `tools/release_check.py` (dirty tree, untagged HEAD, tag not on the base branch, released-stage tasks not done; `--allow-untagged` for previews) as gate `release-clean`, and `tools/smoke.py` (URL status paths, headers only as `--header "Name: env:VARIABLE"`, recorded via `gate.py`). Generated `AGENTS.md` says: agents never publish; releases run in CI from tags.

**UI briefs.** `templates/task-brief.md` has an optional "UI specification" section: target values in px/ms/tokens, all applicable states, "do not", screenshot evidence. `templates/design-rules.md` is the binding token/state/accessibility reference. The rubric has a 13th criterion: a UI task without target values fails.

**Drift detection.** `tools/manifest.json` lists the SHA-256 of every shipped file; `tools/drift.py` compares the project-local copy (`.generator/`) with it and `update.sh` prints the drift report (the files that differ) before updating. `check.py` warns "local edits or outdated copy" and names the files. Extra files next to the copy are ignored.

**Guard extras.** `kill`, `pkill`, `killall` and `xargs kill` in a worker command get a warning (Claude Code: `ask`; DSH: one message per turn) — never a denial. Guarded paths compare case-insensitively on macOS and Windows, where the file system does.

**Compatibility.** No field removed; a valid 0.9 board still validates and `check.py` reports the version difference as a migration warning. Validation is now strict per schema version, so unknown fields are errors — a board with invented fields drops them or moves them anywhere outside `board.json`. `drift.py`, `slot.py`, `claim.py`, `worktree.py`, `boundaries.py`, `contracts.py`, `release_check.py`, `smoke.py` and `manifest.py` are additive. The core gains `core/slots.py`, `core/locks.py`, `core/claims.py` and `core/boundaries.py`; the DSH guard mirror in `adapters/dsh/lib/project.mjs` gains the worktree rule, case-insensitive comparison and kill detection, tested against `core/tests/write_cases.json`.

**Migration:** S and M projects need nothing. To adopt the new features: add `resources` to the board, `.polier-slot` to `.gitignore` and a `tools/dev/setup` that reads `.polier-slot`; add `"exclusive": ["e2e"]` (or `db`, `load`) to tasks whose gates share a resource; at M/L a 1.0 board defaults `worktrees` to `required`, while a 0.9 board stays on `recommended`, so an existing project is unchanged until the owner sets `required` after migrating. L projects: set `"schema_version": "1.0"`, add `packages[]` (with `may_import`), `stages[]` and `resources`, move to one package per folder with `ARCHITECTURE.md` and optional `AGENTS.md`, declare `contracts[]` with schemas and fixtures, and use `worktrees: required`. Plugin users: `git pull` in the clone, run `dsh plugin --profile <name> add ./polier` again and restart; one update is needed to get `tools/manifest.json` for drift detection. Claude Code users: replace the package copy (`./install.sh claude` or `./update.sh claude`); the hook entries stay the same, set `POLIER_TASK` so the hook claims the task (a second live claim now denies writes), and expect `ask` on process-killing commands and foreign changes in the stop message. Skill-only users: `./update.sh`; reinstall once for the manifest. Projects still on 0.9: `check.py` under 1.0 passes or prints only migration warnings (generator version, missing manifest), and schema errors only appear when a 1.0 field is used without `schema_version`.

## 0.9.0

**Core split from the harness.** The enforcement rules now live in `core/`, a Python package without any DeepSeek Harness code, so later adapters (Claude Code, git hooks) can use the same rules.

- `core/`: `check_write` (guard decision), `check_stop` and `scope_check` (changed files against a task), `run_gate` (gate records), `verify_evidence`, `load_board`, `pick_task`, `active_tasks`, `ready_tasks`. Python 3.9+, standard library only, own tests in `core/tests/`.
- The DSH plugin moved from `dsh/` to `adapters/dsh/`; `package.json` points there. Its synchronous guard keeps a JavaScript mirror of `check_write`; both are tested against one decision table, `core/tests/write_cases.json`.
- `tools/gate.py`, `tools/scope_check.py` and `tools/check.py` are thin command-line wrappers around `core/`; paths, options, output and exit codes are unchanged.
- **Claude Code adapter** in `adapters/claude-code/`: a `PreToolUse` hook checks `Write`, `Edit`, `MultiEdit`, `NotebookEdit` and the files a `Bash` command visibly writes (new `core/shell.py`); a `Stop` hook runs the stop check and sends violations back to Claude. Roles and settings come from `POLIER_*` environment variables. Example `settings.example.json`, install guide and tests with simulated hook events.
- README lists what the guard does not cover.
- `install.sh` no longer copies `__pycache__` folders and leaves out the new test folders.
- Unchanged: plugin behaviour, tool names, `/pl`, messages, `board.json` fields. The guard and the stop check keep their slightly different rule order (the guard lets `reviews/evidence/` through before `scope_write_forbidden`, the stop check checks `scope_write_forbidden` first).

**Migration:** set `generator_version` to `0.9.0`. Plugin users: `git pull` in the clone, then run `dsh plugin --profile <name> add ./polier` again and restart the harness. Skill-only users: `./update.sh`. Projects that call `tools/gate.py` keep working. Claude Code: optional, see `adapters/claude-code/README.md`.

## 0.8.0

**Renamed to Polier.** The project was the "Prompt Generator"; it now plans and enforces, so it is called Polier (German for site foreman).

- Repository `atshv/polier` (GitHub redirects the old `atshv/prompt-generator`), package `dsh-polier`, plugin row and skill `polier`.
- Tools `pl_status`, `pl_gate`, `pl_scope_check`, `pl_check` (were `pg_*`); human command `/pl` (was `/pg`).
- Messages start with `Polier:`. `install.sh` and `update.sh` install the skill as `polier`.
- Unchanged: file layout, `board.json` fields (including `generator_version`), the Python tools and their output.

**Migration:** set `generator_version` to `0.8.0`. In each project's `AGENTS.md`, replace `pg_gate` with `pl_gate` (and any other `pg_*`). Plugin users: `dsh plugin --profile <name> remove dsh-prompt-generator`, then `dsh plugin --profile <name> add ./polier`. Skill-only users: delete `~/.dsh/skills/prompt-generator/` and run `./install.sh` again. Use `/pl` instead of `/pg`.

## 0.7.1

- Plugin: `/pg reviewer` makes a session write only under `reviews/` (with or without a running task).
- `prompt/generator.md`: tool check detects the plugin; the gate rule in `AGENTS.md` names `pg_gate` or the real `gate.py` path; the human checklist sets each task `in_progress` before the worker starts; start and review prompts use `pg_status`, `pg_gate`, `pg_scope_check` and gate records.
- `guide/cheatsheet.md`: new "Before every task" checklist, evidence and `/pg` steps after every task, red flags for the guard.
- GitHub workflow runs `npm test` and `check.py` on the example for every push to `main` and every pull request.
- Example: gate rule in `AGENTS.md` updated; leftover `brief.md` and `review-feedback.md` removed (`project-input.md` and `reviews/M03.md` are the current versions).

**Migration:** set `generator_version` to `0.7.1`. Optional: take the new gate rule from `templates/AGENTS.template.md`; use `/pg reviewer` for review sessions.

## 0.7.0

**DeepSeek Harness plugin.** The package is now also an installable DSH plugin (`dsh plugin --profile <name> add …`, see `README.md`). It registers the skill with its files resolved inside the package and adds:

- a write guard: while a task is `in_progress`, a worker session may write only inside that task's `scope_write` (minus `scope_write_forbidden`); `board.json`, `STATUS.md` and `tasks/` are lead-owned, `reviews/evidence/` is always writable. Config `enforce: deny | ask | off`.
- a stop check: before a turn ends, the git diff is compared with the scope. Out-of-scope changes, including those made through `bash`, are sent back to the agent (max. 2 reminders per turn).
- tools `pg_status`, `pg_gate`, `pg_scope_check`, `pg_check`.
- the human command `/pg` (`status`, `lead`, `worker`, `off`, `task <ID>`, `render`). Roles live in memory; after a harness restart every session is a worker again.

**Tools.**

- New `tools/scope_check.py`: changed files (modified, staged, untracked, deleted, both sides of a rename) against the running task's scope. Exit 0/1/2, `--json`.
- `tools/gate.py` writes a new log and a JSON record per run (command, exit code, times, commit, dirty flag, SHA-256 of the log) and never overwrites. The last output line is `record: <path>`. New `--shell "<command>"`.
- `tools/check.py` verifies records for `done` tasks: file exists, belongs to the task, log unchanged, exit code 0, every listed gate covered. A record made on a commit outside `HEAD`'s history warns. Free-text evidence only warns.
- Earlier in this cycle: `install.sh` uses `tar` instead of `rsync`; optional `handoff` per task, shown by `render_status.py` under "Ready now"; `check.py` warns on `STATUS.md` over 300 words, context packs over about 15k tokens and done tasks without handoff.
- Tests: `npm test` (plugin against the real DSH tool registry, Python `unittest` for the tools).

**Migration:** set `generator_version` to `0.7.0`. Replace the gate line in `AGENTS.md` with the one from `templates/AGENTS.template.md`. From now on put the record paths from `gate.py`/`pg_gate` into `evidence`; old free-text evidence keeps passing with a warning. Commit `reviews/evidence/`. To use the plugin, install it and use `/pg lead` in sessions that plan, merge or edit the board.

## 0.6.0

- Package reorganised: `prompt/` (generator, rubric, DSH mapping), `guide/` (cheatsheet), root keeps entry points (`SKILL.md`, `README.md`, `CHANGELOG.md`, `VERSION`, `install.sh`, `update.sh`).
- `prompt/generator.md` states which paths belong to the package and which to the project.

**Migration:** projects: set `generator_version` to `0.6.0`. Chat users: attach `prompt/generator.md` and `prompt/rubric.md` instead of the root files. Skill installs: run `./update.sh`.

## 0.5.6

- `install.sh` and `update.sh` accept the target `claude` (`~/.claude/skills`) for Claude Code; DSH stays the default.

**Migration:** set `generator_version` to `0.5.6`.

## 0.5.5

- `install.sh` and `update.sh` target the DeepSeek Harness only (`~/.dsh/skills` or a given path).

**Migration:** set `generator_version` to `0.5.5`.

## 0.5.4

- `install.sh` and `update.sh` install, update or roll back the skill from the shell, optionally pinned to a tag.

**Migration:** set `generator_version` to `0.5.4`.

## 0.5.3

- `STATUS.md` starts with a "Ready now" list: pending tasks whose dependencies are done.
- `check.py` rejects `done` tasks without `evidence`.
- Interview questions offer a recommended default first.
- `board.json` records `generator_version`; `check.py` warns when it differs from the package.

**Migration:** add `"generator_version": "0.5.3"` to `board.json`; fill `evidence` for every `done` task; run `render_status.py`.

## 0.5.2

- `dsh.md` maps every phase to a DeepSeek Harness tool, with fallbacks; install as a DSH skill.
- All documents tightened; no rule changed.

**Migration:** none.

## 0.5.1

- `SKILL.md` entry point for installation as an agent skill.
- `check.py` cross-checks artifacts: briefs match their board entry (ID, title, acceptance IDs, `**Scope:**` line, `satisfies`), every `AD-n`/`ADR-nnnn` reference exists, `STATUS.md` matches `board.json`.
- Traceability: definition-of-done items `D1..Dn` in `docs/quality.md`, covered by the new task field `satisfies`.

**Migration:** run `render_status.py`; align briefs with the board; optionally number the definition of done and add `satisfies` (without D-IDs, `check.py` only warns).

## 0.5.0

- Package translated to English; default project language English.
- Reviews stored in `reviews/<ID>.md`; briefs always `tasks/<ID>.md`.
- `check.py` requires `.gitignore` and `base_branch`; layer names in `docs/module-map.md` are checked in English (UI, logic, data).

**Migration:** projects from 0.4 keep running with the 0.4 package; switching requires English layer names in `docs/module-map.md`, a `.gitignore`, and moving review files to `reviews/`.

## 0.4.0

German original.
