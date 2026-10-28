# DanteStreamer Desktop

Desktop apps for macOS and Windows that show the state of one or more
[DanteStreamer](../dantestreamer/) hosts. They read the Virgil control API on
port 8480, the same data the web panel shows.

What both apps do:

- Keep a list of DanteStreamer hosts (name, host, port, remote password).
- Show the device, engine state, network address, clock state and leader,
  sample rate, channels, dropouts in the last hour and the apps playing.
- Show live TX and RX meters per Dante channel on a -60 to 0 dBFS scale,
  with the channel names from Dante Controller.
- Start, stop or restart the audio engine (`/api/start`, `/api/stop`,
  `/api/restart`).

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
  Needs macOS 12 or later. The app is signed with a Developer ID but not
  notarized, so the first time you right-click it and choose Open.
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

The apps save the host list on the computer: macOS in the app's user
defaults, Windows in `%APPDATA%\DanteStreamerController\instances.json`.
Passwords are saved there in plain text.

## Building

See [macos/README.md](macos/README.md) and
[windows/README.md](windows/README.md). The CI workflow is
`.github/workflows/build-desktop.yml`.

## License

GPLv3, same as DanteStreamer.
