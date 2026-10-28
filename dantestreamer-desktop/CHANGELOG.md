# dantestreamer-desktop: latest changes

Newest first.

## 2026-10-28 (6)

- Virgil ships inside both apps: Install Virgil on the start page installs
  it with one permission prompt and connects. No separate download.
  Windows runs Virgil 0.8.1's official installer silently, checked against
  its SHA-256 in CI. macOS builds Virgil from source at a pinned commit and
  signs it with the app's Developer ID; the app runs the package with
  `/usr/sbin/installer` after the password prompt.
- Virgil Control on macOS is signed with the audio-input entitlement, so
  audio interface inputs work under the hardened runtime.
- CI prints which Apple secrets it can see (set or empty) in the notarize
  step.

## 2026-10-28 (5)

- Start page with the two setups. A: this PC or Mac plays to the Dante
  speakers through Virgil, with no other box; Download Virgil and Use this
  computer buttons, and the steps for Desktop audio and Dante Controller.
  B: a DanteStreamer box on the network.
- On first start the app checks for Virgil on this computer and adds it by
  itself when it runs.
- Find on network: lists DanteStreamer boxes by their AirPlay receiver
  (Shairport Sync), skipping Apple TVs and HomePods, and fills in the
  address.
- Setup guide button and "How do I connect?" link open the new guide in the
  README: step by step for both setups on Windows and macOS, and a table of
  every connection message with what to do.
- Error messages name the fix: install or start Virgil, set
  `REMOTE_PASSWORD` on the box, or correct the password.

## 2026-10-28 (4)

- When a host refuses the port, both apps say what to do: use `localhost`
  on the DanteStreamer computer, or turn on remote access or an SSH tunnel
  from another one. Before, Windows showed only the socket error.
- `tools/mock_virgil.py`: a fake Virgil API (status, start, stop, restart,
  optional password) for trying the apps without a Dante host.

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
