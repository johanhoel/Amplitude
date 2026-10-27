# Home Deck

The home's dashboard system: the panels and backend (Home Deck), the configuration UI (Studio), boards, the camera panel,
the Android app, the camera feed service, the edge proxy config and the friend edition.

| Folder | What | Lives on |
|---|---|---|
| `server/` | Home Deck backend (`homedeck/`), settings (`homedeck.toml`), every page (`www/`) | CT 106 `.52` `/opt/panel-wrapper` |
| `services/camwatch-feed/` | read-only camera feed (visits, thumbnails, video) | CT 102 `.81` `/opt/camwatch-feed` |
| `infra/` | edge nginx site (`:8126`), `homedeck-apply`, `homedeck-onboard`, the systemd units | `.40`, `.52` |
| `onboard/` | setup wizard for fresh installs: network scan, suggestions, writes `homedeck.toml` (`install.sh` installs it with the generic edition) | `/opt/homedeck-onboard` |
| `app/` | Android app + Docker builder (`build.sh`, `publish.sh`) | builds here, APK to `.52` `www/app/` |
| `friend/` | friend edition kit (`homedeck.sh` one-liner) | published on winrepo `.41` |
| `docs/` | Studio handbook | |
| `tools/`, `tests/` | pull-live, deploy, staging, check; Playwright smoke test | |

## Screenshots

| | |
|---|---|
| ![Start](docs/screenshots/start.jpg)<br>**Start**: the wall home: who's home, front door, lights, weather, next bus, now playing | ![Control](docs/screenshots/control.jpg)<br>**Control**: every switch in the house, speakers and media |
| ![Rooms](docs/screenshots/rooms.jpg)<br>**Rooms**: all lights, room by room | ![Media](docs/screenshots/media.jpg)<br>**Media**: Sonos, Spotify and the Apple TV remote |
| ![Ambient](docs/screenshots/ambient.jpg)<br>**Ambient**: night-time clock with door and camera-alert status | ![Boards](docs/screenshots/boards.jpg)<br>**Boards**: your own dashboards, built from modules |
| ![Lab panel](docs/screenshots/labpanel.jpg)<br>**Lab panel**: every server and service at a glance | ![Local AI](docs/screenshots/localai.jpg)<br>**Local AI**: wake the PC, load and unload its language models, open OpenCode, Claude Code or video-use on the PC |
| ![Local AI chats](docs/screenshots/localai-chat.jpg)<br>**Local AI chats**: saved chats; an answer keeps going on Home Deck when the page closes | |

| Phone: Remote | Phone: Family info | Phone: Local AI | Phone: Local AI chat |
|---|---|---|---|
| <img src="docs/screenshots/phone-remote.jpg" width="300"> | <img src="docs/screenshots/phone-familyinfo.jpg" width="300"> | <img src="docs/screenshots/phone-localai.jpg" width="300"> | <img src="docs/screenshots/phone-localai-chat.jpg" width="300"> |

## Fresh install and setup wizard

A fresh install knows nothing about any house: it installs the generic edition (`friend/src`, the same as the
friend kit) and a setup wizard. On a new Debian or Ubuntu machine, from a checkout of this folder:

```bash
sudo ./install.sh
```

It starts the panels and prints the **setup wizard** address (`http://<machine>:8089`) and a one-time setup code.
The wizard:

1. scans the network (Home Assistant, Pi-hole, Proxmox, cameras and recorders, Sonos, Google Cast, Apple TV,
   Dante speakers, routers). It only asks devices what they are; nothing is changed.
2. connects Home Assistant (paste a long-lived token). Rooms, lights, people, players, the lock and the weather then
   come from Home Assistant by themselves.
3. suggests the rest for you to confirm: which players and people to show, the door lock and weather, and status dots
   on Start for the routers, servers and recorders it found.
4. shows the exact lines of `homedeck.toml` that change, saves (old copy kept), restarts with automatic rollback,
   and switches itself off.

Run it again any time with `sudo homedeck-onboard`. Running `install.sh` again updates the code and keeps
settings, token and layouts.

| | |
|---|---|
| ![Scan](docs/screenshots/onboard-scan.jpg)<br>**Scan**: what was found on the network | ![Home Assistant](docs/screenshots/onboard-ha.jpg)<br>**Home Assistant**: address found by the scan, token, connect |
| ![Home](docs/screenshots/onboard-home.jpg)<br>**Home**: door lock and weather, or automatic | ![Media](docs/screenshots/onboard-media.jpg)<br>**Media**: which players to show; speakers found on the network |
| ![Network](docs/screenshots/onboard-network.jpg)<br>**Network**: status dots for routers, servers and recorders | ![Review](docs/screenshots/onboard-review.jpg)<br>**Review**: the exact settings lines that change |

## Daily use

```bash
tools/pull-live.sh     # bring anything changed directly on the server into git (then commit it)
tools/staging.sh       # run this repo's Home Deck on :8099 with throw-away state
tools/check.sh         # compile + settings check (+ smoke test of every page when staging runs)
tools/deploy.sh        # the only way to production: refuses if live was edited by hand, rolls back on failure
```

Never in git (see `.gitignore`): `secrets.json`, the app signing key (`app/signing`, kept in `~/homedeck-app/signing`), build output.
