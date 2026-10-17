# <Projektname>

Fachliche Details: siehe `ARCHITECTURE.md`. Fortschritt: siehe `STATUS.md`. Struktur: siehe `docs/module-map.md`.

> **Regel:** Nur Regeln, die für jede Aufgabe gelten. Was die KI ohne die Zeile richtig machen würde, wird gestrichen. Keine Architektur, kein Fortschritt, keine langen Erklärungen.

## Befehle

- **Starten:** `<...>`
- **Build:** `<...>`
- **Alle Tests:** `<...>`
- **Einzelner Test:** `<...>`
- **Lint/Typen:** `<...>`
- **Git-Status:** `git status --short`
- **Diff:** `git diff`
- **Letzte Commits:** `git log --oneline -5`

## Abweichungen vom Standard

- <nur Regeln, die vom Üblichen abweichen>
- <bekannte Stolperfallen der Umgebung, nötige Umgebungsvariablen>

## Regeln

- Arbeite nur an der Aufgabe, die im Auftrag steht.
- Lies zuerst `ARCHITECTURE.md`, `AGENTS.md`, `STATUS.md`, `docs/module-map.md` und deinen Task-Brief.
- Bei Unklarheit: `open_questions` im Ergebnis, nicht raten.
- Belege Erfolg mit der Ausgabe jedes Gates.
- Ändere keine Dateien außerhalb deines Scopes.
- Ein Commit pro Task: Task-ID + Titel, z. B. `M03: Add, List und Search`. Kein Push, kein Remote, keine PRs ohne Freigabe.
- Schichten nicht vermischen: UI ruft Logik auf, Logik ruft Daten – nie umgekehrt.
- Bibliotheken/APIs/Versionen nur aus Doku oder Manifest verwenden; keine erfundenen Pakete.
- Secrets: keine Keys/Tokens im Repo oder Bundle. Mobile/Web sind öffentlich (Expo: `EXPO_PUBLIC_*`); Secrets nur serverseitig.

## Verboten

- Neue Abhängigkeiten ohne Freigabe.
- Bestehende Tests ändern oder löschen ohne Freigabe.
- Platzhalter oder TODOs als fertig melden.
- Architektur-Invarianten ändern (nur über ADR + Freigabe).
- Secrets, Tokens oder Caches committen.
