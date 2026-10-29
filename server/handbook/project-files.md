# Project files

What Polier keeps where. Committed files are the project's memory; runtime files are local conveniences you can delete.

## Committed

| Path | Contents | Written by |
|---|---|---|
| `ARCHITECTURE.md` | rules every module follows | generator, then reviewed edits |
| `AGENTS.md` | commands and rules for agents | generator |
| `board.json` | stages, tasks, dependencies, scopes, status | `state.py`, the plan editor |
| `policy.json` | limits, approvals, protected paths, denied commands | generator, owner |
| `tasks/<ID>.md` | the brief of one task | generator, lead |
| `runs/<ID>.json` | attempts, events, gate records, usage | the tools |
| `reviews/<ID>.md` | review verdict and findings | reviewer |
| `reviews/evidence/` | gate logs referenced by the records | `gate.py` |
| `reviews/approvals/AP-NNN.json` | approval requests and decisions | `approve.py` |
| `dashboard.json` | feature flags, labels, defaults | Settings |
| `views/<id>.json` | saved filters, grouping, sorting | Board / Table |
| `intake/<id>.json` | intake proposals and decisions | Intake |
| `templates/tasks/<id>.json` | task templates | Plan editor, drawer |
| `automations.json` | automation rules | Automations |
| `STATUS.md` | generated progress summary | `render_status.py` |

## Runtime (not committed)

Stored in `<git-common-dir>/polier/dashboard/`, shared by all worktrees:

| Path | Contents |
|---|---|
| `config.json` | session provider, gate command overrides, UI preferences |
| `plan.json` | interview answers |
| `jobs/<id>.log` | gate, check and audit job output |
| `sessions/<id>/` | prompt, settings, transcript of a headless session |
| `inbox.json`, `pages.json` | read marks, page favorites |
| `assistant/<id>.json` | assistant conversations |

Deleting the runtime folder loses transcripts, logs and read marks — never project state.
