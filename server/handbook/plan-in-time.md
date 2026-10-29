# Plan in time: estimates, timeline and cycles

Polier schedules work from what it already knows — dependencies and estimates — and lets you pin dates where they matter.

## Estimates

Set `estimate_hours` per task in the drawer's **Properties**, in the Plan editor or in bulk. The worklog compares it with the actual hours derived from sessions and attempts; no time tracking needed.

## The timeline

**Timeline** places every task after its dependencies, sized by its estimate (or complexity × 2 h) at `defaults.hours_per_day` (default 4) and inside sequential stage lanes. Done tasks sit at their real finish date.

- **Days / Weeks** switch the scale.
- The **critical path** is marked with ◆; overdue targets are flagged.
- Click a bar to open the task.

## Fixed dates

Two optional fields override the schedule for one task: `planned_start` and `target` (`YYYY-MM-DD`).

```bash
python3 tools/plan.py update WEB-02 --planned-start 2026-11-03 --target 2026-11-07
```

## Cycles

Each stage is a cycle with a goal, exit criteria, exit gates and an owner decision. **Cycles** shows progress, effort and a burndown built from the run records. Set the decision when the stage is complete:

```bash
python3 tools/plan.py stage engine-spike decision --decision continue
```
