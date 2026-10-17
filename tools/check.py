#!/usr/bin/env python3
"""Prüft ein generiertes Projekt gegen die Regeln des Prompt-Generators.

Nutzung:
    python3 tools/check.py examples/minimal-cli
    python3 tools/check.py /pfad/zum/projekt

Keine externen Abhängigkeiten. Exit 0 = keine Fehler (Warnungen erlaubt),
Exit 1 = mindestens ein Fehler.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REQUIRED = [
    "ARCHITECTURE.md",
    "AGENTS.md",
    "STATUS.md",
    "board.json",
    "docs/module-map.md",
    "docs/quality.md",
]

PLACEHOLDER = re.compile(r"<\.\.\.>|<Name>|<Projektname>|\bTODO\b|\bTBD\b")
STATUS = {
    "pending", "claimed", "in_progress", "verifying", "review",
    "rework", "done", "blocked", "failed",
}
QUESTION_STATUS = {"open", "answered", "dropped"}


def words(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").split())


def normalized(path: str) -> str:
    return path.strip().replace("\\", "/").rstrip("/")


def paths_overlap(a: str, b: str) -> bool:
    a, b = normalized(a), normalized(b)
    return a == b or a.startswith(b + "/") or b.startswith(a + "/")


def check_links(root: Path, errors: list[str]) -> None:
    for path in root.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        for target in re.findall(r"\]\(([^)#]+)(?:#[^)]*)?\)", text):
            target = target.strip()
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            if not (path.parent / target).resolve().exists():
                errors.append(f"{path.relative_to(root)}: Link zeigt ins Leere: {target}")


def check_board(root: Path, errors: list[str], warnings: list[str]) -> None:
    path = root / "board.json"
    try:
        board = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        errors.append(f"board.json: kein valides JSON: {exc}")
        return

    if board.get("profile") not in {"S", "M", "L"}:
        errors.append("board.json: profile muss S, M oder L sein")
    tasks = board.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        errors.append("board.json: tasks fehlt oder ist leer")
        return

    ids = [t.get("id") for t in tasks]
    if len(ids) != len(set(ids)):
        errors.append("board.json: doppelte Task-IDs")
    known = set(ids)

    for task in tasks:
        tid = task.get("id", "?")
        for key in ("title", "goal", "status", "depends_on", "complexity",
                    "stage", "scope_write", "acceptance", "gates"):
            if key not in task:
                errors.append(f"{tid}: Pflichtfeld fehlt: {key}")
        if task.get("status") not in STATUS:
            errors.append(f"{tid}: unbekannter Status {task.get('status')!r}")

        complexity = task.get("complexity")
        if not isinstance(complexity, int) or isinstance(complexity, bool):
            errors.append(f"{tid}: complexity muss eine ganze Zahl sein, ist {type(complexity).__name__}")
        elif not 1 <= complexity <= 10:
            errors.append(f"{tid}: complexity muss 1–10 sein")
        elif complexity >= 7:
            errors.append(f"{tid}: complexity >= 7 — Task teilen")

        for dep in task.get("depends_on", []):
            if dep not in known:
                errors.append(f"{tid}: unbekannte Abhängigkeit {dep}")
        if not task.get("scope_write"):
            errors.append(f"{tid}: scope_write fehlt")
        if not task.get("acceptance"):
            errors.append(f"{tid}: acceptance fehlt")
        if not task.get("gates"):
            errors.append(f"{tid}: gates fehlt")
        for key in ("scope_read", "scope_write_forbidden"):
            if key in task and not isinstance(task[key], list):
                errors.append(f"{tid}: {key} muss eine Liste sein")

        for allowed in task.get("scope_write", []):
            for forbidden in task.get("scope_write_forbidden", []):
                if paths_overlap(allowed, forbidden):
                    errors.append(
                        f"{tid}: Pfad ist gleichzeitig in scope_write und scope_write_forbidden: {allowed} / {forbidden}"
                    )

    # Zyklen
    graph = {t["id"]: t.get("depends_on", []) for t in tasks if "id" in t}
    state: dict[str, int] = {}

    def visit(node: str, stack: list[str]) -> None:
        if state.get(node) == 1:
            errors.append("board.json: Zyklus: " + " -> ".join(stack + [node]))
            return
        if state.get(node) == 2:
            return
        state[node] = 1
        for dep in graph.get(node, []):
            if dep in graph:
                visit(dep, stack + [node])
        state[node] = 2

    for node in graph:
        visit(node, [])

    # Überlappende Schreib-Scopes in derselben Parallelgruppe
    groups: dict[str, list[dict]] = {}
    for task in tasks:
        group = task.get("parallel_group")
        if group:
            groups.setdefault(group, []).append(task)
    for group, group_tasks in groups.items():
        for i, a in enumerate(group_tasks):
            for b in group_tasks[i + 1:]:
                for pa in a.get("scope_write", []):
                    for pb in b.get("scope_write", []):
                        if paths_overlap(pa, pb):
                            errors.append(
                                f"Parallelgruppe {group}: Scope-Überlappung {a.get('id')} / {b.get('id')}: {pa} vs {pb}"
                            )

    # S-Nebenstrang braucht eine gemeinsame Vertrags-Task
    if board.get("profile") == "S":
        by_id = {t.get("id"): t for t in tasks if isinstance(t, dict)}
        for group, group_tasks in groups.items():
            if len(group_tasks) < 2:
                continue
            common = set(group_tasks[0].get("depends_on", []))
            for task in group_tasks[1:]:
                common &= set(task.get("depends_on", []))
            contracts = [
                tid for tid in common
                if tid in by_id and any(
                    str(path).startswith("docs/contracts/")
                    for path in by_id[tid].get("scope_write", [])
                )
            ]
            if not contracts:
                errors.append(
                    f"Parallelgruppe {group}: S-Nebenstrang braucht eine gemeinsame Vertrags-Task "
                    f"mit scope_write unter docs/contracts/, von der beide Tasks per depends_on abhängen."
                )

    # Entscheidungen und offene Fragen (optional, aber wenn vorhanden prüfen)
    for decision in board.get("decisions", []):
        if not isinstance(decision, dict):
            errors.append("board.json: decisions-Eintrag ist kein Objekt")
            continue
        for key in ("date", "id", "title"):
            if key not in decision:
                errors.append(f"board.json: decision {decision.get('id', '?')} fehlt {key}")
        file = decision.get("file")
        if file and not (root / file).exists():
            errors.append(f"board.json: ADR-Datei fehlt: {file}")

    for question in board.get("open_questions", []):
        if not isinstance(question, dict):
            errors.append("board.json: open_questions-Eintrag ist kein Objekt")
            continue
        qid = question.get("id", "?")
        if "question" not in question:
            errors.append(f"board.json: Frage {qid} hat keinen Text")
        if question.get("status") not in QUESTION_STATUS:
            errors.append(f"board.json: Frage {qid} hat ungültigen Status")
        for blocked in question.get("blocks", []):
            if blocked not in known:
                errors.append(f"board.json: Frage {qid} blockiert unbekannte Task {blocked}")


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    errors: list[str] = []
    warnings: list[str] = []

    for name in REQUIRED:
        if not (root / name).exists():
            errors.append(f"Pflichtdatei fehlt: {name}")

    if (root / "ARCHITECTURE.md").exists():
        count = words(root / "ARCHITECTURE.md")
        if count > 800:
            errors.append(f"ARCHITECTURE.md: {count} Wörter (max. 800)")
        elif count < 300:
            warnings.append(f"ARCHITECTURE.md: nur {count} Wörter — für ein kleines Projekt okay, sonst prüfen.")

    for brief in sorted((root / "tasks").glob("M*.md")):
        count = words(brief)
        if not 400 <= count <= 800:
            errors.append(f"{brief.relative_to(root)}: {count} Wörter (Ziel 400–800)")

    for path in [root / "ARCHITECTURE.md", root / "AGENTS.md", root / "STATUS.md",
                 *sorted((root / "tasks").glob("M*.md"))]:
        if path.exists():
            for match in PLACEHOLDER.finditer(path.read_text(encoding="utf-8")):
                errors.append(f"{path.relative_to(root)}: Platzhalter gefunden: {match.group(0)}")

    if (root / "AGENTS.md").exists():
        agents = (root / "AGENTS.md").read_text(encoding="utf-8")
        for needle in ("git status", "Commit", "Scope"):
            if needle.lower() not in agents.lower():
                errors.append(f"AGENTS.md: '{needle}' fehlt")

    if (root / "docs/module-map.md").exists():
        module_map = (root / "docs/module-map.md").read_text(encoding="utf-8")
        for needle in ("UI", "Logik", "Daten"):
            if needle.lower() not in module_map.lower():
                errors.append(f"docs/module-map.md: Schicht '{needle}' fehlt")

    if (root / "board.json").exists():
        check_board(root, errors, warnings)

    check_links(root, errors)

    for warning in warnings:
        print(f"WARN: {warning}")

    if errors:
        print(f"FAIL: {len(errors)} Befund(e) in {root}\n")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"OK: {root} erfüllt die Pflichtprüfungen." + (f" ({len(warnings)} Warnung(en))" if warnings else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
