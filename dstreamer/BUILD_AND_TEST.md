# Build and test DStreamer

How the image is built, how to change it, and how to check a change works
before calling it done. Install and day-to-day use are in the
[README](README.md).

## How the image is built

The `Dockerfile` has two stages:

1. **Builder** (`rust:1-bookworm`): clones the latest `main` of
   [Virgil](https://github.com/Audbol/virgil-virtual-soundcard) and builds
   it with CMake. Virgil's Dante side, Inferno, is Rust, which is why the
   builder starts from a Rust image. Only the daemon (`virgild`) and the ALSA
   plugin (`libasound_module_pcm_virgil.so`) are built; the GTK control app
   and the tests are switched off.
2. **Runtime** (`debian:bookworm-slim`): Shairport Sync, Avahi, D-Bus, ALSA
   tools and the two Virgil files. Both stages use Debian 12 (bookworm), so
   the binaries match the runtime's C library.

The builder doesn't pin a Virgil version, so a rebuild picks up whatever is
on Virgil's `main` that day (0.8.2 on 2026-10-27). To pin it, add
`--branch <tag>` to the `git clone` line.

At start, `docker-entrypoint.sh` checks the names from `.env`, writes them
into `data/virgil.conf` and a copy of the Shairport Sync config, then starts
D-Bus, Avahi, Virgil and Shairport Sync, in that order. Shairport Sync has
to start after Virgil, because the ALSA `virgil` device only works while
Virgil runs.

## Build and change

```bash
docker compose build                 # first build: a few minutes (Rust and C++)
docker compose up -d --build         # rebuild and restart after a change
docker builder prune -af             # free the build cache (about 3 GB)
```

Which change needs what:

| Changed | Run |
|---|---|
| `.env` (names) | `docker compose up -d` |
| `data/virgil.conf` | `docker compose restart dstreamer` |
| `config/*` templates, `docker-compose.yml` | `docker compose up -d` |
| `Dockerfile`, `docker-entrypoint.sh` | `docker compose up -d --build` |

Shell scripts, the Dockerfile, compose files, config and `.env*` keep LF
line endings through the repo's `.gitattributes`, so a checkout on Windows
still runs in the Linux container. Before building, run `bash -n
docker-entrypoint.sh` to catch syntax errors.

## Test a change

Run these on the DStreamer host after `docker compose up -d`.

**1. Healthy and on the Dante clock.** Give it up to 30 seconds:

```bash
docker compose ps        # "healthy"
curl -s http://127.0.0.1:8480/api/status | python3 -c \
  "import json,sys; d=json.load(sys.stdin); print(d['device']['name'], d['clock']['state'], d['tx_names'][:2])"
```

Expect the name from `.env`, `ptp-locked`, and the channel names.

**2. AirPlay is advertised** under the name from `.env`. This lists every
AirPlay device on the network; look for yours with the host's address:

```bash
docker exec dstreamer avahi-browse -rtp _raop._tcp | grep "^=;.*IPv4" | cut -d";" -f4,8
```

**3. Audio reaches Dante.** Play a test tone into the `virgil` device and
read the transmit meters while it plays. The tone goes to Dante transmit 1
and 2, so only subscribed speakers play it.

```bash
docker exec -d dstreamer timeout 20 speaker-test -D virgil -c 2 -r 48000 -t sine -f 440 -l 0
sleep 3; curl -s http://127.0.0.1:8480/api/status | python3 -c \
  "import json,sys; print(json.load(sys.stdin)['meters']['tx'])"
```

A value above 0 on channel 1 or 2 means the path from ALSA to Dante works.

**4. Names change.** For changes to naming, set a test name in `.env`, run
`docker compose up -d`, repeat checks 1 and 2, then set it back.

**5. A real phone.** AirPlay from an iPhone to DStreamer, with transmit
1 and 2 subscribed to a speaker in Dante Controller.

## Screenshots

The repo rule (see `../AGENTS.md`) asks for a screenshot of every feature,
updated when a feature changes. `tools/screenshots.py` captures the panel
into `docs/screenshots/`: status, meters, diagnostics, routing, settings
and the phone view. It needs Playwright for Python, Google Chrome, and the
panel on `http://localhost:8480/`; its first lines say how to tunnel there.
Start the test tone from check 3 first, so the meters show levels.
