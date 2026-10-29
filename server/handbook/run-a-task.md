# Run a task end to end

Take one task through every checkpoint, from the dashboard or the CLI. Both write the same files.

## 1. Pick a ready task

**Dispatch** shows the next wave: tasks whose dependencies and stage are open. **Your Work → Ready now** lists the same tasks. Open one to see its brief.

## 2. Claim and start

In the drawer: **Claim task**, then **→ In progress**.

```bash
python3 tools/claim.py take ENG-01 --harness cli --session me
python3 tools/state.py set ENG-01 in_progress
```

The transition is refused while a dependency is open or the attempt limit is reached; the message names the blocking task.

## 3. Work inside the scope

The agent edits only files in `scope.write`. The write guard denies everything else and logs the attempt in `runs/<ID>.json`. If the task needs a file outside its scope, that is a plan change: update the task in the Plan editor, or request an approval.

## 4. Run the gates

Open the **Gates** tab and run each gate. The command comes from `docs/quality.md` or from your saved gate commands in Settings.

```bash
python3 tools/gate.py --task ENG-01 --name unit --shell "ctest --test-dir build"
```

Each run streams into the **Jobs** tray at the bottom and writes a record with exit code, duration and log checksum.

## 5. Verify, review, finish

1. **→ Verifying** checks that every gate has a passing record.
2. **→ Reviewing** hands the task to a reviewer (a person or a reviewer session).
3. The reviewer writes `reviews/ENG-01.md` with `verdict: pass` or `verdict: fail` and findings.
4. **→ Done** needs the passing verdict and a handoff note.

> [!NOTE]
> A failing review sends the task to `rework` with a note. The round counter rises; after the policy limit the task escalates instead of looping forever.

## What you see afterwards

- The **Worklog** tab: attempts, gate runs, sessions, tokens and hours against the estimate.
- **Activity**: every state change, gate and review in order.
- **Analytics**: throughput, cycle time and gate pass rate update on their own.
