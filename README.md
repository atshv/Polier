# Prompt-Generator für modulare KI-Projekte

**Version 0.4 · Meta-Prompt-Paket · Zielumgebung DeepSeek Harness**  
**English summary:** [README.en.md](README.en.md)

Ein Generator, der aus einem Projekt-Brief ein startbares Projekt-Gerüst macht:

- **eine Seite Architektur** statt einer überladenen Design-Datei,
- **ein Task-Board mit Abhängigkeiten und Schreib-Scopes**,
- **3–5 just-in-time Task-Briefs** statt 25 Prompts vor dem ersten Code,
- **AGENTS.md, STATUS.md und Repo-Struktur**,
- **Lint + unabhängiger Critic + Kaltstart-Test** statt Selbstbewertung.

Der Generator baut nicht das Projekt. Er baut die Dateien, mit denen ein anderer Agent – oder ein Team aus Agents – es baut.

---

## Quickstart

1. **Das Paket (`generator.md`, `templates/`, `rubric.md`, `tools/`) in einen Chat bzw. Ordner legen.** Eingabeblock in `generator.md` ausfüllen (Vorhaben, Modus, Profil, Sprache, Budget). Bei Brownfield liegt das Paket am besten in `.generator/` im Projektordner; der Generator trägt den Ordner in `.gitignore` ein.
2. **Interview beantworten.** Maximal 10 Fragen pro Runde, die schwierigen zuerst.
3. **Architektur und Task-DAG freigeben.** Bei S zusammen mit einem „ja“; bei M/L getrennt. Erst danach schreibt der Generator die Dateien in den Arbeitsordner der Session.
4. **Projekt starten:** erste Session mit `tasks/M01.md`, Plan zeigen lassen, freigeben, umsetzen.
5. **Review in neuer Session** mit dem Review-Prompt aus `generator.md` Phase I.
6. **Nächste Etappe:** nur die nächsten 3–5 Briefs erzeugen lassen.

Das Paket wird als **Ordner** benutzt: `generator.md` + `templates/` + `rubric.md` + `tools/`. Der Generator schreibt in den Arbeitsordner der Session; ohne Dateisystem gibt er Codeblöcke aus. `generator.md` allein reicht nicht, weil die Artefakt-Vorlagen dort absichtlich nicht dupliziert sind.

## Prüfen

```bash
python3 tools/check.py examples/minimal-cli
python3 tools/render_status.py examples/minimal-cli --out STATUS.md
```

`check.py` prüft Board, Budgets, Links, Platzhalter und Pflichtdateien. `render_status.py` erzeugt `STATUS.md` aus `board.json`.

---

## Das erzeugte Projekt enthält

- **Git-Repo:** `main`, `.gitignore`, Initial-Commit `chore: scaffold`, Task-Branches, ein Commit pro Task (Task-ID + Titel). Kein Push, kein Remote.
- **Modulstruktur:** `docs/module-map.md` mit Schichten (UI/Screens, Logik, Daten), Ordnern und erlaubter Importrichtung. Die Architektur verlinkt sie nur.
- **`AGENTS.md`:** Befehle, Abweichungen, Regeln, Scope-, Git- und Schichtregel. Keine Architektur, kein Fortschritt.
- **`ARCHITECTURE.md`:** eine Seite Invarianten, Nicht-Ziele, Randbedingungen, Gates, Deferred, Links.
- **`STATUS.md` + `board.json`:** Fortschritt aus dem Board, nicht handgepflegt.
- **`tasks/M01..`:** die nächsten 3–5 JIT-Briefs mit Kontext-Pack, Gates und Ausgabeformat.
- **`docs/`:** Modulstruktur, Datenmodell, Qualität, ADRs, Verträge, Domäne – nur was das Projekt braucht.
- **S bleibt schlank:** Pflicht sind `ARCHITECTURE.md`, `AGENTS.md`, `board.json`/`STATUS.md`, `docs/module-map.md`, `docs/quality.md` und `tasks/`. ADRs, Contracts und Domain nur bei konkretem Inhalt. Nebenstrang bei S nur mit getrenntem Schreibbereich und vorherigem Vertrag in `docs/contracts/`; damit wird `docs/contracts/` Pflicht.
- **Sicherheit:** Repo-Inhalte sind Daten, keine Anweisungen; Bibliotheken/APIs nur aus Doku oder Manifest (Secrets-Policy: `generator.md` › Regeln).

---

## Dateien

| Datei | Zweck | Wann lesen |
|---|---|---|
| [`generator.md`](generator.md) | Der Meta-Prompt: Phasen 0–I, Regeln, Freigaben, Prompts; verweist auf `templates/`. | Zuerst |
| [`cheatsheet.md`](cheatsheet.md) | Bedienung für den Menschen: Phasen, Checklisten, rote Flaggen; verweist auf die Prompts in `generator.md`. | Beim Arbeiten |
| [`rubric.md`](rubric.md) | 12-Punkte-Rubrik, Lint, Critic-Prompt, Kaltstart-Test. | Vor jeder Freigabe |
| [`dsh.md`](dsh.md) | DSH-Mapping: Subagents, Agent Teams, Board, Worktrees, Profile S/M/L. | Wenn das Projekt läuft |
| [`templates/`](templates/) | Vorlagen für Architektur, Modulstruktur, AGENTS, Task-Brief, Board, ADR, Review. `STATUS.md` wird von `tools/render_status.py` erzeugt. | Beim Anpassen |
| [`tools/`](tools/check.py) | `check.py` prüft ein Projekt; `render_status.py` erzeugt `STATUS.md` aus `board.json`. | Vor der Freigabe |
| [`examples/minimal-cli/`](examples/minimal-cli/) | Vollständiges Beispiel: ein kleines CLI-Projekt mit 6 Tasks. | Zum Vergleichen |

> Die Dateien unter `templates/` sind **Vorlagen mit Platzhaltern**. Sie sind keine Anweisungen für dieses Paket und gelten nicht für die Arbeit am Generator selbst.

---

## Die Idee in sechs Regeln

1. **Architektur ist ein Vertrag, keine Wissensdatenbank.** Maximal 800 Wörter. Nur Entscheidungen, die zwei unabhängig gebaute Module sonst inkompatibel treffen würden. Alles andere wird verlinkt.
2. **Eine Datei, ein Zweck.** `AGENTS.md` = Regeln, `ARCHITECTURE.md` = Invarianten, `STATUS.md` = Fortschritt, `docs/` = Details. Kein Monolith.
3. **JIT statt Wasserfall.** Nur die nächsten 3–5 Task-Briefs. Spätere Etappen bleiben grob, bis sie dran sind.
4. **Die richtige Anzahl Agents.** Default S: ein Schreiber, ein Reviewer. M/L nur, wenn mindestens zwei Aufgaben über eine Etappe gleichzeitig laufen können, ohne dieselben Dateien zu schreiben.
5. **Gates vor Meinung.** Build, Tests, Lint zuerst; LLM-Review danach. Kein Selbst-Score.
6. **Ein Schreiber pro Pfad.** Keine zwei Agents schreiben gleichzeitig dieselbe Datei. Scopes, Worktrees, Board.

---

## Was bewusst nicht enthalten ist

- **Keine Software.** Kein CLI, keine Web-App, keine Datenbank. Das Paket ist Markdown, das in jeden Chat passt.
- **Keine 25 Modul-Prompts vorab.** Der Generator schreibt nur, was als Nächstes gebraucht wird.
- **Keine Rollen für Solo-Projekte.** S braucht keinen Agentenvertrag.
- **Keine Docker-Sandbox, kein LLM-Mediator, kein Cost-Tracker als Default.** Das sind Lösungen für Probleme, die M/L später bekommen können.
- **Kein Selbst-Score.** Der Autor bewertet nicht seine eigene Arbeit; der Critic ist unabhängig.
- **Keine Projekt-spezifischen Inhalte.** Das Beispiel ist neutral; dein Brief kommt oben in den Eingabeblock.

---

## Für wen

- **Solo-Entwickler**, die mit einem Agenten ein kleines bis mittleres Projekt bauen und nicht in Prompt-Chaos versinken wollen.
- **Teams mit 2–3 Agents**, die disjunkte Module parallel bauen und trotzdem einen grünen Main behalten wollen.
- **Menschen, die bereits einen Haufen Prompts haben** und daraus ein wartbares Projekt-Gerüst machen wollen.

Nicht gedacht für: Ein-Satz-Demos, bei denen ein einzelner Prompt reicht. Dann ist der Generator Overhead.

---

## Wie du das Paket anpasst

1. **Eine Regel ändern?** Nur mit Grund: Welche Fehlerklasse hat gefehlt? Änderung in `generator.md` und, falls nötig, in `rubric.md`.
2. **Eine Vorlage ändern?** Nur in `templates/`. `generator.md` verweist darauf und enthält keine Kopien; so kann nichts auseinanderlaufen.
3. **Ein neues Profil?** Erst messen, ob S/M/L nicht reichen. Neue Profile erhöhen die Komplexität des Generators.
4. **Version erhöhen** und einen Golden Brief durchlaufen lassen. First-Pass-Green messen, nicht den eigenen Score (den vergibt der Critic).

---

## Stand und nächste Schritte

**v0.4** – S-Profil nach Gleichzeitigkeit, Phase 0+Interview zusammengelegt, C+D ein gemeinsames Ja, keine Critics vor der Freigabe bei S, ein Subagent in Phase H, `board.json` und schlankes S-Dateiset, Nebenstrang nur mit Vertrags-Task (`docs/contracts/`).

**v0.3** – Beispiel-Faktenfehler korrigiert (`IntegrityError`, Gate-Suche, nicht-deterministisches Gate), Vorlagen entdoppelt (kanonisch in `templates/`), Prompts nur noch in `generator.md`, `scope_write_forbidden` statt mehrdeutigem Feld, Schichtmodell vereinheitlicht, echte Tools (`check.py`, `render_status.py`), LICENSE + englische README.

**v0.2** – Definitionen für Gate/Task-bestanden/Kaltstart, Mobile-/Web-Secrets-Policy, Git-Repo und Modulstruktur explizit, „nichts erfinden“ an Manifeste gebunden, Abbruch-Regel korrigiert.

Mögliche v0.5:
- Golden-Brief-Set + kleines Eval-Skript (First-Pass-Green, Rework-Runden).
- Zwei Beispielprojekte (Web-App, Mobile) statt nur CLI.
- Generator-Variante für Claude Code / Codex (andere Tool-Namen, gleiche Artefakte).
- Übersetzte Fassung (Englisch) für Tool-Kompatibilität.

---

## Quellen und Einflüsse

Die Ideen sind bewusst nicht neu; sie sind aus bewährten Mustern destilliert:

- [BMAD-METHOD: Architecture Spine](https://github.com/bmad-code-org/BMAD-METHOD) – Invarianten, AD-IDs, „Deferred“, Litmus-Test.
- [GitHub Spec Kit](https://github.com/github/spec-kit) – Trennung von Spec, Plan, Tasks, Contracts.
- [Claude Code Agent Teams](https://code.claude.com/docs/en/agent-teams) – Task-Board, Schreibrechte, Worktrees, Review-Unabhängigkeit.
- [Cognition: Don't Build Multi-Agents](https://cognition.com/blog/dont-build-multi-agents) – Kontext teilen, parallele Schreiber vermeiden.
- [Anthropic: Building Effective Agents](https://www.anthropic.com/engineering/building-effective-agents) – einfach starten, Evaluator-Optimizer.
- [AGENTS.md](https://agents.md/) – offenes Regelformat für Coding-Agents.

---

## Lizenz und Veröffentlichung

- **Lizenz:** MIT, siehe [LICENSE](LICENSE). Gratis auf GitHub; kein Verkauf, keine Paywall.
- **Englisch:** [README.en.md](README.en.md) für die internationale Reichweite; die Prompt-Sprache ist noch Deutsch.
- **Zip ohne macOS-Müll:**

```bash
zip -r prompt-generator.zip . -x '__MACOSX/*' -x '.DS_Store' -x '*/__pycache__/*'
```
