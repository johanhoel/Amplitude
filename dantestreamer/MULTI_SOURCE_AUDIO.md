# Multi-Source Audio: AirPlay + Google Cast → Dante

DanteStreamer receives audio from multiple sources simultaneously and outputs to a single Dante network stream.

---

## Architecture

```
┌────────────────────────────────────────────────────────┐
│                 Input Sources                          │
├────────────────────────────────────────────────────────┤
│                                                        │
│  • AirPlay (iOS/macOS)    → Shairport-sync (5000)     │
│  • Google Cast (Android)  → Snapserver (1704)         │
│  • Native Dante           → DanteStreamer (multicast) │
│                                                        │
└────────────────┬────────────────────────────────────────┘
                 │
        ┌────────▼─────────┐
        │   PulseAudio     │  Captures all sources
        │   (virtual sink) │
        └────────┬─────────┘
                 │
        ┌────────▼──────────┐
        │   ALSA Mixer      │  Combines streams
        │   (dmix)          │
        └────────┬──────────┘
                 │
        ┌────────▼────────────────┐
        │  DanteStreamer Engine   │  Encodes to Dante
        │  (Inferno protocol)     │
        └────────┬────────────────┘
                 │
            ┌────▼───────┐
            │ Dante Network
            │ (UDP Multicast)
            └─────────────┘
```

---

## How It Works

### 1. AirPlay Input (iOS, macOS)

**Shairport-sync** listens on port 5000 for AirPlay streams.

**From iOS:**
```
Control Center → AirPlay → Select "DanteStreamer" → Audio streams in
```

**From macOS:**
```
System Preferences → Sound → Output → Select "DanteStreamer AirPlay"
```

**Latency:** ~100–200 ms (typical for AirPlay)

**Config:** `config/shairport-sync.conf`

---

### 2. Google Cast Input (Android, Chromecast)

**Snapserver** listens on port 1704 for Chromecast streams.

**From Android:**
```
Google Home app → Select "DanteStreamer Cast" → Audio streams in
```

**From Chromecast device:**
```
Tap Cast button on any media app → Select "DanteStreamer Cast"
```

**Latency:** ~200–500 ms (typical for Chromecast)

**Config:** `config/snapserver.conf`

---

### 3. Dante Input (Optional)

Virgil can also **receive Dante audio** from other devices on the network and pass it through.

**Use case:** Mix Dante sources with AirPlay/Cast.

**Config:** Enable `dante_input_enabled = true` in `dantestreamer.conf`

---

## Audio Mixing Strategy

### Default: Mix Mode
```
AirPlay (iOS)     \
                   → ALSA Mixer → Dante Output
Google Cast (Android) /
```

**Behavior:** Both sources play simultaneously, mixed into one output.

**Levels:** Configure `airplay_priority` and `chromecast_priority` in config to boost/mute specific sources.

```toml
[inputs]
airplay_priority = 1       # Equal volume
chromecast_priority = 1    # Equal volume
```

### Alternative: Priority Mode
```
[mixer]
mode = "priority"          # Highest priority wins
```

**Behavior:** When both AirPlay and Cast active, only the one with highest priority plays.

### Alternative: Crossfade Mode
```
[mixer]
mode = "crossfade"         # Fade when switching
```

**Behavior:** Smoothly fade out one source when another starts.

---

## Configuration

### Enable/Disable Sources

```toml
[inputs]
airplay_enabled = true
airplay_port = 5000

chromecast_enabled = true
chromecast_port = 1704
```

Restart to apply:
```bash
docker-compose restart dantestreamer
```

### Adjust Mixing

```toml
[mixer]
mode = "mix"              # mix, priority, or crossfade
buffer_size = 4096
period_size = 1024
channels = 2              # 1=mono, 2=stereo
```

### Latency Tuning

```toml
[audio]
sample_rate = 48000       # Match your Dante network
channels = 8              # Output channels

[inputs]
# Each source has buffer
shairport_buffer = 4410   # ~100ms at 44.1kHz
snapcast_buffer = 4410
```

---

## Usage Scenarios

### Scenario 1: Home Stereo
**Device:** TV with AirPlay + Chromecast built-in
**Setup:**
1. TV sees DanteStreamer on network
2. Guest plays AirPlay from iPhone → audio on TV speakers
3. Another guest plays Chromecast from Android → mixed with iPhone
4. All audio routes to Dante speaker system

**Config:**
```toml
[mixer]
mode = "mix"              # Both play simultaneously
channels = 2              # Stereo output
```

### Scenario 2: Live Event
**Device:** Conference room audio system
**Setup:**
1. Presenter connects via AirPlay (Mac laptop)
2. Audience uses Chromecast for background music
3. Both feed Dante mixer for main speakers
4. Audio engineer controls levels in Dante Controller

**Config:**
```toml
[inputs]
airplay_priority = 10     # Presenter louder
chromecast_priority = 1   # Background music quieter

[mixer]
mode = "mix"
```

### Scenario 3: DJ + Live Band
**Device:** Festival sound system
**Setup:**
1. DJ sends audio via Chromecast (laptop)
2. Band sends live feed via Dante (mixer on stage)
3. DJ voice chats via AirPlay (iPhone)
4. All three mixed to main PA system

**Config:**
```toml
[inputs]
airplay_enabled = true
chromecast_enabled = true
dante_input_enabled = true

[mixer]
mode = "priority"         # Switch between sources quickly
```

---

## API Endpoints

### Get Input Status
```bash
curl http://localhost:8080/inputs/status
```

**Response:**
```json
{
  "airplay": {
    "enabled": true,
    "connected": true,
    "device_name": "iPhone",
    "sample_rate": 48000,
    "channels": 2,
    "level_db": -18.5,
    "active": true
  },
  "chromecast": {
    "enabled": true,
    "connected": false,
    "device_name": null,
    "level_db": 0,
    "active": false
  },
  "dante": {
    "enabled": false,
    "connected": false,
    "level_db": 0,
    "active": false
  }
}
```

### Control Mix Mode
```bash
# Set to mix mode (both play)
curl -X POST http://localhost:8080/mixer/mode -d '{"mode":"mix"}'

# Set to priority mode (highest priority wins)
curl -X POST http://localhost:8080/mixer/mode -d '{"mode":"priority"}'
```

### Adjust Source Levels
```bash
# Boost AirPlay by 6dB
curl -X POST http://localhost:8080/inputs/airplay/level -d '{"gain_db":6}'

# Mute Chromecast
curl -X POST http://localhost:8080/inputs/chromecast/level -d '{"mute":true}'
```

### Get Mix Statistics
```bash
curl http://localhost:8080/mixer/stats
```

---

## Troubleshooting

### AirPlay Not Appearing

**Problem:** iPhone doesn't see DanteStreamer in AirPlay menu.

**Solution:**
1. Check Shairport is running:
   ```bash
   docker exec dantestreamer ps aux | grep shairport
   ```

2. Restart service:
   ```bash
   docker-compose restart dantestreamer
   ```

3. Verify firewall allows UDP 5000:
   ```bash
   docker exec dantestreamer netstat -un | grep 5000
   ```

4. Check logs:
   ```bash
   docker logs dantestreamer | grep -i airplay
   tail -f logs/shairport.log
   ```

### Chromecast Not Finding Device

**Problem:** Android doesn't see DanteStreamer in Cast menu.

**Solution:**
1. Verify Snapserver is running:
   ```bash
   docker exec dantestreamer ps aux | grep snapserver
   ```

2. Check mDNS (device discovery):
   ```bash
   docker exec dantestreamer avahi-browse -a | grep -i dante
   ```

3. Restart Avahi:
   ```bash
   docker-compose restart dantestreamer
   ```

4. Check logs:
   ```bash
   docker logs dantestreamer | grep -i snapcast
   tail -f logs/snapserver.log
   ```

### Audio Not Flowing to Dante

**Problem:** AirPlay/Chromecast playing but nothing on Dante network.

**Solution:**
1. Check input levels:
   ```bash
   curl http://localhost:8080/inputs/status
   ```
   - If `level_db: 0` or very low, no audio is present.

2. Verify ALSA mixer is working:
   ```bash
   docker exec dantestreamer alsamixer
   ```

3. Check Virgil status:
   ```bash
   curl http://localhost:8080/status
   ```
   - Ensure `enabled: true` and `clock_locked: true`

4. Verify Dante routes in Dante Controller:
   - Is DanteStreamer's transmit channel subscribed?
   - Is receiver listening?

### Multiple Sources Playing But Too Loud

**Problem:** Mix mode but levels are clipping.

**Solution:**
1. Reduce individual source gains:
   ```bash
   curl -X POST http://localhost:8080/inputs/airplay/level -d '{"gain_db":-6}'
   curl -X POST http://localhost:8080/inputs/chromecast/level -d '{"gain_db":-6}'
   ```

2. Or switch to priority mode (only one at a time):
   ```bash
   curl -X POST http://localhost:8080/mixer/mode -d '{"mode":"priority"}'
   ```

### Latency Too High

**Problem:** Noticeable delay between AirPlay play and Dante output.

**Solution:**
1. Reduce buffers (but risk dropouts):
   ```toml
   [mixer]
   buffer_size = 2048   # Smaller = lower latency
   period_size = 512
   ```

2. Reduce Dante transmit latency:
   ```toml
   [network]
   tx_latency_us = 1000  # 1ms (minimum)
   ```

3. Use wired Ethernet (not Wi-Fi) for AirPlay source device.

---

## Performance Tips

1. **Wired network:** Use Ethernet for DanteStreamer container
2. **Dedicated CPU core:** Set `cpu_affinity` to avoid context switching
3. **Real-time priority:** Enable `use_realtime = true` (already on by default)
4. **Monitor dropouts:** Check `/var/log/dantestreamer/dropouts.log`
5. **Adjust buffers:** Smaller = lower latency, larger = more resilient

---

## Limitations & Gotchas

1. **Sample rate:** All sources must match (default 48 kHz)
   - AirPlay rescales automatically
   - Chromecast rescales automatically
   - No manual setting needed

2. **Channels:** Output is mono/stereo mix
   - If Dante output is 8 channels, left/right repeated
   - Use Dante Controller to route to specific channels

3. **Lip sync:** AirPlay has ~100–200 ms latency
   - Chromecast has ~200–500 ms latency
   - Audio will not sync with video for video calls
   - Use `crossfade` mode to minimize clicks

4. **DRM audio:** AirPlay from Apple Music, Spotify may not work
   - Depends on device DRM settings
   - Works with local music, podcasts, calls

---

## Next Steps

- Tune buffers and latency for your environment
- Test with multiple simultaneous sources
- Monitor CPU load under peak load
- Set up logging & alerting for production

