# DanteStreamer Desktop

Native desktop control applications for macOS and Windows to connect to DanteStreamer instances on local networks or over VPN.

## Features

- **Multi-instance discovery & connection** – Find DanteStreamer on local network via mDNS, or connect over VPN with manual IP
- **Real-time status** – Clock lock, sample rate, channels, connected apps
- **Level meters** – Live audio levels for Dante TX and RX channels
- **Audio control** – Transmit/receive channel management, gain, mute
- **Device profiles** – Save and switch between multiple DanteStreamer instances
- **Network support** – Local network and VPN connections

## Apps

### macOS (`macos/`)
Swift/SwiftUI native app for macOS 12+. Uses system audio frameworks for play/receive.

### Windows (`windows/`)
C# WPF modern Windows app. Uses WASAPI for audio routing.

## Downloads

Prebuilt binaries available on [GitHub Releases](https://github.com/johanhoel/Amplitude/releases):

- **macOS**: `DanteStreamer-macos.zip` – Extract and run `DanteStreamer.app`. Requires macOS 12.0+
- **Windows**: `DanteStreamerController-windows.zip` – Extract and run `DanteStreamerController.exe`. Requires Windows 10+. Includes all dependencies (no .NET runtime needed).

## Building from Source

See `macos/README.md` and `windows/README.md` for build instructions.

## License

GPLv3, same as DanteStreamer.
