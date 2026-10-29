# Introduction

Polier plans an AI coding project before the first line of code and then keeps the agents to that plan. This handbook explains the workflow and the dashboard, step by step.

> [!NOTE]
> Everything Polier knows lives in plain files in your repository: `board.json`, `policy.json`, `runs/`, `reviews/` and the Markdown docs. The dashboard reads and writes those files through the same rules as the command-line tools. Nothing is hosted, nothing is sent anywhere.

## What you get

- **A plan you approved.** An interview turns your idea into a one-page architecture, stages and a task graph with allowed files, acceptance criteria and gates.
- **Agents that stay in scope.** The write guard blocks every file outside the current task, and denied commands stay denied for every role.
- **Proof instead of claims.** A task only reaches `done` with recorded gate runs, a passing review and a handoff.
- **A cockpit for the owner.** The dashboard shows what is ready, what is blocked and what needs your decision.

## How the work flows

1. **Plan.** Answer the interview, review the generated architecture and board, approve.
2. **Dispatch.** Polier shows the next wave: tasks whose dependencies are done.
3. **Build.** An agent claims a task, works inside its scope and runs the gates.
4. **Verify and review.** Gate records are checked, a reviewer writes a verdict.
5. **Decide.** You grant approvals, close stages and accept or reject new ideas.

## Where to go next

- [Quickstart](polier:quickstart) — start the dashboard and move your first task.
- [Core concepts](polier:concepts) — board, statuses, gates, claims and approvals.
- [AI in Polier](polier:ai-overview) — assistant, agents, skills and MCP.
- [API introduction](polier:api-introduction) — script the dashboard from your own tools.
