# DanteStreamer Controller – macOS

Native SwiftUI application for controlling DanteStreamer from macOS.

## Features

- **Instance management** – Save and switch between multiple DanteStreamer instances
- **Local & VPN** – Connect via local network (mDNS discovery) or over VPN
- **Status dashboard** – Real-time clock lock, sample rate, device state
- **Level meters** – Live audio levels for all Dante TX and RX channels
- **Responsive UI** – Built with SwiftUI for native macOS look and feel

## System Requirements

- macOS 12.0 or later
- Xcode 14.0 or later (for building)

## Building

```bash
cd dantestreamer-desktop/macos
swift build -c release
```

Output binary: `.build/release/DanteStreamerController`

Or build and run directly:

```bash
swift run -c release
```

## Architecture

- **ConnectionManager** – Manages API connections and polling to DanteStreamer instances
- **ContentView** – Sidebar with instance list, detail view for selected instance
- **DetailView** – Status tab (device info, clock state) and meters tab (live levels)
- **API client** – REST API calls via URLSession (no external dependencies)

## API Integration

Connects to DanteStreamer REST API (default port 8480):

- `GET /api/status` – Fetch device status, meters, channel info
- `GET /api/config` – Read current configuration (future feature)
- `POST /api/start`, `/api/stop` – Device control (future feature)

## Future Features

- Audio transmit/receive via WASAPI or CoreAudio
- Recording to local file
- Dante routing controls
- Remote password authentication
