# Qualitätsrubrik und Lint

**Zweck:** Ein Prompt-Paket ist gut, wenn ein fremder Agent damit ohne Rückfrage arbeiten kann. Diese Rubrik prüft das – unabhängig vom Autor, ohne Selbst-Score.

---

## 0. Begriffe

- **Gate:** ein deterministischer Befehl mit erwarteter Ausgabe. Bestanden ist es nur, wenn Exit-Code und sichtbare Ausgabe stimmen; die Ausgabe wird als Evidenz gespeichert.
- **Task bestanden:** alle Gates grün, jede Akzeptanz einem Gate/Test zugeordnet, Reviewer-`verdict: pass` ohne Blocker, vom Lead/Menschen gemergt. Ein Worker-`submitted` zählt nicht.
- **Kaltstart-Test:** ein fremder Agent bekommt nur `ARCHITECTURE.md`, `AGENTS.md`, `STATUS.md` und den ersten Task-Brief und muss daraus ohne blockierende Rückfrage einen Plan bauen können. Blockierend = ohne diese Antwort ist kein Plan möglich.

---

## 1. Die 12 Kriterien

Jedes Kriterium wird mit **0 oder 1** bewertet. Blocker sind mit **B** markiert: Ein Blocker verhindert die Freigabe, auch wenn die Summe passt.

| # | Kriterium | Prüffrage | B |
|---|---|---|---|
| 1 | Zweck, Nutzer, Nutzen | Steht in 2–3 Sätzen, was das System für wen tut und woran Erfolg gemessen wird? | B |
| 2 | Umfang und Nicht-Ziele | Gibt es eine Liste, was dazugehört, und eine, was ausdrücklich nicht dazugehört? | – |
| 3 | Testbare Akzeptanz | Ist jede Anforderung als WENN–DANN formuliert und hat mindestens ein Gate oder einen Test? | B |
| 4 | Kontext-Pack | Steht im Brief genau, welche Dateien/Abschnitte gelesen werden – und welche nicht? Gibt es ein Token-Budget? | – |
| 5 | Exakte Vorgaben | Sind Felder, Typen, Grenzen, Pfade und Texte konkret statt adjektivisch? | – |
| 6 | Sonderfälle | Sind leere Eingabe, Duplikat, ungültiger Wert, fehlende Verbindung, Doppelklick o. Ä. abgedeckt? | – |
| 7 | Gates | Gibt es Befehle mit erwarteter Ausgabe für Build, Tests und E2E/Akzeptanz? | B |
| 8 | Architektur-Spine | Ist `ARCHITECTURE.md` ≤ 800 Wörter, mit 3–7 Invarianten (AD-IDs), Nicht-Zielen, Modulstruktur und Verweisen? | – |
| 9 | Rollen und Scopes | Passt die Topologie zum Profil? Hat jede Aufgabe genau einen Schreiber und einen disjunkten Scope? | – |
| 10 | Review-Unabhängigkeit | Ist definiert, wer prüft, was der Reviewer sieht, und wie eskaliert wird? | B |
| 11 | Größenbudgets | Sind Architektur, Briefs, STATUS und Docs innerhalb der Budgets; keine Duplikate? | – |
| 12 | Keine Erfindungen | Sind Bibliotheken, APIs, Paketnamen, Versionen und Pfade aus Doku/Manifest/Repo belegt oder als `[UNVERIFIED]` mit Quelle markiert? | – |

**Bestanden:** ≥ 11/12 **und** kein Blocker. Unter 11 oder ein Blocker: nachbessern und erneut prüfen. Maximal zwei Runden, dann entscheidet der Mensch.

---

## 2. Lint: prüfbare Punkte

`tools/check.py` prüft die harten, maschinellen Punkte (Board, Budgets, Links, Platzhalter, Pflichtdateien). Die übrigen Punkte brauchen Review-Urteil; sie sind hier trotzdem aufgeführt.

Diese Punkte kann ein Skript oder ein sorgfältiger Reviewer ohne Urteil prüfen:

- [ ] `ARCHITECTURE.md` vorhanden, ≤ 800 Wörter, Abschnitte 1–8 vorhanden.
- [ ] `docs/module-map.md` vorhanden; Schichten (UI/Logik/Daten), Ordner und Importrichtung definiert.
- [ ] `AGENTS.md` vorhanden, ≤ 400 Wörter, keine Architektur, kein Fortschritt; enthält Befehle, Scope- und Commit-Regel.
- [ ] `STATUS.md` vorhanden und aus `board.json` ableitbar.
- [ ] `board.json` ist valides JSON, entspricht `templates/board.schema.json`.
- [ ] Jede Task hat: `id`, `title`, `goal`, `status`, `depends_on`, `complexity`, `stage`, `scope_write`, `acceptance`, `gates`.
- [ ] Keine Task mit `complexity ≥ 7`.
- [ ] Keine Zyklen in `depends_on`.
- [ ] Keine zwei parallel laufenden Tasks mit überlappendem `scope_write`.
- [ ] Jede Akzeptanz `A1..An` hat mindestens ein Gate oder einen benannten Test.
- [ ] Jede Task hat einen Kontext-Pack mit „Lies genau“ und „Lies nicht“.
- [ ] Jede Task hat einen Stop-/Budget-Abschnitt.
- [ ] Keine `TODO`, `TBD`, `Platzhalter`, `[UNVERIFIED]` in kritischen Pfaden.
- [ ] Alle internen Links und Dateipfade existieren.
- [ ] Keine Datei, die „alles“ enthält (Monolith).
- [ ] Keine erfundenen Bibliotheksversionen ohne Quelle.
- [ ] Keine Secrets, Tokens oder echten Zugangsdaten in Dateien.
- [ ] Secrets-Policy beachtet: keine Secrets in Dateien/Bundles; Mobile/Web-Bundles sind öffentlich.
- [ ] Bibliotheken/APIs/Versionen sind aus Doku oder Manifest belegt, nicht erfunden.
- [ ] Git-Repo initialisiert, `.gitignore` vorhanden, `base_branch` gesetzt, erster Commit vorhanden.
- [ ] Keine Task mischt UI und Datenzugriff; jede Task nennt ihre Schicht/Modulgruppe.

---

## 3. Critic-Prompt (ein Subagent, nach dem Kaltstart)

Der Critic ist **derselbe** Subagent wie im Kaltstart. Er bekommt zuerst nur die vier Kaltstart-Dateien; erst danach Board, Briefs und diesen Prompt. Kein zweiter Subagent.

```text
Du bist unabhängiger Kritiker. Du hast dieses Projekt nicht geschrieben und
sollst es nicht umschreiben. Du prüfst nur.

Lies ausschließlich:
- ARCHITECTURE.md
- AGENTS.md
- STATUS.md
- board.json
- tasks/M01..Mxx.md (die vorhandenen Briefs)
- docs/quality.md, falls vorhanden

Bewerte mit der 12-Punkte-Rubrik (rubric.md). Achte besonders auf:
1. Architektur > 800 Wörter oder Details, die nicht hineingehören
2. Akzeptanz ohne Gate/Test
3. Tasks ohne Scope, mit Zyklen oder überlappenden Schreibpfaden
4. fehlende Kontext-Packs oder Budgets
5. Rollen/Rechte, die nicht zum Profil passen
6. erfundene Versionen, Pfade oder APIs
7. Widersprüche zwischen Architektur, Briefs und Board
8. fehlendes Git-Repo, fehlende `.gitignore` oder fehlender erster Commit
9. vermischte Schichten (UI greift direkt auf Daten zu, Logik importiert UI)

Ausgabe: Tabelle | # | Kriterium | 0/1 | Blocker | Finding | Datei | Fix.
Danach: Gesamtsumme, Blocker-Liste, drei wichtigste Verbesserungen.
Keine Rewrites. Keinen Score ohne Findings. Keine Meinung ohne Datei/Zeile.
```

---

## 4. Kaltstart-Test

Der wichtigste Test: Ein fremder Agent bekommt **nur** die Dateien, die ein neuer Mitarbeiter auch bekommen würde.

```text
Du bist ein neuer Agent auf diesem Projekt. Du bekommst nur:
- ARCHITECTURE.md
- AGENTS.md
- STATUS.md
- tasks/M01.md

Beantworte ohne Rückfrage:
1. Was ist das Ziel des Projekts in einem Satz?
2. Was ist der Scope von M01, und was ist ausdrücklich nicht drin?
3. Welche Dateien würdest du ändern, und welche nicht?
4. Welche Befehle würdest du ausführen, und was erwartest du?
5. Welche Informationen fehlen dir, um einen Plan zu schreiben?
6. Welche Datei müsstest du zusätzlich lesen?
7. In welche Schicht (UI/Logik/Daten) gehört die Änderung, und welche Dateien darfst du dafür anfassen?

Antworte knapp. Erfinde nichts.
```

**Auswertung:** Jede Rückfrage ist ein Befund. Ergänze den Kontext-Pack oder die Architektur – aber nur, wenn es eine echte Lücke ist. Ein Detail, das nur ein Modul braucht, gehört in den Brief, nicht in die Architektur.

**Bestanden:** keine blockierende Rückfrage; der Agent nennt die richtigen Dateien, die richtige Schicht und die Gates und kann planen, ohne eine neue Entscheidung zu treffen. **Nicht bestanden:** eine blockierende Rückfrage oder eine falsche Datei/Schicht – Kontext korrigieren und erneut testen.

---

## 5. Anti-Gaming

- Der Autor bewertet nicht seine eigene Arbeit.
- Der Critic sieht keine Denkspur, keine Selbstbewertung, keine Chat-Historie – nur Artefakte.
- „Sieht gut aus“ ist kein Finding. Jedes Finding braucht Datei, Kriterium und Evidenz.
- Ein Score ohne Findings ist wertlos. Zähle die behobenen Blocker, nicht den Score.
- Wenn der Critic nie etwas findet, ist die Rubrik zu weich oder der Kontext zu klein. Rubrik schärfen, nicht loben.

---

## 6. Wann du aufhörst

- ≥ 11/12 und kein Blocker: freigeben.
- Ein Blocker: nachbessern, erneut prüfen.
- Zwei Runden ohne Fortschritt: Mensch fragen, nicht weiter würfeln.
- Widersprüchliche Anforderungen: stoppen, Entscheidung verlangen.
