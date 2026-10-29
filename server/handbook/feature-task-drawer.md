# The task drawer

Click any task — on a card, a row, a chip or a search result — and the drawer opens on the right. `Esc` closes it; the URL (`#/board/ENG-01`) can be shared.

## Header

ID, status, title, stage, package, complexity, review round and attempt. Below it:

- **Status** — only the transitions the state machine allows; the suggested next step is highlighted.
- **Note** — appears when a reachable status needs a reason (rework, blocked, failed).
- **Claim** — take or release the claim; **Copy CLI** copies the matching `state.py` or `gate.py` command.

## Tabs

| Tab | Shows |
|---|---|
| **Brief** | properties (labels, estimate, dates), goal, why, acceptance and the full brief |
| **Gates** | each gate with its records; run a gate with a command |
| **Run** | the event log of every attempt |
| **Review** | the verdict and findings |
| **Evidence** | gate logs from `reviews/evidence/` |
| **Handoff** | the handoff note for the next task |
| **Session** | start or watch a headless agent for this task |
| **Worklog** | attempts, sessions, tokens and hours against the estimate |

**Properties** fold into one summary line; open them to edit labels, the estimate and planning dates.
