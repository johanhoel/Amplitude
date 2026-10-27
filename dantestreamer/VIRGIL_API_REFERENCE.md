# Virgil API Reference for Dante Player

Quick lookup for key functions and data structures you'll reuse.

---

## Network & Dante (src/common/net.cpp)

### Initialize Dante Network
```cpp
// From src/daemon/engine.cpp
class Engine {
    std::unique_ptr<Net> net_;  // Dante network instance
};

// Create network interface
auto net = std::make_unique<Net>(config, logger);
net->start();  // Join Dante network
```

**Key struct: `Netconfig`** (from `src/common/config.cpp`)
```cpp
struct Netconfig {
    std::string interface;           // "eth0", "en0", etc.
    std::string device_name;         // "Virgil-hostname"
    int tx_latency_us = 4000;       // Transmit latency (4 ms default)
    int latency_us = 4000;          // Receive latency
    bool master_capable = false;    // Can lead Dante clock?
};
```

### Receive Dante Audio
```cpp
// Inside Engine::mix_to_dante() loop
// net_->receive_audio() fills buffers from Dante network
std::vector<float> dante_in(num_channels * num_samples);
net_->receive_audio(dante_in.data(), num_channels, num_samples);
// dante_in now contains float samples [0.0 .. 1.0]
```

**Dante packet structure** (in `third_party/inferno/`)
- UDP multicast (224.x.x.x or 239.x.x.x)
- Ports: 4440, 4455, 8700, 8800 (or 24440–24443 if reusing)
- PTP (Precision Time Protocol): UDP 319/320
- mDNS discovery: UDP 5353

---

## PTP Clock Synchronization (src/common/ptp.cpp)

### Dante Clock Management
```cpp
class Ptp {
public:
    bool start(const std::string& interface);
    bool is_locked() const;              // Clock synced?
    int64_t get_time_ns() const;         // Dante network time
    void set_master_capable(bool capable);
};

// Usage in engine:
if (!ptp_->is_locked()) {
    LOG_WARN("Dante clock not yet synced");
}
```

**Key concept:** Dante uses PTPv1 (not PTPv2). One device is "Leader", others "Followers".

```cpp
if (config.ptp.master_capable && no_dante_devices_on_network) {
    ptp_->set_master_capable(true);  // Become leader
    // Other Virgil nodes follow this clock
}
```

---

## Audio Engine (src/daemon/engine.cpp)

### Main Mix Loop
```cpp
void Engine::mix() {
    // 1. Receive from Dante network
    receive_from_dante();
    
    // 2. Mix desktop audio + audio interface inputs
    mix_sources();
    
    // 3. Transmit to Dante network
    transmit_to_dante();
    
    // 4. Output to audio interface
    output_to_audio_interface();
}
```

### Audio Buffers & Channels
```cpp
struct AudioBuffer {
    float* data;                // Interleaved or planar?
    int num_channels;           // 1-128
    int num_samples;            // Depends on buffer size
    int sample_rate;            // 44100, 48000, 96000
};

// Dante supports:
// - Channels: 1-128 each direction
// - Sample rates: 44.1 kHz, 48 kHz, 96 kHz
// - Format: 32-bit float (internally)
```

### Configuration from File
```cpp
// src/common/config.cpp
class Config {
public:
    bool load_from_file(const std::string& path);
    const Netconfig& network() const;
    const AudioConfig& audio() const;
};

// Example config file (TOML):
// [device]
// enabled = true
// name = "MyDantePlayer"
// [network]
// interface = "eth0"
// [audio]
// sample_rate = 48000
// channels = 8
```

---

## Control API (src/daemon/http_server.cpp)

### HTTP Endpoints (for your UI)
```cpp
// Embedded HTTP server, runs on port 8700+ or custom
class HttpServer {
public:
    void add_route(const std::string& path, Handler handler);
};

// Virgil exposes these (reuse pattern):
// GET  /status          → { enabled, clock_locked, channels, ... }
// GET  /channels        → [ {name, rx_enabled, tx_enabled, level}, ... ]
// POST /config          → Update settings
// GET  /diagnostics    → Dropout log, latency history
```

**Example control response:**
```json
{
  "device_name": "Virgil-MyPC",
  "enabled": true,
  "clock_locked": true,
  "sample_rate": 48000,
  "tx_latency_us": 4000,
  "channels": 8,
  "receive_channels": [
    {"index": 0, "name": "L", "level_db": -20.5, "subscribed": true},
    {"index": 1, "name": "R", "level_db": -21.2, "subscribed": true}
  ]
}
```

---

## Configuration Management (src/common/config.cpp)

### Config File Format (TOML)
```toml
[device]
name = "MyDantePlayer"
enabled = true

[network]
interface = "eth0"
tx_latency_us = 4000
latency_us = 4000

[ptp]
master_capable = false

[audio]
sample_rate = 48000
channels = 8
```

### Load & Parse
```cpp
Config config;
if (!config.load_from_file("/etc/dante-player/config.toml")) {
    LOG_ERROR("Failed to load config");
    return 1;
}

auto netconfig = config.network();
auto audioconfig = config.audio();
```

---

## Logging & Diagnostics (src/daemon/diagnostics.cpp)

### Dropout Detection
```cpp
class Diagnostics {
public:
    void log_dropout(const std::string& reason);
    std::vector<DropoutEvent> get_history();
    void export_report(const std::string& path);
};

// Virgil tracks:
// - Rx underruns (couldn't keep up with Dante)
// - Tx overruns (app didn't provide audio in time)
// - PTP sync loss (clock leader disappeared)
// - Network errors
```

### Enable Logging
```cpp
// Set environment variable or config:
// VIRGIL_LOG=debug
// or in config.toml:
// [logging]
// level = "debug"
```

---

## Threading Model

**Key threads in Virgil:**
1. **Main thread** → config, control API, UI
2. **Audio thread** (real-time) → engine.cpp mix loop
3. **Network thread** → Dante packet I/O (blocking recv/send)
4. **PTP thread** → Clock sync (low frequency)
5. **HTTP server thread** → Control endpoints

**Synchronization:** Lock-free queues for audio ↔ network, mutexes for config.

---

## Platform Abstraction (src/common/platform.cpp)

### OS-Specific Wrappers
```cpp
namespace platform {
    // Get network interfaces
    std::vector<std::string> get_network_interfaces();
    
    // Get audio devices (ALSA, Core Audio, ASIO)
    std::vector<AudioDevice> enumerate_audio_devices();
    
    // Set thread priority (real-time)
    bool set_thread_realtime(int priority);
};
```

---

## Building Your Player: Minimal Template

```cpp
// dante_player.cpp
#include "include/virgil/config.h"
#include "src/common/net.h"
#include "src/common/ptp.h"
#include "src/common/log.h"
#include <vector>
#include <fstream>

int main(int argc, char* argv[]) {
    // 1. Load config
    Config config;
    config.load_from_file("dante_player.toml");
    
    // 2. Initialize network + Dante
    auto net = std::make_unique<Net>(config.network(), Logger());
    auto ptp = std::make_unique<Ptp>();
    
    net->start();
    ptp->start(config.network().interface);
    
    // 3. Wait for clock sync
    while (!ptp->is_locked()) {
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }
    std::cout << "Clock synchronized!" << std::endl;
    
    // 4. Audio loop
    std::ofstream wav_out("dante_output.pcm", std::ios::binary);
    std::vector<float> buffer(4096 * 8);  // 4096 samples, 8 channels
    
    for (int i = 0; i < 48000; ++i) {  // 1 second
        net->receive_audio(buffer.data(), 8, 4096);
        wav_out.write((char*)buffer.data(), buffer.size() * sizeof(float));
    }
    
    // 5. Cleanup
    net->stop();
    ptp->stop();
    
    return 0;
}
```

**Compile:**
```bash
g++ -std=c++17 dante_player.cpp \
    src/common/net.cpp src/common/ptp.cpp src/common/config.cpp \
    src/common/log.cpp src/common/platform.cpp \
    -lpthread -o dante_player
```

---

## Key Headers to Include

```cpp
// Network
#include "src/common/net.h"
#include "src/common/ptp.h"

// Config
#include "src/common/config.h"
#include "src/common/log.h"

// Audio
#include "src/daemon/engine.h"

// Dante protocol (through Inferno bridge)
#include "src/common/net.h"  // net.h exposes Inferno functions
```

---

## Common Patterns

### Listen on Specific Dante Channels
```cpp
// In Engine::mix():
// Subscribe to receive channels 1-2 (L/R) from another device
net_->subscribe_channel(1);  // Left
net_->subscribe_channel(2);  // Right

// Get samples for those channels
std::vector<float> dante_rx = net_->get_receive_buffer(num_samples);
```

### Set Transmit Levels
```cpp
// Transmit your audio at lower level (avoid clipping)
for (auto& sample : audio_buffer) {
    sample *= 0.9;  // -0.91 dB headroom
}
net_->transmit_audio(audio_buffer.data(), num_channels, num_samples);
```

### Monitor Network Health
```cpp
if (diag_->get_dropout_count() > 0) {
    auto events = diag_->get_history();
    for (const auto& event : events) {
        LOG_WARN("Dropout at %llu: %s", event.timestamp, event.reason);
    }
}
```

---

## References Inside Virgil

- **Header files:** `include/virgil/*.h`
- **Protocol docs:** `docs/*.md`
- **Tests:** `tests/` (loopback tests show real API usage)
- **Inferno Rust API:** `third_party/inferno/crates/dante/src/lib.rs`

---

**Next:** Use this reference while reading `src/daemon/engine.cpp` and `src/daemon/main.cpp` to understand the full flow.
