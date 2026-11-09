<p align="center">
  <img src="docs/images/line.de.svg" alt="Polier – die Fertigungslinie: Idee, Konzept, Design, Architektur, Plan, Bau, Prüfung, Release, Betrieb" width="100%">
</p>

<p align="center">
  <a href="https://github.com/atshv/Polier/releases"><img alt="release" src="https://img.shields.io/github/v/release/atshv/Polier?style=flat-square&color=6366f1"></a>
  <a href="https://github.com/atshv/Polier/actions/workflows/test.yml"><img alt="tests" src="https://img.shields.io/github/actions/workflow/status/atshv/Polier/test.yml?branch=main&style=flat-square&label=tests"></a>
  <img alt="license" src="https://img.shields.io/badge/license-MIT-34d399?style=flat-square">
  <img alt="python" src="https://img.shields.io/badge/python-3.9%2B-1f5f8b?style=flat-square">
  <img alt="dependencies" src="https://img.shields.io/badge/dependencies-none-34d399?style=flat-square">
</p>

<p align="center"><a href="README.md">English</a> · <b>Deutsch</b></p>

**Polier ist eine KI-Softwarefabrik.** Du beschreibst das Produkt, Polier führt es durch neun Stationen – Idee, Konzept, Design, Architektur, Plan, Bau, Prüfung, Release, Betrieb. Egal ob Website, iOS- oder Android-App, Desktop-App, CLI oder Backend-Service. An jeder Station weiss Polier, was dein Produkt braucht (Registrierung, Zahlungen, Offline-Modus, Datenschutzerklärung, App-Store-Datenschutzangaben, geschlossener Play-Test, Signierung, Monitoring …), verlangt Nachweise und schliesst die Station erst mit deiner Freigabe.

Danach bauen Agenten Aufgabe für Aufgabe innerhalb des Plans. Schreibzugriffe ausserhalb der Aufgabe werden blockiert, nur aufgezeichnete Testläufe zählen als Nachweis, jeder Versuch, jedes Review und jede Freigabe wird protokolliert. Funktioniert mit **Claude Code**, jedem **MCP**-Client und **DeepSeek Harness**. Nur Python-Standardbibliothek, alles bleibt als Dateien in deinem Repository.

## Schnellstart

```bash
git clone https://github.com/atshv/Polier.git && cd Polier
./install.sh claude          # Claude Code; für DeepSeek Harness: dsh plugin --profile <name> add .
```

In einem leeren Ordner eine Session öffnen und schreiben: *„Baue mit Polier eine neue App: …“*. Polier stellt seine Fragen, startet die Linie und führt dich durch die Stationen.

```bash
python3 tools/factory.py --root <projekt> status    # wo das Projekt steht
python3 tools/factory.py --root <projekt> next      # was die aktuelle Station noch braucht
```

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

- Ein Punkt ist erst erledigt mit Nachweis, also einer Datei im Projekt (`docs/concept.md#user-stories`) oder verknüpften Aufgaben, die fertig sind.
- `must`-Punkte sind erledigt oder *nicht zutreffend* mit Begründung, nur `should`-Punkte dürfen verschoben werden.
- Eine Aufgabe ist erst fertig mit bestandenem Review, aufgezeichneten Gate-Läufen und einer Übergabe.
- Eine Station schliesst erst, wenn alle Punkte erledigt sind, alle früheren Stationen geschlossen sind und du freigibst (`factory.py advance --by <du>`).

## Was drin ist

| | |
|---|---|
| **Fabrik** | `factory/catalog.json`, `tools/factory.py`, Vorlagen für Konzept, Abläufe, Rechtstexte, Store-Einträge und Runbook |
| **Leitplanken** | Write Guard, Prüfpunkte, Übernahmen, Freigaben, Token-Budgets – in `core/`, für alle Zugänge gleich |
| **Gates** | Kataloge für Node/TS, Python, Swift/iOS, Kotlin/Android, Expo, Flutter, C++, WASM, Postgres, Playwright, Last, Visual Diff |
| **Anbindungen** | Claude-Code-Hooks, DeepSeek-Harness-Plugin (`pl_factory`, `/pl factory`), MCP-Server (`tools/mcp.py`) |
| **Beispiele** | [`factory-app`](examples/factory-app) (Linie in Arbeit), [`minimal-cli`](examples/minimal-cli), [`monorepo-mini`](examples/monorepo-mini) |

## Mehr erfahren

- **Ablauf** – [`prompt/generator.md`](prompt/generator.md) · **Dein Teil** – [`guide/cheatsheet.md`](guide/cheatsheet.md) (Englisch)
- **KI-Client verbinden** – `claude mcp add polier -- python3 tools/mcp.py --root <projekt>`
- **Grenzen** – Polier ist keine Sandbox, siehe [was der Write Guard nicht abdeckt](docs/guard-limits.md) (Englisch)
- **Änderungen** – [`CHANGELOG.md`](CHANGELOG.md) · [Releases](https://github.com/atshv/Polier/releases)

Tests: `npm install && npm test`. Lizenz: [MIT](LICENSE).
