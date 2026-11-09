# Gate Catalogue: Kotlin / Android

> Copy the gates the project has to `docs/gates/kotlin-android.md`; delete the rest. Replace every `<...>`; use only tasks verified in the Gradle build (`./gradlew tasks`).

| Gate | Command shape | Expected |
| --- | --- | --- |
| `build` | `./gradlew assembleDebug` | exit 0, `BUILD SUCCESSFUL` |
| `tests` | `./gradlew testDebugUnitTest` [VERIFY: variant name] | exit 0, all unit tests pass |
| `lint` | `./gradlew lintDebug` | exit 0, no errors in the lint report |
| `format` | `./gradlew ktlintCheck` or `./gradlew detekt` [VERIFY: plugin in the build] | exit 0 |
| `ui-tests` | `./gradlew connectedDebugAndroidTest` | exit 0; exclusive (`emulator`) |
| `bundle` | `./gradlew bundleRelease` (CI only, signed with the upload key) | exit 0, AAB written |

- Use the Gradle wrapper of the repo (`./gradlew`), never a global `gradle`.
- The release bundle is signed in CI from secrets; agents never hold the upload key.

## Pitfalls

- A running emulator is shared: instrumented tests are `exclusive: ["emulator"]`.
- Gradle daemons and caches survive between runs; a flaky build after a dependency change wants `--refresh-dependencies` once, not a code change.
- `local.properties`, keystores and `google-services.json` with secrets belong in `.gitignore` and policy protected paths.
- `targetSdk` must meet the current Play requirement; check it before the release station.
