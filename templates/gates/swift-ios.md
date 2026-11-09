# Gate Catalogue: Swift / iOS

> Copy the gates the project has to `docs/gates/swift-ios.md`; delete the rest. Replace every `<...>`; use only flags verified in the Xcode project, `Package.swift` or the docs.

| Gate | Command shape | Expected |
| --- | --- | --- |
| `build` | `xcodebuild build -scheme <Scheme> -destination 'platform=iOS Simulator,name=<Device>'` [VERIFY: scheme and simulator name] | exit 0, `** BUILD SUCCEEDED **` |
| `tests` | `xcodebuild test -scheme <Scheme> -destination 'platform=iOS Simulator,name=<Device>'` | exit 0, `** TEST SUCCEEDED **` |
| `ui-tests` | `xcodebuild test -scheme <Scheme> -only-testing:<UITestTarget> -destination '…'` | exit 0; exclusive (`simulator`) |
| `lint` | `swiftlint --strict` [VERIFY: SwiftLint is in the project] | exit 0, no violations |
| `format` | `swift format lint --recursive <Sources>` [VERIFY: swift-format version] | exit 0 |
| `spm-tests` | `swift test` (Swift packages only) | exit 0, all tests pass |

- List simulators with `xcrun simctl list devices available`; pin the device name in the gate, never "latest".
- Archive and upload run in CI (Xcode Cloud or fastlane) from a tag, never from an agent session.

## Pitfalls

- A booted simulator is a shared resource: UI tests are `exclusive: ["simulator"]`.
- Code signing in tests: use the simulator destination; device builds need a signing identity CI provides.
- `DerivedData` is large and machine-local; never commit it, clean it when a build fails for no code reason.
- Privacy manifest (`PrivacyInfo.xcprivacy`) and `Info.plist` usage strings are part of the build item, not an afterthought.
