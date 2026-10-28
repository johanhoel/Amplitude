# dantestreamer-desktop: latest changes

Newest first.

## 2026-10-28 (3)

- Both apps built in CI for the first time (run 40771546912). The release
  job failed because its token could not write releases; it now has
  `contents: write` and uses `action-gh-release@v2`.
- Edit a saved host (name, address, port, password) on both apps.
- Open web panel button: opens Virgil's panel in the browser for settings,
  routing and diagnostics.
- Passwords no longer saved in plain text: macOS uses the login keychain,
  Windows encrypts them with DPAPI. Old Windows files still load.
- macOS: universal binary (Apple silicon and Intel), notarized and stapled
  when the `APPLE_ID` and `APPLE_APP_PASSWORD` secrets exist (or an App
  Store Connect API key). Version in `Info.plist` follows the CI run number.
- CI shows Swift compiler errors as annotations on the run page.

## 2026-10-28 (2)

- Windows build fixed. It failed on XAML `StringFormat` escapes (`{{0}}`
  is not valid XAML; it is now `{}{0}`) and then on missing `System.IO` and
  `System.Collections.Generic` usings. `App.xaml` loaded
  `Themes/Generic.xaml`, which does not exist, so the app would also have
  crashed at start.
- Both apps now read the real `/api/status` JSON. Virgil nests the fields
  (`device.name`, `clock.state`, `meters.tx`); the old Windows model
  expected flat names like `device_name` and would have shown nothing.
- Windows: the Add form works, selecting a host connects to it, and Start,
  Stop and Restart audio buttons call the API. Meters show each channel in
  dBFS. The release is one 72 MB exe instead of a folder of DLLs.
- macOS: the app was a placeholder that printed "Full UI coming soon". It
  is now a SwiftUI app with the same features as the Windows app. The
  bundle allows plain HTTP to reach Virgil and is signed with the hardened
  runtime.
- Both apps send the remote password with HTTP Basic auth and explain 401,
  403 and 429 answers from Virgil.
- READMEs rewritten to match what the apps do. Removed claims of mDNS
  discovery, audio routing, WASAPI and CoreAudio playback, which were never
  built.
- Screenshots still missing: they need a Mac and a PC connected to a
  running host.

## 2026-10-28

- First version: a WPF app for Windows, a placeholder for macOS, and the
  `build-desktop.yml` workflow that builds both and publishes a
  prerelease. The Windows build did not compile, and the macOS app had no
  window.
