# Concept: Polier next

> Station 2 (concept), draft for the owner's approval. Polier run on itself. Owner decision 2026-11-12: the first stage is F1–F4. Research: `docs/research/neighbours.md`, `docs/research/verification-reports.md`, `docs/research/claude-plugin-eval.md`.

## Direction

Polier does not try to win at writing specs; Spec Kit, OpenSpec and Kiro do that. Its edge is what they lack: the whole line to an operated product (stores, legal, monitoring) and proof with owner gates. The 2026 reports name verification as the bottleneck of agent work. So Polier next deepens **proof** and adds a **feedback loop**: measure whether agents follow the process, learn from the records of real projects, and keep a shipped product changeable without the full line.

## Personas

| Name | Situation | Goal | Frustration today |
| --- | --- | --- | --- |
| Owner | builds one product with Polier in DSH or Claude Code, answers its dialogs | ship and keep improving the product without babysitting the agents | after release a two-line fix goes through stages; cannot see whether the agent kept the rules |
| Maintainer | changes Polier itself | improve Polier where it actually fails | no data on which rules agents break or which items cost the most rounds |
| Lead agent | plans and records in a Polier project | the next correct move without reading the whole process | a change to a shipped product has no artifact that says what changes |

## Features

| ID | Feature | Priority | Why |
| --- | --- | --- | --- |
| F1 | **Process evals**: `evals/` with 10–20 scenarios (close a station, out-of-scope write, chat "yes", delegate to a role, gate failure), run with `claude plugin eval --ablation with-without`; score and delta in CI on demand | MVP | the success signal needs a measured lead over the baseline; prerequisite for every later change |
| F2 | **Retro**: `tools/retro.py` reads the records of one or more project folders (runs, review rounds, attempts, approvals, guard denials, deferred items) and writes `docs/retro.md` with error classes, counts and the Polier file each points at | MVP | turns "change the generator only for a named class of errors" into a routine; no telemetry |
| F3 | **Change proposals**: `changes/<ID>/proposal.md` with the delta to concept, acceptance and architecture (ADDED/MODIFIED/REMOVED), linked tasks; the owner approves it, `done` merges the delta into the living docs | MVP | a shipped product changes with a reviewable artifact (OpenSpec idea, Polier evidence) |
| F4 | **Quick track**: a fix or small change as one task with brief, gates, review and handoff, without opening stations; refused when it touches platforms, traits, data or a must item | MVP | small changes stay cheap; BMAD's scale-adaptive tracks show the demand |
| F5 | **Re-checked evidence**: CI reruns the recorded gate commands of every task done in a PR and compares the result with `reviews/evidence/`; a record carries the hash of its log and of the diff it saw | next | makes forged or stale gate records visible; answers the verification bottleneck |
| F6 | **Freshness sweep**: `tools/research.py verify` lists `[VERIFY]` markers and dated sources older than N months in the package and in a project, as a scheduled CI job | next | 64 markers in templates today; store and legal facts go stale |
| F7 | **Token usage in Claude Code**: read usage from the session transcript at Stop and record it with `tools/usage.py` | next | budgets work without the lead counting tokens `[UNVERIFIED: transcript format]` |
| F8 | **Other MCP clients**: run `claude/server.mjs` from Codex, Gemini CLI or Cursor (tools only, guard where the client has hooks) | later | the server is already harness-neutral; reach without a third adapter |
| F9 | **Two review lenses by default at M/L**: spec compliance first, code quality second | later | Superpowers shows it; Polier's rubric already has both parts |

The MVP, and the first stage, is F1–F4 (owner, 2026-11-12): F1 measures, F2 learns, F3 and F4 make the line usable after the first release. F5–F9 wait for a later stage.

## User stories

- **US1** (F1) As the maintainer I want the process scenarios scored with and without Polier so that I know whether a change to Polier helps.
  - WHEN `claude plugin eval` runs the suite THEN every case reports a score for both arms and the run prints the delta.
  - WHEN a change makes a case worse than on `main` THEN the CI job fails and names the case.
- **US2** (F2) As the maintainer I want the failure classes of real projects so that I change Polier where it fails.
  - WHEN `tools/retro.py` runs on project folders THEN `docs/retro.md` lists each error class with its count, an example record and the Polier file it points at.
  - WHEN a folder has no Polier records THEN it is skipped with a reason, and nothing is written into it.
- **US3** (F3) As the owner I want to change a shipped product through a proposal so that concept and acceptance stay true.
  - WHEN the lead drafts `changes/C01/proposal.md` THEN `pl_approval` (scope_change) asks the owner and the proposal is linked to its tasks.
  - WHEN every linked task is done THEN the delta is merged into `docs/concept.md` and `docs/quality.md`, the proposal is archived, and `check.py` finds no story without a done scenario.
- **US4** (F4) As the owner I want a small fix without the full line so that it costs one task.
  - WHEN the owner asks for a fix THEN the lead opens one quick task with brief, gates and review, and no station reopens.
  - WHEN the change touches platforms, traits, the data model or a must item THEN the quick track refuses and names the proposal path instead.

## Alternatives

| Alternative | What it does well | Why Polier next anyway |
| --- | --- | --- |
| GitHub Spec Kit | constitution and cross-artifact analysis before coding | stops at implementation; no release, store, legal or operate items, no evidence records |
| OpenSpec | small change proposals with deltas into living specs | no gates, no owner approvals, no product catalog; F3 takes the idea into Polier's records |
| BMAD Method | many role agents, tracks by project size | documents over proof; no write guard or recorded gates |
| Superpowers | enforced TDD, subagent per task, two-stage review | a skill set, not a factory line; no catalog or records |

## Costs

| Item | Per month | Source/date |
| --- | --- | --- |
| Hosting, services | 0 | no service; everything runs locally or in GitHub Actions |
| Eval runs (F1) | tokens of ≤ 20 cases × 2 arms per run, on demand and before releases | `claude plugin eval --help`, 2026-11-12; price per token [VERIFY] |
| CI minutes | within the free tier of a public repository `[UNVERIFIED]` | — |

## Risks

| Risk | Effect | How the plan reduces it |
| --- | --- | --- |
| Evals are flaky or expensive | the score is noise, nobody runs it | few cases, deterministic graders first (tool used, file unchanged), LLM graders second; run on demand |
| Polier grows heavier | owners skip it | quick track (F4); every feature must remove work somewhere or be measured by F1 |
| Retro reads private project data | trust | local only, folders named by the owner, output stays in the maintainer's folder; no upload |
| Re-checked evidence slows CI | merges wait | only tasks done in the PR, gates marked `exclusive` run alone |
