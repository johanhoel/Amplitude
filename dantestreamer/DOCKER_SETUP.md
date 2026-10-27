# Docker Setup for Dante Player

Run Virgil + Dante Player in containerized environments for development and testing.

---

## Quick Start

### Build Image
```bash
cd /home/user/avvideo
docker build -t dante-player:latest .
```

### Single Container (Dante Player Only)
```bash
docker run -it --rm \
  --net=host \
  --cap-add=NET_RAW \
  --cap-add=SYS_ADMIN \
  -v $(pwd)/config/virgil-player.conf:/app/virgil.conf \
  -v $(pwd)/output:/app/output \
  -e DANTE_PLAYER_LOG=debug \
  dante-player:latest
```

### Two-Container Setup (Source + Player)
```bash
docker-compose up -d
```

**Verify:**
```bash
docker-compose ps
docker logs dante-source
docker logs dante-player
```

**Stop:**
```bash
docker-compose down
```

---

## What's in the Image

- **Base:** Debian Bookworm (slim)
- **Pre-built:** Virgil daemon + control tools
- **ALSA plugin:** For Linux audio
- **Size:** ~500 MB (optimized with multi-stage build)

**Ports exposed:**
- UDP 319/320 (PTP)
- UDP 5353 (mDNS)
- TCP 4440, 4455, 8700, 8800 (Dante control)
- TCP 8080 (HTTP control API)

---

## Configuration

### Edit Config Files

**For source (Dante audio generator):**
```bash
vim config/virgil-source.conf
```

**For player (Dante audio receiver):**
```bash
vim config/virgil-player.conf
```

Key settings:
```toml
[device]
name = "MyPlayer"          # Device name in Dante Controller
enabled = true

[network]
interface = "eth0"         # Network adapter (auto-detect if empty)
tx_latency_us = 4000       # Transmit ahead (milliseconds)
latency_us = 4000          # Receive buffer depth

[ptp]
master_capable = true      # Only on ONE device!

[audio]
sample_rate = 48000
channels = 8
```

### Auto-Detection

Leave `interface` empty in config for auto-detection:
```toml
[network]
interface = ""             # Auto-detect first Dante-capable adapter
```

---

## Testing Scenarios

### Scenario 1: Two Virgil Containers on Same Host
```bash
docker-compose up -d
```

Both containers:
- Share host network (`--net=host`)
- See each other's Dante devices
- Can route audio between them
- Logs in `./logs/`

**Verify connectivity:**
```bash
docker exec dante-source curl http://localhost:8701/status
docker exec dante-player curl http://localhost:8702/status
```

### Scenario 2: Single Player Container
```bash
docker run -it --rm \
  --net=host \
  --cap-add=NET_RAW \
  --cap-add=SYS_ADMIN \
  -v $(pwd)/config/virgil-player.conf:/app/virgil.conf \
  -v $(pwd)/output:/app/output \
  dante-player:latest
```

Then route audio to it from:
- Another Virgil instance (on host or another container)
- Real Dante device on network
- Dante dongle

### Scenario 3: Expose API to Other Machines
```bash
docker run -d \
  --net=host \
  --cap-add=NET_RAW \
  --cap-add=SYS_ADMIN \
  -v $(pwd)/config/virgil-player.conf:/app/virgil.conf \
  -v $(pwd)/output:/app/output \
  -p 8080:8080 \
  --name dante-player \
  dante-player:latest
```

Access from remote machine:
```bash
curl http://<container-host>:8080/status
```

---

## Networking Modes

### `--net=host` (Recommended for Dante)
- Containers share host's network namespace
- Can access all host adapters
- No NAT overhead
- Dante networking works seamlessly

### `--net=bridge` (Isolated Network)
- ❌ **Do NOT use for Dante**
- Multicast + UDP 319/320 won't route correctly
- Only for non-Dante scenarios

---

## Volumes & Data

### Directories

```
avvideo/
├── config/                 # Config files (mounted read-only)
│   ├── virgil-source.conf
│   └── virgil-player.conf
├── output/                 # Audio output (read-write)
│   └── dante_stream.pcm   # Dante audio recorded to file
├── logs/                   # Application logs
│   ├── dante-source.log
│   └── dante-player.log
└── docker-compose.yml
```

**Persist data across restarts:**
```bash
docker-compose down
# Logs, output, config survive
docker-compose up -d
```

**Clean everything:**
```bash
docker-compose down -v
rm -rf logs output
```

---

## Troubleshooting

### Container Won't Start
```bash
docker logs dante-player
# Check for network interface errors or permission issues
```

### PTP Clock Not Syncing
```bash
docker exec dante-player curl http://localhost:8080/status | grep clock
```

If `"clock_locked": false`:
- Wait 10–30 seconds (PTP convergence time)
- Check `master_capable` setting (only ONE device should be true)
- Verify network connectivity between containers

### No Audio Flowing
```bash
# Check diagnostics
docker exec dante-player curl http://localhost:8080/diagnostics
```

**Common causes:**
- Dante source not running or enabled
- Channels not subscribed in Dante Controller
- Sample rate mismatch

### Permission Denied (Network)
```bash
# Make sure you're running with sudo or in docker group
sudo docker-compose up -d
# OR
sudo usermod -aG docker $USER
newgrp docker
docker-compose up -d
```

### Can't Find Network Interface
```bash
# Inside container:
docker exec dante-player ip addr show
docker exec dante-player ip route show
```

If no interfaces visible:
- Use `--net=host` (required)
- Verify `interface` setting in config matches output of `ip addr show`

---

## Production Deployment

### Multi-Stage Build
Current `Dockerfile` uses multi-stage build to reduce image size:
- Stage 1: Build Virgil (includes build tools)
- Stage 2: Runtime only (slim base, just binaries)

### Systemd Service (on Host)
```bash
[Unit]
Description=Dante Player Container
After=docker.service
Requires=docker.service

[Service]
Type=simple
Restart=always
RestartSec=10
ExecStart=docker run --rm \
  --net=host \
  --cap-add=NET_RAW \
  --cap-add=SYS_ADMIN \
  -v /etc/dante-player/virgil.conf:/app/virgil.conf \
  -v /var/log/dante-player:/app/logs \
  dante-player:latest

[Install]
WantedBy=multi-user.target
```

Save as `/etc/systemd/system/dante-player.service`, then:
```bash
sudo systemctl enable dante-player
sudo systemctl start dante-player
sudo systemctl status dante-player
```

### Kubernetes Deployment
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: dante-player
spec:
  replicas: 1
  selector:
    matchLabels:
      app: dante-player
  template:
    metadata:
      labels:
        app: dante-player
    spec:
      hostNetwork: true  # Required for Dante
      containers:
      - name: dante-player
        image: dante-player:latest
        securityContext:
          capabilities:
            add:
              - NET_RAW
              - SYS_ADMIN
        volumeMounts:
        - name: config
          mountPath: /app/virgil.conf
          subPath: virgil.conf
        - name: output
          mountPath: /app/output
        - name: logs
          mountPath: /app/logs
      volumes:
      - name: config
        configMap:
          name: dante-player-config
      - name: output
        emptyDir: {}
      - name: logs
        emptyDir: {}
```

---

## Building a Custom Image

### Add Your Custom Player Code
```dockerfile
# In Dockerfile, after COPY virgild:
COPY ./src/dante_player /app/dante_player
RUN cd /app/dante_player && make
CMD ["/app/dante_player", "-c", "/app/virgil.conf"]
```

### Add Python Dependencies
```dockerfile
RUN apt-get install -y python3 python3-pip && \
    pip3 install --no-cache-dir numpy scipy
```

### Use Different Base Image
```dockerfile
FROM ubuntu:22.04
# or
FROM alpine:latest  # Smaller, but no systemd
```

---

## Debugging Inside Container

### Shell Access
```bash
docker exec -it dante-player /bin/bash
```

### Check Network
```bash
docker exec dante-player ip addr show
docker exec dante-player netstat -un | grep -E "319|320|4440"
```

### Live Logs
```bash
docker logs -f dante-player
```

### Monitor Resources
```bash
docker stats dante-player
```

---

## Docker Compose Commands

```bash
# Start all services
docker-compose up -d

# View logs (all)
docker-compose logs -f

# View logs (specific service)
docker-compose logs -f dante-player

# Execute command in container
docker-compose exec dante-player bash

# Stop services
docker-compose stop

# Remove containers (keep volumes)
docker-compose down

# Remove everything (including volumes)
docker-compose down -v

# Rebuild image
docker-compose build --no-cache

# Restart service
docker-compose restart dante-player
```

---

## Next Steps

1. **Build:** `docker build -t dante-player:latest .`
2. **Test:** `docker-compose up -d`
3. **Verify:** `docker-compose logs dante-player`
4. **Route audio:** Use Dante Controller or HTTP API
5. **Check output:** `ls -la output/` (if file backend enabled)
6. **Deploy:** Use systemd or Kubernetes config above

---

## Notes

- **Dante requires UDP multicast** → Use `--net=host`
- **PTP needs CAP_NET_RAW** → Add `--cap-add=NET_RAW`
- **One master clock per network** → Only one container/device with `master_capable = true`
- **Logs survive** → Check `logs/` directory after container exits
- **Output persists** → Audio written to `output/` survives restart

