# DanteStreamer Controller for macOS

SwiftUI app for macOS 12 or later. No dependencies outside the macOS SDK.

## Build and run

Needs Xcode 15 or later (Swift 5.9).

```bash
cd dantestreamer-desktop/macos
swift run -c release
```

`swift build -c release` puts the binary in
`.build/release/DanteStreamerController`. CI builds a universal binary
(`--arch arm64 --arch x86_64`), wraps it in `DanteStreamer.app` with an
`Info.plist`, signs it and notarizes it.

The `Info.plist` must allow plain HTTP (`NSAllowsArbitraryLoads`), because
Virgil's API has no HTTPS. Without it, macOS blocks every request.

## Files

- `Sources/DanteStreamerApp.swift`: app entry point and window.
- `Sources/ConnectionManager.swift`: saved hosts, polling `/api/status` once
  a second, start/stop/restart, HTTP Basic auth for the remote password.
- `Sources/ContentView.swift`: sidebar, Status and Meters tabs, Add/Edit sheet.
- `Sources/Keychain.swift`: saves each host's remote password in the login
  keychain (service `com.dantestreamer.controller`).
- `Sources/Models.swift`: the `/api/status` JSON, matching `status_json()`
  in Virgil's `src/daemon/control.cpp`.
