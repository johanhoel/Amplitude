# Home Deck

The home's dashboard system: the panels and backend (Home Deck), the configuration UI (Studio), boards, the camera panel,
the Android app, the camera feed service, the edge proxy config and the friend edition.

| Folder | What | Lives on |
|---|---|---|
| `server/` | Home Deck backend (`homedeck/`), settings (`homedeck.toml`), every page (`www/`) | CT 106 `.52` `/opt/panel-wrapper` |
| `services/camwatch-feed/` | read-only camera feed (visits, thumbnails, video) | CT 102 `.81` `/opt/camwatch-feed` |
| `infra/` | edge nginx site (`:8126`), `homedeck-apply`, the systemd unit | `.40`, `.52` |
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
| ![Lab panel](docs/screenshots/labpanel.jpg)<br>**Lab panel**: every server and service at a glance | |

| Phone: Remote | Phone: Family info |
|---|---|
| <img src="docs/screenshots/phone-remote.jpg" width="300"> | <img src="docs/screenshots/phone-familyinfo.jpg" width="300"> |

## Daily use

```bash
tools/pull-live.sh     # bring anything changed directly on the server into git (then commit it)
tools/staging.sh       # run this repo's Home Deck on :8099 with throw-away state
tools/check.sh         # compile + settings check (+ smoke test of every page when staging runs)
tools/deploy.sh        # the only way to production: refuses if live was edited by hand, rolls back on failure
```

Never in git (see `.gitignore`): `secrets.json`, the app signing key (`app/signing`, kept in `~/homedeck-app/signing`), build output.
