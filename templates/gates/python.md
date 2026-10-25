# Gate Catalogue: Python

> Copy the gates the project has to `docs/gates/python.md`; delete the rest. Replace every `<...>`; use only flags verified in the manifest or docs.

| Gate | Command shape | Expected |
| --- | --- | --- |
| `lint` | `uv run ruff check .` or `python3 -m ruff check .` [VERIFY: from manifest/docs] | exit 0, no errors |
| `format` | `uv run ruff format --check .` [VERIFY: from manifest/docs] | exit 0, files already formatted |
| `types` | `uv run mypy <module>` or `python3 -m mypy <module>` [VERIFY: from manifest/docs] | exit 0, "Success: no issues found" |
| `tests` | `uv run pytest` or `python3 -m pytest` [VERIFY: from manifest/docs] | exit 0, all tests pass |
| `build` | `uv build` or `python3 -m build` [VERIFY: from manifest/docs] | exit 0, dist artifacts written |

- Single test: `<runner> <file>::<test>` [VERIFY: from manifest/docs].
- Sync the environment first with the project command (`uv sync`, `pip install -e .[dev]`) [VERIFY: from manifest/docs]; a gate never installs packages.

## Pitfalls

- Use the project's virtualenv or `uv` runner; a bare `python3` may be the wrong interpreter.
- `pytest` discovery depends on the working directory and the `pyproject.toml`/`pytest.ini` settings.
- Fixtures leak state: use a per-slot test database or `tmp_path` and reset it (`postgres.md`).
- `__pycache__/`, `.pytest_cache/`, `.venv/` and coverage files belong in `.gitignore`.
- Type checking a partial tree passes for the wrong reason; run it on what CI names.
- E2E tests are their own gate and may need the `exclusive` lock.
