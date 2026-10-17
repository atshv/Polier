# Architektur: <Projektname>

**Stand:** <Datum> · **Status:** verbindlich · **Besitzer:** <Rolle>

> **Größenbudget:** 400–600 Wörter, harte Obergrenze 800. Wenn du mehr brauchst: auslagern und verlinken, nicht anhängen.

## 1. Zweck und Nicht-Ziele

<2–3 Sätze: Was kann das System, für wen, welcher Nutzen?>

**Nicht-Ziele:** <was bewusst nicht dazugehört>

## 2. Harte Randbedingungen

- **Plattform/Version:** <...>
- **Daten und Netz:** <offline, keine API, ...>
- **Recht/Regeln:** <ToS, Datenschutz, Lizenzen>
- **Secrets/Backend:** <kein Backend; keine Secrets im Bundle | Backend, Secrets serverseitig>
- **Zeit/Budget:** <...>
- **Sprache:** UI <Deutsch>, Code/Prompts <Englisch>

## 3. Systemform und Modulstruktur

<Schichten und erlaubte Abhängigkeitsrichtung. Details: `docs/module-map.md`>

| Schicht | Ordner | Darf | Darf nicht |
| --- | --- | --- | --- |
| UI/Screens | `<...>` | Logik aufrufen | Daten/DB direkt |
| Logik | `<...>` | Data/Repository, eigene Domain-Typen | UI |
| Daten/Infrastruktur | `<...>` | Standardbibliothek/DB-Treiber, eigene Row-Typen | UI, Logik |

**Regel:** Abhängigkeiten zeigen nur nach unten: UI → Logik → Daten; keine Zyklen. Domain-Typen liegen in der Logik; Data importiert sie nicht.

## 4. Invarianten (AD-1 … AD-n)

> Nur Entscheidungen, die zwei unabhängig gebaute Module sonst inkompatibel treffen würden – nicht offensichtlich, echter Trade-off.

| ID | Regel | Bindet | Verhindert |
| --- | --- | --- | --- |
| AD-1 | <ein Satz> | <Module/Pfade> | <Fehlerklasse> |
| AD-2 | <...> | <...> | <...> |

## 5. Grenzen und Eigentum

| Bereich | Gehört zu | Schreiben | Lesen |
| --- | --- | --- | --- |
| <Pfad/Modul> | <Schicht/Rolle> | <wer> | <wer> |

## 6. Qualitätsgates

- **Build:** `<Befehl>` → <erwartet>
- **Tests:** `<Befehl>` → <erwartet>
- **Lint/Typen:** `<Befehl>` → <erwartet>
- **E2E/Akzeptanz:** <Szenario> → <sichtbares Ergebnis>
- **Review:** unabhängig, Diff + Kriterien + Gate-Ausgabe

## 7. Offen / bewusst nicht entschieden (Deferred)

- <Thema> — <wann entschieden wird>

## 8. Verweise

- Modulstruktur: `docs/module-map.md`
- Datenmodell: `docs/data-model.md`
- Verträge: `docs/contracts/<...>.md`
- Entscheidungen: `docs/adr/`
- Domänenwissen: `docs/domain/<...>.md`
- Betrieb: `docs/runbook.md`
