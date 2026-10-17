# ADR-0002: Tags erst in Etappe 2

**Datum:** 17.10.2026 · **Status:** akzeptiert · **Ersetzt:** –

## Kontext

Tags sind für den täglichen Nutzen wichtig, aber sie berühren Service, Store und CLI. M03 (Add/List/Search) ist der MVP-Kern. Würden Tags in M03 wandern, wächst der Task über Komplexität 5 und die Review-Fläche steigt.

## Entscheidung

M03 bleibt bei Add/List/Search ohne Tags. Tags kommen als M04 in Etappe 2, nachdem der MVP-Kern grün ist.

## Konsequenzen

- **Positiv:** M03 bleibt klein und testbar; der MVP ist früher nutzbar.
- **Negativ:** `bm add --tag` funktioniert erst in Etappe 2.
- **Bindet:** M03, M04
- **Verhindert:** einen überladenen ersten Task.

## Alternativen

- **Tags in M03** — verworfen: Task zu groß, vermischte Akzeptanz.
- **Tags ganz weglassen** — verworfen: Filter sind ein Kernnutzen.
