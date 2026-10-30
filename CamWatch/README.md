<p align="center"><img src="app/static/logo-wordmark.svg" alt="camwatch" width="460"></p>

# CamWatch

Self-hosted camera service for up to four RTSP cameras. It records events with
pre-roll, finds people and vehicles with YOLOv8, pushes alerts with a snapshot,
identifies faces offline against your own photos, reads number plates and keeps
a "who came and when" log.

It runs as a Docker Compose stack on a small Debian VM or Proxmox LXC, with a
web UI and Home Assistant integration. Everything stays on your LAN.

> **Maintainers / LLMs: read [HANDOVER.md](HANDOVER.md)**: architecture, data formats, every setting, operations and known issues.

## Screenshots

`python dev/screenshots.py` takes these screenshots from demo pictures. They show no real camera footage.

| | |
|---|---|
| ![Dashboard](docs/screenshots/dashboard.jpg)<br>**Dashboard**: shows a summary of today, the live cameras and a tile for every page. | ![Clips](docs/screenshots/clips.jpg)<br>**Clips**: lists the clips of each day on a timeline. You can filter and tag the clips. *Select* downloads or deletes several clips at once. |
| ![Clip](docs/screenshots/clip.jpg)<br>**Clip**: plays one clip. *Play all* plays every camera in the same visit. You can name the faces. | ![Live](docs/screenshots/live.jpg)<br>**Live**: shows every camera live. A button tests the whole chain from camera to phone alert. |
| ![Zones](docs/screenshots/zones.jpg)<br>**Zones**: you draw the areas that start, ignore or mark activity for each camera. | ![Report](docs/screenshots/report.jpg)<br>**Report**: counts visits per day and per hour. A map shows where people walk most often. |
| ![Settings](docs/screenshots/settings.jpg)<br>**Settings**: shows the sections in pairs, side by side on a wide screen. | ![Request a feature](docs/screenshots/requests.jpg)<br>**Request a feature**: sends your idea to GitHub as an issue and shows whether it is done. |
| ![Strangers](docs/screenshots/strangers.jpg)<br>**Strangers**: groups unknown faces that come back. You name each person once. | ![Cameras](docs/screenshots/settings-cameras.jpg)<br>**Settings, cameras**: holds up to 4 cameras. *Find* searches your network for cameras. |
| ![Off-site](docs/screenshots/settings-offsite.jpg)<br>**Settings, off-site copies**: copies clips to iCloud, Google Drive or another place. Home Assistant settings follow below. | ![Updates](docs/screenshots/settings-updates.jpg)<br>**Settings, updates**: shows the running version. *Update now* installs a newer version from GitHub. |
| ![Storage](docs/screenshots/settings-storage.jpg)<br>**Settings, storage**: sets how long clips stay, and moves the recordings to another disk or a network share. | ![Studio](docs/screenshots/studio.jpg)<br>**Studio**: the console. *Dashboard* chooses the cards camwatch shows you, in your order, and the page it opens on; *Cameras* and *Discover* set the cameras up, several VLANs at a time, as changes you apply together and can undo. |

| Phone: home | Phone: cameras | Phone: settings |
|---|---|---|
| <img src="docs/screenshots/phone-home.jpg" width="300"> | <img src="docs/screenshots/phone-wall.jpg" width="300"> | <img src="docs/screenshots/phone-settings.jpg" width="300"> |

## Features

- **Recording**: copies the camera stream without re-encoding into a rolling buffer; each event becomes one MP4 with pre-roll, plus snapshot and metadata.
- **Detection**: cheap pixel motion gates YOLOv8 (person, car, truck, motorcycle, bicycle, dog, cat, …); parked vehicles are ignored automatically; loitering alerts.
- **Zones** drawn in the web UI: ignore, trigger (alerts say "person at door"), house/street (arrived/left), parking (car arrived/left).
- **Alerts** via ntfy (server, topic and login set in Settings) with snapshot and **Open / Star / Snooze 1h** buttons; arm/disarm with schedule; snooze a camera; camera offline alerts; daily summary.
- **Several cameras** (up to 4), added in Settings with **Find** (network scan + ONVIF reads the stream addresses); a walk past several cameras is one visit with one push and *Play all*.
- **Unusual activity**: each camera learns when people, cars and animals normally appear; a visit at an unusual time or place gets an urgent push.
- **Faces**: offline matching of recorded clips against `photos/<Person>/`; tag faces in the UI to improve matching; automatic re-check when the library changes.
- **Number plates** of arriving/moving vehicles, known plates with names.
- **Presence log** in MariaDB: visits, who, direction, cars coming and going.
- **Dashboard** (`/dashboard`): today at a glance and a tile for every page.
- **Weekly report** (`/report`) with per-day/hour charts and a heatmap of where people walk; weekly push.
- **Packages**: draw a package zone on the doorstep to get "delivered" / "picked up" alerts.
- **Timelapse**: the whole day in a minute plus a highlights reel of every event, built nightly.
- **Share a blurred copy** of a clip (faces and plates pixelated, sound removed).
- **Search** recordings by description ("white van", "person with a dog") with a local CLIP model.
- **Recurring strangers**: unknown faces seen in several clips, grouped so you can name them once.
- **Quiet household alerts**: known faces get a quiet push, strangers the loud one.
- **Optional no-password access on the LAN** (Settings).
- **Wall view** (`/view`): a phone/tablet page with live picture, filter chips and a swipeable full-screen player.
- **Phone home** (`/m`): a page made for phones - what needs attention (camera offline, unusual visits, packages, strangers, off-site failing, snoozes), swipeable live cameras with *Snooze 1h*, today's numbers and recent visits, arm/disarm, a bottom tab bar. The installed app opens here.
- **Phone app**: add camwatch to the home screen (manifest + icons; full app install on Android needs HTTPS).
- **Web UI**: clips with timeline and filters, player, stars (never auto-deleted), people & photo library, plates, zones editor, settings, presence log, live view, end-to-end test button, Home Assistant guide.
- **Home Assistant**: MQTT auto-discovery (sensors, armed switch, snapshot camera, event entity) and/or webhook.
- **Off-site storage** (Settings): copies to iCloud Drive, Google Drive, OneDrive, Dropbox, Backblaze B2, S3 or a NAS (SFTP/SMB) via rclone; encrypted by default; alarms uploaded within a minute, the rest nightly; retention and speed limit.
- **Optional extras**: read-only JSON feed for dashboard panels; copy starred clips to iCloud Drive via a Windows share.

## Install

Prerequisites: Debian 12/13 VM or LXC (Proxmox LXC: `pct set <CTID> --features nesting=1,keyctl=1`), a data disk for recordings, MariaDB on the host for the presence log:

```bash
sudo apt install mariadb-server
sudo mariadb -e "CREATE DATABASE camwatch; CREATE USER 'camwatch'@'localhost' IDENTIFIED BY 'choose-a-password'; GRANT ALL ON camwatch.* TO 'camwatch'@'localhost';"
```

Then:

```bash
git clone https://github.com/johanhoel/amplitude.git && cd amplitude/CamWatch
cp .env.example .env        # set RTSP_URL, NTFY_TOPIC, TZ, paths, WEB_BASE_URL, WEB_PASSWORD, DB_PASSWORD
sudo ./deploy.sh            # installs Docker if needed, copies to /opt/camwatch, builds and starts
```

Open `http://<host>:8080`, subscribe to your `NTFY_TOPIC` in the ntfy app, then on the **Live** page press **Simulate motion** to test the whole chain (push → clip → clip page).

On Windows or a Mac, CamWatch runs in a small Linux system on the same computer: [docs/install-windows-mac.md](docs/install-windows-mac.md).

## Use

- **People**: add 3–10 clear face photos per person; faces in clips can be assigned with "This is them".
- **Zones**: draw ignore areas (trees, street) and optional trigger/house/street/parking zones on the live picture.
- **Plates**: save known plates with a name; known cars get quiet pushes.
- **Settings**: arm/disarm or schedule, loitering time. How long clips stay is under **Settings → Storage** (starred clips are kept forever, clips with identified people longer).
- **Home Assistant**: follow the **Home Assistant** page in the web UI; the MQTT broker (IP, user, password) and webhook are entered under **Settings → Home Assistant**.

### More cameras

Up to 4 cameras: the first is in `.env`, the others are added on the web UI's **Settings → Cameras** (name, RTSP stream, optional detection substream, a *Test picture* button). They start within seconds, no restart needed. Each camera has its own recorder container and zones; clips, live view, heatmap, timelapse and the dashboard show all cameras with a picker.

### Updates

**Settings → Updates** checks GitHub for a newer CamWatch.
When it finds one, it shows an **Update now** button.
The button asks a helper on the server to install the new version.
`deploy.sh` installs this helper (`extras/install-updater.sh`, a systemd path unit).
The helper runs `extras/release.sh`.
That script backs up the running version and builds the new one.
When the new version does not start, the script puts the old version back.

The amplitude repository is public, so updates need no access key.
GitHub allows 60 update checks an hour without a key. CamWatch makes at most a few per check.

The access key is optional: a fine-grained token for this one repository.
Only the owner of the repository can make it.
Enter it under **Settings → Updates → Where updates come from**.
The guide [docs/update-key.md](docs/update-key.md) explains each step to make the key.
CamWatch shows the same guide: **Settings → Updates → How to make the key** (`/settings/update/key`).

### Storage

**Settings → Storage → Keep clips** sets how long clips stay and how much disk stays free.
The values in `.env` (`RETENTION_DAYS`, `RETENTION_KEEP_DAYS`, `MIN_FREE_GB`) only count until you save there.

**Where recordings go** moves the recordings to another folder, disk or network share (NFS or SMB).
The update helper on the server does the work: it copies, stops CamWatch, copies the newest clips, switches and starts.
When CamWatch does not start with the new place, the helper switches back. The old copy stays.
A network share goes into `/etc/fstab` under `/mnt/camwatch-net/`, and Docker waits for it at boot.
An unprivileged Proxmox container cannot connect to a share. Connect it on the Proxmox host and pass it in with `pct set`.
Settings shows the steps.

### GPU

CamWatch finds people, cars, number plates and faces with image models. By default these models run on the CPU.
**Settings → Image processing → Use the GPU when the server has one** moves the object, plate and search models to a GPU.
Each model switches the next time it runs, and recording does not stop.
The table below the switch shows what each part runs on.
When a GPU cannot run a model, that model stays on the CPU, and the table says so.
The face models always run on the CPU.

Measured on an Intel HD Graphics 630 (i7-8809G): object detection takes 68 ms per frame on the GPU, against 212 ms on the CPU.
On that GPU, OpenVINO cannot run the number plate detector, so plates stay on the CPU.

**Settings → GPU on the server** shows what the update helper found.
The helper scans the PCI bus, so it also finds a GPU in a virtual machine or a GPU without a driver.
It then shows the next step:

- An Intel GPU or an NVIDIA GPU that Docker can use: **Add GPU support** builds CamWatch again with it.
  This takes 5 to 15 minutes. When the new build does not start, the old build comes back.
- A Proxmox container: the `pct set` command for the Proxmox host, with the right `renderD` device.
- A virtual machine with only a virtual graphics card: the steps to pass a real GPU through.
- A GPU without a driver, or an NVIDIA GPU without the NVIDIA Container Toolkit: what to install.

An Intel GPU uses OpenVINO, and an NVIDIA GPU uses CUDA. CamWatch cannot use AMD GPUs yet.
By hand: set `CAMWATCH_GPU=intel` (or `nvidia`) in `.env`, and add `docker-compose.gpu-intel.yml`
(or `docker-compose.gpu-nvidia.yml`) to `COMPOSE_FILE`.

### Home Deck

CamWatch can link with the Studio in Home Deck (`panels/` in the amplitude repository). The link is optional.

1. In CamWatch, open **Settings → Home Deck** and click **Make a link key**.
2. In the Studio, open **Overview → CamWatch**. Enter CamWatch's address and the key, and click **Link**.

Home Deck then calls `POST /api/link/sync` about once a minute. It sends its network devices and its people.
CamWatch answers with its cameras and the people in its face library. The key opens this one route only.

- **The Studio** lists the cameras under Devices, source CamWatch. Add one and switch on Watch.
  Home Deck then sends a notice when the camera stops sending pictures.
- **The Studio's People page** shows when each person was last seen by a camera.
- **CamWatch's camera finder** names each camera with Home Deck's name for it.
  It also lists devices from camera makers that the scan missed.
- **CamWatch's People page** lists Home Deck's people who have no photos yet.

### Feature requests

Every page has a **💡 Request a feature** link at the bottom.
A request becomes an issue in the GitHub repository from Settings → Updates.
Without an access key, GitHub opens with the request filled in.
You press **Submit new issue** there, with your own GitHub account.
With a key that has **Issues: Read and write**, CamWatch creates the issue itself.
It then gets the labels `feature request` and `camwatch`.
CamWatch keeps every request in `DATA_PATH/feature_requests.jsonl`.
When GitHub refuses a request, **Send again** retries it.

## How it is built

Six containers, one Compose stack:

| Container | What it does |
|---|---|
| `camwatch-recorder` | Always on: RTSP → buffer, motion/objects, events, alerts, plates, parking, HA, retention |
| `camwatch-facematch` | Offline face identification of finished clips |
| `camwatch-presence` | Presence log in MariaDB, daily summary |
| `camwatch-webui` | Web UI on port 8080 |
| `camwatch-offsite` | Off-site uploads (idle until set up in Settings) |
| `camwatch-recorder-2..4` | Camera slots 2-4; idle until a camera is added in Settings |

### Optional extras (host services)

```bash
# dashboard feed (needs python3-pil); edit FEED_ALLOW in the unit first
sudo cp extras/systemd/camwatch-feed.service /etc/systemd/system/ && sudo systemctl enable --now camwatch-feed
# nightly database dump into DATA_PATH/db-backup (include DATA_PATH and PHOTOS_PATH in your host backup)
sudo cp extras/systemd/camwatch-db-backup.* /etc/systemd/system/ && sudo systemctl enable --now camwatch-db-backup.timer
# starred clips -> iCloud Drive (needs smbclient; set ICLOUD_SHARE / ICLOUD_CRED in .env)
sudo cp extras/systemd/icloud-sync.* /etc/systemd/system/ && sudo systemctl enable --now icloud-sync.timer
```

### Operations

```bash
cd /opt/camwatch
sudo docker compose ps
sudo docker compose logs -f recorder
sudo docker compose up -d --build && sudo docker builder prune -af   # after code changes
```

## Notes

### Privacy

Face recognition and plate reading process other people's personal data. Point the camera at your own property, keep retention short, protect the web UI with `WEB_PASSWORD`, keep it off the internet (use a VPN), and never commit `.env`.

### Licences

Object detection uses Ultralytics YOLOv8 (AGPL-3.0); face models from the OpenCV model zoo (Apache-2.0); plate models from fast-alpr (MIT).
