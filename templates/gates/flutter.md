# Gate Catalogue: Flutter

> Copy the gates the project has to `docs/gates/flutter.md`; delete the rest. Replace every `<...>`; use only commands verified in `pubspec.yaml` or the docs.

| Gate | Command shape | Expected |
| --- | --- | --- |
| `analyze` | `flutter analyze` | exit 0, "No issues found!" |
| `format` | `dart format --output=none --set-exit-if-changed .` | exit 0 |
| `tests` | `flutter test` | exit 0, all tests pass |
| `integration` | `flutter test integration_test` [VERIFY: folder exists] | exit 0; exclusive (`simulator`) |
| `build` | `flutter build <apk|appbundle|ipa|web>` (release builds in CI only) | exit 0 |

- Pin the Flutter version (`.fvmrc` or the CI setup); `flutter --version` goes into `docs/versions.md`.

## Pitfalls

- Generated files (`*.g.dart`) need `dart run build_runner build`; the gate fails if they are stale — regenerate, never hand-edit.
- Platform folders still need the iOS/Android release items (signing, privacy manifest, permissions).
