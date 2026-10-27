# Dante Player: Build & Test Guide

Setup, build, and test your Dante player project locally.

---

## Prerequisites

### Linux (Debian/Ubuntu)
```bash
sudo apt update
sudo apt install -y \
    build-essential \
    cmake \
    git \
    libpthread-stubs0-dev \
    rustc cargo
```

### macOS
```bash
# Install Xcode Command Line Tools
xcode-select --install

# Install Homebrew (if not already)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install dependencies
brew install cmake rust
```

### Windows (MSVC)
- Visual Studio 2019+ with C++ workload
- CMake (from cmake.org or via `choco install cmake`)
- Rust (from rustup.rs)

---

## Build Virgil Reference Implementation

This gives you a working Dante stack to learn from:

```bash
cd /tmp
git clone --depth 1 https://github.com/Audbol/virgil-virtual-soundcard.git
cd virgil-virtual-soundcard
mkdir build && cd build

# Configure
cmake .. -DCMAKE_BUILD_TYPE=Release

# Build
cmake --build . --config Release -j $(nproc)

# Install (optional)
sudo cmake --install .
```

**Expected output:**
- `virgild` (daemon binary)
- `virgil_control` (GUI app)
- Driver (ASIO/Core Audio/ALSA, platform-specific)

**Test it:**
```bash
# Linux/macOS
./virgild --help
./virgild --config /path/to/virgil.conf

# macOS: Check if loaded
system_profiler SPAudioDataType | grep Virgil

# Linux: Check ALSA
aplay -l | grep -i virgil
```

---

## Project Structure for Your Player

```
dante-player/
├── CMakeLists.txt                  # Main build config
├── src/
│   ├── main.cpp                    # Entry point
│   ├── dante_receiver.cpp          # Dante RX logic
│   ├── audio_output.cpp            # Your output backend
│   └── control_api.cpp             # HTTP control API
├── include/
│   └── dante_player/
│       ├── dante_receiver.h
│       ├── audio_output.h
│       └── config.h
├── config/
│   └── dante_player.toml           # Default config
├── tests/
│   └── test_dante_rx.cpp           # Unit tests
├── scripts/
│   ├── install.sh
│   └── configure.sh
└── README.md
```

---

## Setup: Extract Virgil Components

### Copy Inferno + Common Code
```bash
mkdir -p dante-player
cd dante-player

# Copy Dante protocol implementation
cp -r ../virgil-virtual-soundcard/third_party/inferno ./

# Copy common utilities
cp -r ../virgil-virtual-soundcard/src/common ./dante_common
cp -r ../virgil-virtual-soundcard/include ./
cp ../virgil-virtual-soundcard/CMakeLists.txt ./CMakeLists.virgil

# Copy cmake helpers
cp -r ../virgil-virtual-soundcard/cmake ./
```

### Minimal CMakeLists.txt
```cmake
cmake_minimum_required(VERSION 3.16)
project(dante-player VERSION 0.1.0 LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(Threads REQUIRED)

# Include Inferno bridge (Rust → C FFI)
include(cmake/rust_bridge.cmake)

# Build your player
add_executable(dante-player
    src/main.cpp
    src/dante_receiver.cpp
    src/audio_output.cpp
    dante_common/log.cpp
    dante_common/net.cpp
    dante_common/ptp.cpp
    dante_common/config.cpp
    dante_common/platform.cpp
)

target_include_directories(dante-player PRIVATE include dante_common)
target_link_libraries(dante-player PRIVATE
    Threads::Threads
    virgil_dante  # From Inferno
)

if(WIN32)
    target_link_libraries(dante-player PRIVATE ws2_32 iphlpapi)
elseif(UNIX AND NOT APPLE)
    target_link_libraries(dante-player PRIVATE rt)
endif()
```

---

## Build Your Player

```bash
cd dante-player
mkdir build && cd build

# Configure
cmake .. -DCMAKE_BUILD_TYPE=Release

# Build
cmake --build . --config Release -j $(nproc)

# Run
./dante-player --config ../config/dante_player.toml
```

---

## Testing Strategy

### Phase 1: Compilation & Linkage
```bash
# 1. Compile successfully
cmake --build . 2>&1 | tee build.log
if [ $? -eq 0 ]; then echo "✓ Build OK"; else echo "✗ Build failed"; fi

# 2. Check for undefined symbols
nm ./dante-player | grep "U " | head -10
# Should see mostly stdlib functions; no Dante protocol symbols
```

### Phase 2: Unit Tests (Standalone)
```cpp
// tests/test_dante_rx.cpp
#include <gtest/gtest.h>
#include "dante_player/dante_receiver.h"

TEST(DanteReceiver, Initialize) {
    Config cfg;
    cfg.load_from_file("../config/dante_player.toml");
    
    DanteReceiver rx(cfg);
    EXPECT_TRUE(rx.is_initialized());
}

TEST(DanteReceiver, ReceiveBuffer) {
    // Mock Dante network, verify rx buffer fills correctly
    std::vector<float> buffer(4096 * 8);
    rx.receive_audio(buffer.data(), 8, 4096);
    // Check for zeros (no Dante traffic) or valid samples
}
```

**Build & run tests:**
```bash
cmake --build . --target tests
./tests/test_dante_rx --gtest_repeat=5
```

### Phase 3: Integration Test (Loopback)
```bash
# Start your player
./dante-player --config test.toml &
PLAYER_PID=$!

sleep 2

# Verify network interface joined
ip addr show  # Should see multicast
netstat -un | grep -E "319|320|4440"  # Dante ports

# Simulate Dante audio input (via test tool or Virgil)
# Generate test tone, route to player's receive channels
# Record output, verify audio
ffmpeg -f lavfi -i sine=f=440:d=5 -f f32le - | \
  ./dante-player --input - &

sleep 3
kill $PLAYER_PID
```

### Phase 4: Real Dante Network Test
```bash
# Prerequisites:
# - Connect to a real Dante network (or Dante-capable VM)
# - Have a Dante source (Dante interface, another Virgil, etc.)
# - Have Dante Controller or a Dante-aware device

# Run player
./dante-player --config dante_player.toml &

# In Dante Controller:
# 1. Verify "MyDantePlayer" appears in device list
# 2. Check clock lock (PTP sync)
# 3. Route a Dante channel to player's receive
# 4. Play audio, verify it's received
# 5. Monitor dropout count (should be 0)

# Verify via player logs
./dante-player --log-level debug 2>&1 | grep -E "clock|dropout|received"
```

---

## Configuration File

**dante_player.toml** (TOML format)
```toml
[device]
name = "MyDantePlayer"
enabled = true
model = "dante-player"
version = "0.1.0"

[network]
# Dante network interface (eth0, en0, etc.)
# Leave empty to auto-detect
interface = ""

# Dante device name (as seen in Controller)
dante_name = "MyDantePlayer"

# Latency tuning (in microseconds)
tx_latency_us = 4000      # Transmit (ahead of time)
latency_us = 4000         # Receive (buffer depth)

[ptp]
# Can this device lead the Dante clock?
master_capable = false

[audio]
sample_rate = 48000
channels = 8

[logging]
level = "info"            # debug, info, warn, error
file = "/var/log/dante-player.log"
max_file_size = 10485760  # 10 MB

[output]
# Output backend: file, http, alsa, custom
type = "file"
path = "/tmp/dante_out.pcm"

[http]
# Control API
enabled = true
port = 8080
allow_remote = false      # Can other hosts connect?
```

---

## Common Build Issues & Fixes

### Issue: `error: Could not find Rust bridge (virgil_dante)`
**Cause:** Inferno build failed (Rust compiler issue)  
**Fix:**
```bash
cd inferno/crates/dante
cargo build --release
cd ../../../
cmake ..
```

### Issue: `undefined reference to 'inferno_...'`
**Cause:** Inferno library not linked  
**Fix:**
```bash
# Check if virgil_dante is built
ls -la build/*/virgil_dante* 
# If missing:
cmake --build . --target virgil_dante
```

### Issue: `Port 4440 already in use`
**Cause:** Another Dante app (Virgil, Focusrite Control, etc.) is running  
**Fix:**
```bash
# Kill competing process
pkill -f virgild
pkill -f dante

# Or use alternate ports in config:
# [network]
# ports = "24440-24443"
```

### Issue: `No network interfaces detected`
**Cause:** Missing network access or Linux permission  
**Fix:**
```bash
# Check interfaces
ip link show

# Add user to dialout group (Linux)
sudo usermod -a -G dialout $USER
newgrp dialout
```

### Issue: Compilation fails on macOS (`AudioServerPlugIn not found`)
**Cause:** CoreAudio headers missing  
**Fix:**
```bash
# You don't need the ASIO/CoreAudio driver for MVP
# Edit CMakeLists.txt:
cmake .. -DVIRGIL_BUILD_COREAUDIO=OFF -DVIRGIL_BUILD_ASIO=OFF
```

---

## Performance Profiling

### Linux: CPU & Memory Usage
```bash
# Run under perf
perf record -F 99 ./dante-player --config dante_player.toml
sleep 10
perf report

# Or use valgrind for memory leaks
valgrind --leak-check=full ./dante-player --config dante_player.toml
```

### macOS: Instruments
```bash
# Profile with Xcode Instruments
xcrun xctrace record --template 'System Trace' --output dante_trace.trace \
  -- ./dante-player --config dante_player.toml
```

### Dropout Monitoring
```bash
# Enable verbose logging
DANTE_PLAYER_LOG=debug ./dante-player 2>&1 | tee player.log

# Count dropouts
grep -c "dropout\|underrun\|overrun" player.log

# Export diagnostics
./dante-player --export-report dante_diagnostics.json
```

---

## Deployment Checklist

- [ ] Builds cleanly on target platform (Linux, macOS, Windows)
- [ ] Runs without errors when Dante network unavailable
- [ ] Receives audio correctly on real Dante network
- [ ] Clock locks within 5 seconds
- [ ] No dropouts on stable network
- [ ] CPU load < 10% on i5/AMD equivalent
- [ ] HTTP control API responds within 100 ms
- [ ] Graceful shutdown (no hanging threads)
- [ ] Logs rotate (doesn't fill disk)
- [ ] Config can be updated without restart
- [ ] Survives network interface changes (Wi-Fi reconnect, etc.)
- [ ] Works on Raspberry Pi 4+ (cross-compile test)

---

## Next Steps

1. **Build Virgil** → Verify Dante stack works
2. **Extract components** → Copy net.cpp, ptp.cpp, config.cpp to your project
3. **Write minimal main.cpp** → Initialize network, enter PTP sync
4. **Add audio output** → File, HTTP, or ALSA backend
5. **Test loopback** → Dante → player → file
6. **Test real network** → Route actual Dante audio
7. **Optimize** → Tune latency, monitor dropouts
8. **Package** → Create installable (systemd service, etc.)

---

**Tips:**
- Start with file output (easiest to debug)
- Keep log level at `debug` during development
- Use Dante Controller or Virgil Control to monitor network state
- Test on isolated Dante network first, then production
- Save dropout logs for performance analysis

