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

## Building

See `macos/README.md` and `windows/README.md` for build instructions.

## License

GPLv3, same as DanteStreamer.
