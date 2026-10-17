# Quality: bm

## Definition of done (project)

- **D1** `bm add`, `bm list`, `bm search` work on a fresh DB.
- **D2** A duplicate canonical URL is rejected (exit 2).
- **D3** `bm export` and `bm import` preserve all entries and tags.
- **D4** Lint, types and tests are green.
- **D5** An E2E run on a fresh DB is documented and works.
- **D6** The README explains installation and the five core commands.

## Gates

| Gate | Command | Expected |
|---|---|---|
| Lint | `uv run ruff check .` | no errors |
| Types | `uv run mypy bm` | no errors |
| Tests | `uv run pytest` | all green |
| E2E | `uv run pytest tests/e2e -m e2e` | all green |
| Manual | `bm add` → `bm list` → `bm search` | visible matches, exit 0 |

A gate passes when command, exit code and expected output match; the output is the evidence. The task passes when all gates are green, every acceptance criterion is evidenced and the reviewer gives `pass` with no blockers.

## Review

- The reviewer is not the author.
- The reviewer sees the diff, acceptance criteria and gate output, not the author's reasoning.
- Every finding: `severity`, `file`, `line`, `criterion`, `issue`, `evidence`, `fix_hint`.
- Results go to `reviews/Mxx.md`.
- No style questions unless they cause defects.
- At most 5 findings per round.

## Human checklist per task

- [ ] Gates actually run and output seen.
- [ ] Acceptance A1..An evidenced individually.
- [ ] Diff only within scope.
- [ ] No tests changed without approval.
- [ ] No placeholders/TODOs.
- [ ] `STATUS.md` regenerated from the board.
- [ ] Commit with task ID.

## Deliberately not checked (V1)

- Windows compatibility
- Performance with > 10,000 entries
- CLI accessibility (colours/screen readers)
- Icons, web UI, sync
