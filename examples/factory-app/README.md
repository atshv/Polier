# Example: Fault Codes — a factory line in progress

A phone app for heat-pump technicians (iOS and Android from one codebase, offline, German and English), stopped in the **design** station.

- `project-input.md` — station 1 input; closed by the owner.
- `docs/concept.md`, `docs/quality.md` — station 2; closed.
- `docs/ux-flows.md` — station 3, half done; mockups deferred with a reason.
- `factory.json` — the line, written only by `tools/factory.py`; `docs/factory.md` is generated from it.

Try it from the package root:

```bash
python3 tools/factory.py --root examples/factory-app status
python3 tools/factory.py --root examples/factory-app next
python3 tools/factory.py --root examples/factory-app catalog --platforms ios,android --traits offline,i18n,cross_platform
```

There is no board yet: `ARCHITECTURE.md`, `board.json` and the briefs come in stations 4 and 5. For a planned project see `examples/minimal-cli/` and `examples/monorepo-mini/`.
