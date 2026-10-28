# DanteStreamer Desktop

Desktop apps for macOS and Windows that show the state of one or more
[DanteStreamer](../dantestreamer/) hosts. They read the Virgil control API on
port 8480, the same data the web panel shows.

What both apps do:

- Keep a list of DanteStreamer hosts (name, host, port, remote password)
  that you can add, edit and remove.
- Show the device, engine state, network address, clock state and leader,
  sample rate, channels, dropouts in the last hour and the apps playing.
- Show live TX and RX meters per Dante channel on a -60 to 0 dBFS scale,
  with the channel names from Dante Controller.
- Start, stop or restart the audio engine (`/api/start`, `/api/stop`,
  `/api/restart`).
- Open Virgil's own web panel in the browser, for settings, routing and
  diagnostics.

Status refreshes once a second.

## Screenshots

Not taken yet. They need a Mac and a Windows PC connected to a running
DanteStreamer host. Save them as `docs/screenshots/macos-status.jpg`,
`macos-meters.jpg`, `windows-status.jpg` and `windows-meters.jpg`.

## Download

Each push to `main` that touches this folder builds both apps and publishes
a prerelease named `desktop-v1.0.<run>` on the
[Releases page](https://github.com/johanhoel/Amplitude/releases).

- macOS: `DanteStreamer-macos.zip`. Unzip and open `DanteStreamer.app`.
  Needs macOS 12 or later, Apple silicon or Intel. The app is signed with a
  Developer ID. It is notarized when the notarization secrets below exist;
  the release notes say which. Without notarization, right-click the app
  the first time and choose Open.
- Windows: `DanteStreamerController-windows.zip`. Unzip and run
  `DanteStreamerController.exe`. Needs 64-bit Windows 10 or later. The .NET
  runtime is inside the exe.

## Connecting to a host

Virgil answers only on `127.0.0.1:8480` unless remote access is on. Pick one:

1. SSH tunnel, no password. Run this, then add host `localhost`, port 8480:

   ```bash
   ssh -L 8480:127.0.0.1:8480 user@dantestreamer-host
   ```

2. Remote access. In the web panel's Settings, turn on remote access and set
   a remote password. Add the host's IP address and that password. This is
   plain HTTP, so use it only on a trusted network or over a VPN.

If the app says the host refused the port, nothing listens there for this
computer. On the DanteStreamer computer itself, use host `localhost`. From
another computer, turn on remote access or open the tunnel first.

To try the apps without a Dante host, run the mock API, which answers like
Virgil with moving meters on TX 1 and 2:

```bash
python3 dantestreamer-desktop/tools/mock_virgil.py            # port 8480
python3 dantestreamer-desktop/tools/mock_virgil.py --password test
```

The apps save the host list on the computer. macOS keeps it in the app's
user defaults and the passwords in the login keychain. Windows keeps both in
`%APPDATA%\DanteStreamerController\instances.json`, with the password
encrypted for the current Windows user (DPAPI).

## Building

See [macos/README.md](macos/README.md) and
[windows/README.md](windows/README.md). The CI workflow is
`.github/workflows/build-desktop.yml`.

The macOS job uses these repository secrets (Settings, Secrets and
variables, Actions):

| Secret | Used for |
|---|---|
| `DEVELOPER_ID_CERT_BASE64`, `DEVELOPER_ID_CERT_PASSWORD` | The Developer ID Application certificate (.p12, base64) and its password. Required. |
| `DEVELOPER_ID_TEAM` or `APPLE_TEAM_ID` | Team ID, part of the certificate name. Required. |
| `APPLE_ID`, `APPLE_APP_PASSWORD` | Notarization with an Apple ID and an app-specific password from appleid.apple.com. The same secrets `installers.yml` uses. |
| `APPLE_API_KEY_ID`, `APPLE_API_ISSUER_ID`, `APPLE_API_KEY_BASE64` | Notarization with an App Store Connect API key instead (the .p8 file in base64). |

Without one of the two notarization sets, the job signs the app, skips
notarization and shows a warning on the run page.

## License

GPLv3, same as DanteStreamer.
