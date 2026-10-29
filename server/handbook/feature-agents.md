# Agents and integrations

Put agents to work, ask questions about the project and see what CI says — all without leaving the dashboard.

## Sessions

Start a headless agent for a task or without one, watch its transcript live, stop it. See [Run agents headless](polier:agent-sessions).

## Assistant

Ask questions about the project in plain language: "What blocks the web app stage?", "Which tasks are over budget?". The assistant reads a compact briefing of the board, approvals, claims, sessions and intake. It cannot write anything itself; when it suggests an action — a status change, a new task, a gate run, a session — the suggestion appears as a card with **Apply**, and only your click executes it through the validated API.

## Automations

Rules that turn state into suggestions, evaluated as a dry run. See [Automations](polier:automations).

## GitHub

Open pull requests and recent workflow runs from the authenticated `gh` CLI, mapped to tasks by branch (`task/<ID>`). Read-only, cached for 30 seconds, and it explains what is missing when it cannot connect.
