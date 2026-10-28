# Changelog

All notable changes to DanteStreamer Desktop will be documented in this file.

## [1.0.0] – 2026-10-28

### Added

- **macOS app** (Swift/SwiftUI)
  - Native control application for macOS 12+
  - Instance discovery via mDNS on local network
  - Manual IP entry for VPN connections
  - Real-time status dashboard (device info, clock lock, sample rate)
  - Live level meters for TX and RX channels
  - Instance profiles (save and switch between multiple DanteStreamer instances)
  - Responsive UI with tabbed interface

- **Windows app** (C# WPF)
  - Native control application for Windows 10+
  - Same feature set as macOS version
  - MVVM architecture for clean separation of concerns
  - Instance persistence to AppData
  - Modern WPF UI with tabbed interface

### Planned

- Audio transmit/receive via CoreAudio (macOS) and WASAPI (Windows)
- Recording to MP3/WAV/AAC
- Dante routing controls
- Enhanced meter visualization with peak hold
- Remote password authentication
- mDNS discovery on Windows (for local network instances)
