# Self-Hosted Dante Player Project Guide

Based on **Virgil Virtual Soundcard** as Foundation

---

## Project Overview

You're planning to build a self-hosted Dante audio player using Virgil as the base. Virgil is an open-source implementation of Dante networking that allows computers to join Dante networks as audio devices.

**Virgil's key strengths:**
- Built on **Inferno**, an independent open-source Dante protocol implementation
- Low-latency audio streaming (configurable 0.25–4+ ms)
- Cross-platform: Windows (ASIO), macOS (Core Audio), Linux (ALSA/PipeWire)
- Up to 128 channels each direction at 44.1–96 kHz
- HTTP control panel + CLI interface
- Dante clock management (PTPv1)
- Network resilience (auto-reconnect, dropout logging)

---

## Architecture: Virgil's Key Components

### 1. **Core Layers**

```
┌─────────────────────────────────────────┐
│  OS Audio Drivers (ASIO/Core Audio/ALSA)│  ← Apps see Virgil as soundcard
├─────────────────────────────────────────┤
│  virgil_client (Shared Memory + Mixing) │  ← Platform-specific audio I/O
├─────────────────────────────────────────┤
│  Daemon (virgild) + Engine              │  ← Main audio/control logic
├─────────────────────────────────────────┤
│  Network Library (PTP + Inferno Dante)  │  ← Dante protocol + clocking
├─────────────────────────────────────────┤
│  Inferno (Rust, vendored)               │  ← Dante implementation
└─────────────────────────────────────────┘
```

### 2. **Source Layout**

```
src/
├── daemon/          # Main service (C++)
│   ├── main.cpp     # Entry point, signal handling
│   ├── engine.cpp   # Audio I/O, sample mixing/routing
│   ├── control.cpp  # CLI/config management
│   ├── http_server.cpp  # Web panel API
│   ├── diagnostics.cpp  # Dropout tracking, metrics
│   └── ui/          # Embedded control panel HTML
├── common/          # Shared utilities (C++)
│   ├── net.cpp      # Dante network I/O
│   ├── ptp.cpp      # Dante clock (PTPv1)
│   ├── config.cpp   # Config file parsing
│   ├── platform.cpp # OS-specific audio setup
│   └── client.cpp   # Driver ↔ daemon IPC
└── third_party/
    └── inferno/     # Dante protocol (Rust → C FFI)
```

---

## Building a Dante Player on Virgil

### Option A: Minimal Dante Receiver (Recommended for MVP)

**What you'd build:**
- Extract Virgil's **Dante receive** only (no virtual soundcard driver)
- Custom audio output backend (file write, HTTP streaming, embedded player)
- Simplified control UI

**Reusable Virgil components:**
```
✓ inferno/       (Dante protocol)
✓ src/common/net.cpp, ptp.cpp    (Network handling)
✓ src/common/config.cpp          (Config management)
✓ src/daemon/engine.cpp          (Mix/route logic)
✓ src/daemon/http_server.cpp     (Control API)
```

**What you'd replace:**
- ASIO/Core Audio/ALSA driver glue → Your audio output (file, HTTP, embedded DAC)
- Shared memory IPC → Direct in-process or UDP API

**Effort:** ~40% of Virgil's codebase

---

### Option B: Full Fork (Maximum Flexibility)

**Clone Virgil entirely**, then:**
1. Remove driver layers you don't need (ASIO, Core Audio, ALSA)
2. Add your custom audio output (embedded playback, streaming, DSP)
3. Extend HTTP API for player-specific features (playlists, EQ, recording)
4. Customize UI/branding

**Effort:** ~100% of Virgil, but complete control

---

## Getting Started: Step-by-Step

### Phase 1: Setup & Understanding (Week 1)

1. **Build Virgil as-is** on your target platform:
   ```bash
   cd virgil-virtual-soundcard
   mkdir build && cd build
   cmake .. -DCMAKE_BUILD_TYPE=Release
   cmake --build .
   ```
   - This verifies Dante networking works on your hardware
   - Test with Dante Controller (or on a Dante network)

2. **Study the codebase:**
   - `src/daemon/engine.cpp`: Core audio processing loop
   - `src/daemon/main.cpp`: Service lifecycle, config loading
   - `src/common/net.cpp`: Dante packet send/receive
   - `src/common/ptp.cpp`: Clock synchronization
   - `third_party/inferno/`: Dante implementation (Rust; understand its C API)

3. **Run diagnostics:**
   ```bash
   # Check what Virgil exports
   grep -r "inferno" src/common/net.cpp
   grep -r "struct" include/*.h
   ```

### Phase 2: Extract Receive Path (Weeks 2–3)

**Goal:** Dante audio → your audio backend (bypassing ASIO/Core Audio/ALSA)

1. **Isolate Dante receive in `engine.cpp`:**
   - Find the loop that fills Dante receive buffers
   - Trace calls to `inferno_*` functions
   - Understand sample format, channel mapping, latency config

2. **Create a minimal player stub:**
   ```cpp
   // minimal_player.cpp
   #include "include/virgil/config.h"
   #include "src/common/net.h"      // Dante I/O
   #include "src/common/ptp.h"      // Clocking
   
   int main() {
       // 1. Init config from file or CLI
       // 2. Join Dante network (net.cpp functions)
       // 3. Enter PTP clock sync (ptp.cpp)
       // 4. Loop: receive Dante packets → decode → output
       // 5. Cleanup
   }
   ```

3. **Pick audio output:**
   - **File**: Simple, debugging-friendly
     ```cpp
     FILE* out = fopen("dante_out.wav", "wb");
     // Write received samples as WAV
     ```
   - **PulseAudio / JACK** (Linux): `src/common/platform.cpp` has hooks
   - **HTTP streaming** (web player): Add WebSocket to HTTP server
   - **Embedded DAC** (Raspberry Pi): GPIO or I²S via ALSA

### Phase 3: Control & Configuration (Week 4)

1. **Extend HTTP API** (`src/daemon/http_server.cpp`):
   - `/api/status` → player state, channel levels
   - `/api/channels` → Dante channel listing, enable/disable
   - `/api/config` → latency, sample rate, output format

2. **Simple UI:**
   - Web panel (reuse Virgil's `src/daemon/ui/index.html` as template)
   - Or CLI tool (`src/daemon/control.cpp` for reference)

3. **Config file** (TOML/JSON):
   ```toml
   [device]
   enabled = true
   name = "MyDantePlayer"
   
   [output]
   type = "file"  # or "http", "alsa", "embedded"
   path = "/var/audio/dante_stream.wav"
   
   [network]
   interface = "eth0"
   ```

### Phase 4: Integration & Testing (Weeks 5+)

1. **Test on real Dante network:**
   - Get a Dante-capable device or VM
   - Route Dante channels to your player
   - Measure latency, dropout behavior

2. **Performance tuning:**
   - Adjust `latency_us`, `tx_latency_us` in config
   - Profile CPU load (`top`, `perf`)
   - Monitor dropout logs

3. **Packaging:**
   - Linux: Debian/systemd integration (copy from `packaging/`)
   - RPi: Init script + auto-start
   - Cross-compile if needed

---

## Code Map: Where to Start Reading

| File | Purpose | Lines |
|------|---------|-------|
| `src/daemon/engine.cpp` | Audio loop, Dante RX/TX, mixing | ~1000 |
| `src/daemon/main.cpp` | Config load, service setup | ~500 |
| `src/common/net.cpp` | Dante network, socket I/O | ~600 |
| `src/common/ptp.cpp` | Clock sync (PTPv1) | ~700 |
| `include/virgil/*.h` | Public APIs | ~400 |
| `third_party/inferno/` | Dante wire protocol | ~5k (Rust) |

**Read in this order:**
1. `src/daemon/main.cpp` (entry point)
2. `src/daemon/engine.cpp` (audio flow)
3. `src/common/net.cpp` (network setup)
4. `include/virgil/` (data structures)

---

## Quick Build Checklist for MVP

```markdown
- [ ] Clone Virgil, build successfully on your platform
- [ ] Run Virgil, confirm it appears in Dante Controller
- [ ] Read engine.cpp → understand Dante receive loop
- [ ] Create minimal_player.cpp with Dante RX only
- [ ] Add basic audio output (WAV file or stdout)
- [ ] Test receive audio from a Dante source
- [ ] Add HTTP control API
- [ ] Add CLI tool for config management
- [ ] Package for Linux/RPi
- [ ] Test end-to-end on real Dante network
```

---

## Useful Resources Inside Virgil

- **`docs/`** → Design docs, protocol notes
- **`tests/`** → Unit tests, loopback tests (great for understanding APIs)
- **`packaging/`** → Installer scripts, systemd units, config templates
- **`CMakeLists.txt`** → Build system (C++17, thread library, platform flags)
- **`CHANGELOG.md`** → Feature evolution, past decisions

---

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| Dante protocol complexity | Inferno handles wire protocol; focus on `net.cpp` API |
| Audio latency issues | Virgil's tuning docs + built-in latency measurement |
| Network resilience | Copy Virgil's dropout handling, PTP failover logic |
| Cross-platform audio | Start with Linux (ALSA/PipeWire), add macOS/Windows later |
| Real-time constraints | Copy Virgil's thread priorities, buffer strategy from `engine.cpp` |

---

## Next Steps

1. **Clone & build** Virgil locally
2. **Explore** the codebase with this map as guide
3. **Decide:** Option A (minimal extract) or Option B (full fork)?
4. **Prototype** minimal Dante receive → file output
5. **Share** findings; iterate on architecture

The beauty of Virgil as a foundation: **it already solves Dante networking, clocking, and config management**. You're building the **player-specific layer** on top.

---

**Generated:** 2026-10-27  
**Virgil Version:** 0.8.2  
**Project Lead:** @johanhoel
