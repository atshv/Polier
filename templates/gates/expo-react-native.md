# Gate Catalogue: Expo / React Native

> Copy the gates the project has to `docs/gates/expo-react-native.md`; delete the rest. Replace every `<...>`; use only scripts verified in `package.json`.

| Gate | Command shape | Expected |
| --- | --- | --- |
| `types` | `npx tsc --noEmit` | exit 0, no errors |
| `lint` | `npx expo lint` or `npm run lint` [VERIFY: from package.json] | exit 0 |
| `tests` | `npx jest` or `npm test` [VERIFY: from package.json] | exit 0, all tests pass |
| `doctor` | `npx expo-doctor` | exit 0, no failed checks |
| `e2e` | `maestro test <flows/>` [VERIFY: Maestro or Detox in the project] | exit 0; exclusive (`simulator`) |
| `build` | `eas build --platform <ios|android> --profile <preview>` (CI only) [VERIFY: eas.json profiles] | exit 0, build URL |

- `EXPO_PUBLIC_*` variables end up in the app bundle: never put a secret in one.
- Native folders (`ios/`, `android/`) are generated with prebuild unless the project commits them; the ADR says which.

## Pitfalls

- Version drift between Expo SDK and libraries: `npx expo install <pkg>` picks compatible versions; a plain `npm install` may not.
- Metro cache causes ghost errors: `npx expo start -c` once, not a code change.
- OTA updates (`eas update`) are a release: they go through the release station, not an agent session.
