# Tracking views

Five views answer "what happened, and is it good enough?": decisions, history, requirement coverage, package health and the numbers.

## Approvals

Pending, granted and denied owner decisions. Request one, grant or deny with a note. See [Reviews and approvals](polier:reviews-and-approvals).

## Activity

Every run event, gate result, review and approval, newest first, filterable by task.

## Coverage

Requirements from `docs/quality.md` (lines like `**D3** …`) joined with the tasks that satisfy them and their evidence. Each requirement is *covered*, *partial*, *open* or *missing*; codes that tasks reference without a definition are reported.

## Modules

The packages of the board as modules: tasks and status counts, health (*ok*, *watch*, *attention*, *done*), README/ARCHITECTURE presence, contract versions, tokens and effort. Tasks without a package are listed separately.

## Analytics

| Metric | Built from |
|---|---|
| completion, status counts | the board |
| throughput per week | `done` events in `runs/` |
| cycle time per stage | first work event to done |
| gate pass rate | gate records |
| rework rate, blocked age | state events |
| estimate vs actual | the worklog |
| tokens per stage, sessions | usage records |
