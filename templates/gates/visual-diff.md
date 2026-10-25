# Gate Catalogue: Visual diff

> Copy the gates the project has to `docs/gates/visual-diff.md`; delete the rest. Replace every `<...>`; the tool and tolerance come from the manifest.

| Gate | Command shape | Expected |
| --- | --- | --- |
| `visual` | `npm run test:visual` or `npx playwright test --project=visual` [VERIFY: from manifest/docs] | exit 0, 0 snapshot differences |
| `visual-update` | the project's snapshot-update command [VERIFY: from manifest/docs] | baselines updated — requires review, never a gate |

- Baselines are committed. Updating one needs a reviewer who saw the before and after images.
- Failure diffs go to `reviews/evidence/` together with the gate record.
- Run the `visual` gate on the same seeded data and viewport set as `e2e`; a different state produces a false diff.

## Pitfalls

- Screenshots depend on OS, fonts, device pixel ratio and browser version; pin all four or accept a documented tolerance.
- Animations, timestamps, random data and lazy images cause false diffs: disable animations, mask volatile regions, wait for load.
- Fix the viewport per snapshot (e.g. 1440×900 and 390×844); a resize changes every baseline.
- Never update baselines to make a gate pass; that hides the regression the gate exists for.
- Run on the same machine class as CI, or expect different pixels.
