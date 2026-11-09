<p align="center">
  <img src="docs/images/line.de.svg" alt="Polier – die Fertigungslinie: Idee, Konzept, Design, Architektur, Plan, Bau, Prüfung, Release, Betrieb" width="100%">
</p>

<p align="center">
  <a href="https://github.com/atshv/Polier/releases"><img alt="release" src="https://img.shields.io/github/v/release/atshv/Polier?style=flat-square&color=6366f1"></a>
  <a href="https://github.com/atshv/Polier/actions/workflows/test.yml"><img alt="tests" src="https://img.shields.io/github/actions/workflow/status/atshv/Polier/test.yml?branch=main&style=flat-square&label=tests"></a>
  <img alt="license" src="https://img.shields.io/badge/license-MIT-34d399?style=flat-square">
  <img alt="DeepSeek Harness" src="https://img.shields.io/badge/DeepSeek%20Harness-0.2.2-1f5f8b?style=flat-square">
  <img alt="dependencies" src="https://img.shields.io/badge/runtime%20deps-none-34d399?style=flat-square">
</p>

<p align="center"><a href="README.md">English</a> · <b>Deutsch</b></p>

**Polier ist eine KI-Softwarefabrik für DeepSeek Harness.** Du beschreibst das Produkt, Polier führt es durch neun Stationen – Idee, Konzept, Design, Architektur, Plan, Bau, Prüfung, Release, Betrieb. Egal ob Website, iOS- oder Android-App, Desktop-App, CLI oder Backend-Service. An jeder Station weiss Polier, was dein Produkt braucht (Registrierung, Zahlungen, Offline-Modus, Datenschutzerklärung, App-Store-Datenschutzangaben, geschlossener Play-Test, Signierung, Monitoring …), verlangt Nachweise und schliesst die Station erst mit deiner Freigabe.

## Installieren

```bash
dsh plugin --profile web add github:atshv/polier
```

DSH neu starten (oder *dsh-polier* unter **Plugins** einschalten). Python 3.9+ muss vorhanden sein, sonst wird nichts installiert.

## Keine Befehle

In einem leeren Ordner eine Session öffnen und sagen, was du willst, z. B. *„Baue mit Polier eine App, die …“*. Ab dann redest du einfach.

| Du sagst | Was passiert |
|---|---|
| „Was fehlt noch?“ | Der Agent sieht den Live-Block `<polier>` schon – Station, offene Punkte, laufende Aufgabe, nächster Schritt |
| „Schliess die Station.“ | Du bekommst eine DSH-Freigabeabfrage, nur deine Antwort schliesst sie |
| „Übernimm Aufgabe M03.“ | Die Session bindet die Aufgabe, reserviert sie und darf nur noch in ihrem Bereich schreiben |
| „Wir brauchen die Bibliothek httpx.“ | Eine Freigabeabfrage, die Antwort landet in `reviews/approvals/` |
| „Plane die nächste Etappe.“ | Die Session fragt nach dem Lead-Modus – wieder eine Abfrage, die du beantwortest |

Ein „ja“ im Chat ändert nichts. Entscheidungen sind Freigabeabfragen, Einträge schreiben die Tools, `STATUS.md` und `docs/factory.md` erneuern sich selbst.

## Die Linie

| # | Station | Ergebnis | Beispiele, was geprüft wird |
|---|---|---|---|
| 1 | Idee | `project-input.md`, `factory.json` | Problem, Nutzer, Erfolgssignal, Abgrenzung, Plattformen |
| 2 | Konzept | `docs/concept.md` | MVP-Funktionen, User Stories, Abnahmeszenarien, Kosten, Rechtsrahmen |
| 3 | Design | `docs/ux-flows.md`, `docs/design-rules.md` | Abläufe, Screens, Tokens, Zustände, Barrierefreiheit, Plattform-Richtlinien |
| 4 | Architektur | `ARCHITECTURE.md`, ADRs | Stack mit Quellen, Schichten, Datenmodell, API, Secrets, Umgebungen |
| 5 | Plan | `board.json`, `policy.json`, Briefs | jeder Bau- und Prüfpunkt hat eine Aufgabe, Gates, Kaltstart-Test |
| 6 | Bau | Code, `runs/`, `reviews/` | Login, Daten, Sicherheit, Zahlungen, Push, Berechtigungen, Privacy Manifest |
| 7 | Prüfung | Gate-Nachweise | E2E, Geräte-/Browser-Matrix, Barrierefreiheit, OWASP/MASVS, Beta |
| 8 | Release | `docs/legal.md`, `docs/store/*` | CI ab Tags, Rechtstexte, Store-Einträge, Signierung, Notarisierung |
| 9 | Betrieb | `docs/runbook.md` | Fehler, Erreichbarkeit, Backups, Support, Updates, Store-Pflege |

Die vollständige Checkliste – 175 Punkte, jeweils mit den Plattformen und Eigenschaften, für die sie gelten – steht in [`factory/CATALOG.md`](factory/CATALOG.md) (Englisch). Eine Web-App mit Konten bekommt rund 100 davon, ein CLI rund 50.

## Nachweise statt Versprechen

- Ein Punkt ist erst erledigt mit Nachweis, also einer Datei im Projekt (`docs/concept.md#user-stories`) oder verknüpften Aufgaben, die fertig sind. `must`-Punkte werden nie verschoben.
- Eine Aufgabe ist erst fertig mit aufgezeichneten Gate-Läufen, bestandenem unabhängigem Review und einer Übergabe.
- Ein Worker schreibt nur in seinem Aufgabenbereich, geschützte Pfade, Abhängigkeiten und verbotene Befehle folgen `policy.json`.
- DSH-Goals, Subagents und Ralph-Schleifen passen dazu, ihre Berichte sind aber Behauptungen – entscheiden tun Gates und Prüfpunkte.

## Was drin ist

| | |
|---|---|
| [`plugin/`](plugin) | das DSH-Plugin – Live-Kontext, Leitfaden, Write Guard, Stop-Check, die `pl_*`-Tools |
| [`factory/`](factory) | der Katalog der Stationen und Punkte |
| [`core/`](core), [`tools/`](tools) | die Regeln und die Python-Tools darunter (auch ohne Oberfläche nutzbar) |
| [`prompt/`](prompt), [`templates/`](templates) | der Ablauf, die Bewertung und alle Dokumentvorlagen |

## Mehr erfahren

- **Ablauf** – [`prompt/generator.md`](prompt/generator.md) · **In DSH** – [`prompt/dsh.md`](prompt/dsh.md) · **Dein Teil** – [`guide/cheatsheet.md`](guide/cheatsheet.md) (Englisch)
- **Grenzen** – Polier ist keine Sandbox, siehe [was der Guard nicht abdeckt](docs/guard-limits.md) (Englisch)
- **Tools** – [`docs/tools.md`](docs/tools.md) · **Aufbau** – [`docs/architecture.md`](docs/architecture.md) (Englisch)
- **Mitmachen** – [`CONTRIBUTING.md`](CONTRIBUTING.md), [`AGENTS.md`](AGENTS.md) · **Sicherheit** – [`SECURITY.md`](SECURITY.md) · **Änderungen** – [`CHANGELOG.md`](CHANGELOG.md)

Tests: `npm install && npm test`. Lizenz: [MIT](LICENSE).
