# DanteStreamer Controller – Windows

Native WPF application for controlling DanteStreamer from Windows 10+.

## Features

- **Instance management** – Save and switch between multiple DanteStreamer instances
- **Local & VPN** – Connect via local network or over VPN with manual IP entry
- **Status dashboard** – Real-time clock lock, sample rate, device state, audio configuration
- **Level meters** – Live audio levels for all Dante TX and RX channels (future)
- **Modern UI** – WPF with MVVM architecture

## System Requirements

- Windows 10 or later
- .NET 8.0 Runtime
- Visual Studio 2022 (for building)

## Building

```bash
cd dantestreamer-desktop/windows
dotnet build -c Release
```

Output: `bin/Release/net8.0-windows/DanteStreamerController.exe`

Or build and run:

```bash
dotnet run -c Release
```

## Architecture

- **ConnectionViewModel** – MVVM view model handling API calls, polling, instance management
- **MainWindow** – WPF UI with tabbed interface (Status, Meters)
- **DanteModels** – Data structures matching DanteStreamer REST API
- **HTTP client** – REST API integration via HttpClient

## API Integration

Connects to DanteStreamer REST API (default port 8480):

- `GET /api/status` – Device status, meters, channel names
- `GET /api/config` – Configuration (future)
- `POST /api/start`, `/api/stop` – Device control (future)

## Data Persistence

Instance profiles stored in:
```
%APPDATA%\DanteStreamerController\instances.json
```

## Future Features

- Audio transmit/receive via WASAPI
- Recording to local file
- Dante routing controls
- Enhanced meter visualization
- Remote password authentication
