# Cheatsheet: Der Generator in der Praxis

**Zweck:** Die Bedienungsanleitung für den Menschen. Der Generator entwirft und schreibt; du prüfst, gibst frei und startest die Tasks.

---

## In 30 Sekunden

1. Paket (`generator.md`, `templates/`, `rubric.md`, `tools/`) in einen Chat/Ordner legen, Eingabeblock in `generator.md` ausfüllen.
2. Interview beantworten (max. 10 Fragen pro Runde).
3. Architektur (1 Seite) und Task-DAG prüfen; bei S zusammen mit einem „ja“ freigeben.
4. Der Generator schreibt das Projekt-Gerüst in den Arbeitsordner der Session; ohne Dateisystem als Codeblöcke.
5. Pro Task: neue Session, Task-Brief einfügen, umsetzen lassen, Gates prüfen.
6. Review in neuer Session; erst danach `STATUS.md` und Commit.

**Merksatz:** Der Generator schreibt keine 25 Prompts. Er schreibt eine Architektur, ein Board und die nächsten 3–5 Briefs.

---

## Phasen und deine Rolle

| Phase | Der Generator | Du |
|---|---|---|
| 0 Modus + Interview | Tool-Check, max. 10 Fragen, Profilvorschlag am Ende | Profil im Vorschlag prüfen |
| B Recon | Repo-Fakten (Brownfield) | „stimmt / stimmt nicht“ |
| C Architektur | 1 Seite + Artefakt-Landkarte | bei M/L **Freigabe**; bei S warten |
| D Task-DAG | Board, Abhängigkeiten, Scopes | bei S **C+D zusammen freigeben**; bei M/L separat |
| E Agentenvertrag | nur M/L: Rollen, Handoffs | **Freigabe** (nur M/L) |
| F JIT-Briefs | 3–5 Briefs | ersten Brief lesen |
| G Scaffold | Dateien schreiben, Git-Repo anlegen, S-Dateiset | Dateibaum, Git, Struktur prüfen |
| H Lint + ein Subagent | `check.py`, Kaltstart, Rubrik | Findings entscheiden |
| I Übergabe | Start-/Review-/Eskalations-Prompts | loslegen |

### Nach dem Scaffold: die drei Fundamente prüfen

1. **Git-Repo**
   - `git status --short` → Repo vorhanden, keine fremden Änderungen.
   - `.gitignore` vorhanden (OS/Editor/Caches/Secrets).
   - Erster Commit `chore: scaffold` vorhanden.
   - Basisbranch ist `main` (oder der Branch aus `board.json`).
2. **Modulstruktur**
   - `docs/module-map.md` vorhanden.
   - Schichten getrennt: UI/Screens, Logik, Daten; Importrichtung nur nach unten: UI → Logik → Daten.
   - Keine UI-Datei, die direkt SQL oder die DB öffnet.
3. **AGENTS.md**
   - Befehle (Build, Test, Lint, Start) stehen drin.
   - Git-Regel und Commit-Format (Task-ID + Titel) stehen drin.
   - Schichtregel und Scope-Regel stehen drin.
   - Keine Architektur, kein Fortschritt.

---

## Wo die Prompts stehen

Die kanonischen Copy-Paste-Prompts stehen **einmal** in [`generator.md`](generator.md), Phase I:

- **Start:** Eingabeblock oben + Phase 0
- **Task starten:** Phase I → „Start (neue Session)“
- **Review:** Phase I → „Review (neue Session)“
- **Fix:** Phase I → „Fix“
- **Eskalation:** Phase I → „Eskalation“
- **Nächste Etappe:** Phase I → „Nächste Etappe“

Hier stehen bewusst keine Kopien, damit es nur eine Wahrheit gibt. Wenn du den Prompt anpassen willst, ändere ihn in `generator.md`.

## Nach jedem Task: deine Checkliste

- [ ] Alle Gates grün – **Ausgabe gesehen**, nicht nur „fertig“.
- [ ] Keine bestehenden Tests geändert oder gelöscht (oder Freigabe dokumentiert).
- [ ] Nur Dateien aus dem Scope geändert (Diff angeschaut).
- [ ] Jede Akzeptanz A1..An einzeln belegt.
- [ ] Review in neuer Session ohne offene Blocker.
- [ ] Keine Platzhalter, TODOs, `[UNVERIFIED]`.
- [ ] `STATUS.md` aus dem Board aktualisiert.
- [ ] Commit mit Task-ID + Titel im Text.
- [ ] Richtige Schicht geändert; keine UI-Datei greift direkt auf die DB zu.
- [ ] Nächster Task: Brief lesen, nicht „weiter wie bisher“.

---

## Rote Flaggen

| Symptom | Bedeutung | Reaktion |
|---|---|---|
| Kein Git-Repo / kein Diff | Rollback und Review blind | `git init`, `.gitignore`, erster Commit |
| Nebenstrang ohne Vertrag | geteilte Schnittstelle driftet | Vertrags-Task in `docs/contracts/` vorziehen (dann Pflicht); beide Stränge `depends_on` |
| UI importiert DB/Store direkt | Modulstruktur verletzt | `docs/module-map.md` anwenden, Task schneiden |
| Architektur > 800 Wörter | Zweites Pflichtenheft | Kürzen, auslagern |
| 20+ Task-Briefs vor dem ersten Code | Wasserfall | Stoppen, nur 3–5 |
| Generator gibt sich selbst 9/10 | Selbstbewertung | Critic + Kaltstart verlangen |
| Zwei Tasks schreiben dieselben Dateien | Scope-Konflikt | Scopes schneiden oder sequenziell |
| Agent setzt Task auf „done“ | Selbstbewertung | Nur Lead setzt done, nach Gates + Merge |
| Reviewer findet nie etwas | Review-Theater | Linse schärfen, Evidenzpflicht, Yield messen |
| Lead schreibt selbst Feature-Code | Flaschenhals | Lead plant/merged, Worker schreiben |
| Alle Docs im Kontext | Token-Blähung | Kontext-Pack, „Lies nicht“ |
| Keine Gates, nur „sieht gut aus“ | Keine Verifikation | Gates im Brief nachziehen |
| Agent erfindet Version/Paket/API | Halluzination | Nur Doku/Manifest, sonst `[UNVERIFIED]` + Quelle oder fragen |

---

## Wenn der Generator zu viel produziert

1. **Sofort stoppen.** Nicht „ist ja schon da“.
2. Fragen: Welche Datei verhindert eine konkrete Fehlerklasse? Alle anderen streichen.
3. Architektur auf eine Seite kürzen; Details in `docs/` verlinken.
4. Briefs auf die nächsten 3–5 reduzieren.
5. Board und STATUS auf eine Wahrheit bringen.
6. Erst weiter, wenn der Kaltstart-Test ohne Rückfrage besteht.

---

## Versionierung

- `templates/` ist kanonisch für Artefakte, `generator.md` für den Prozess, `rubric.md` für Qualität.
- Änderungen am Generator nur mit Grund: Welche Fehlerklasse hat gefehlt?
- Nach jeder Änderung: einen Golden Brief durchlaufen lassen und First-Pass-Green messen.
- Version im README erhöhen; alte Version behalten, bis die neue besser ist.
