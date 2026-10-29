# Troubleshooting and FAQ

Answers to the questions that come up most often.

## The dashboard says "no board.json yet"

The folder has no plan. Use the interview in the **Plan editor**, or start the server for the right folder: `python3 tools/serve.py /path/to/project`.

## A status change is refused

The message lists what is missing and the command that produces it. Typical causes:

- a dependency is not `done` yet → finish it first, or check **Dispatch**
- a gate has no passing record → run it from the **Gates** tab
- no review verdict → write `reviews/<ID>.md` with `verdict: pass`
- the attempt or round limit is reached → the task escalates; decide in the drawer

## "state-changing requests need the X-Polier-Action: 1 header"

You called a write endpoint from your own script. Add the header; see [Authentication](polier:api-authentication).

## The live indicator shows "Offline"

The server stopped or the connection dropped. The page reconnects with backoff; restart `serve.py` if needed. With `?noevents=1` the page runs without live updates.

## GitHub shows "unavailable"

The panel needs a GitHub remote and an authenticated `gh` CLI (`gh auth login`). It never blocks the rest of the dashboard.

## Where are my session transcripts?

In `<git-common-dir>/polier/dashboard/sessions/<id>/`, outside the working tree, shared by all worktrees.

## Can several people use one dashboard?

It is a local tool for one operator and one project. For a shared read-only view, run it with `--read-only` and a token behind a reverse proxy — never open to a network without both.
