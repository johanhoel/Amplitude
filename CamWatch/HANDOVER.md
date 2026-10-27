# camwatch: technical documentation

Self-hosted home camera service: an RTSP camera feeds motion and object detection, push alerts (ntfy), recordings on disk, offline face identification against a photo library, number-plate reading, a presence log ("who came and when"), a web UI, and Home Assistant integration.

This document is for whoever maintains or extends the service (human or LLM): what exists, how it fits together, where data lives, how to operate and change it, and what is fragile. Setup steps are in [README.md](README.md). Secrets never go in the repository; they live in `/opt/camwatch/.env` (mode 600, root only).

---

## 1. Requirements

| Item | Notes |
|---|---|
| Host | Debian 12/13 VM or LXC container. In Proxmox LXC enable `nesting=1,keyctl=1`. 4 vCPU / 4 GB RAM is enough for one 4 MP camera with YOLOv8s. |
| Disk | Root disk ≥ 16 GB (the image is ~1.5 GB; builds need headroom). A separate data disk for recordings is recommended. |
| Runtime | Docker CE + Compose plugin (`deploy.sh` installs them). |
| Database | MariaDB on the host for the presence log, reached through its socket `/run/mysqld` (database + user `camwatch`, password `DB_PASSWORD`). |
| Camera | Any RTSP camera (H.264/H.265). Two connections are opened: ffmpeg for recording and OpenCV for detection. An optional low-resolution substream (`DETECT_URL`) reduces CPU. |
| Push | ntfy (ntfy.sh or self-hosted). |

---

## 2. Architecture

```
                     ┌──────────────────────────── camwatch-recorder ───────────────────────────────┐
 RTSP camera ──┬───► ffmpeg (copy, no re-encode) ─► 2 s .mkv segments in /buffer (rolling)         │
               │                                                                                     │
               └───► OpenCV decode @5 fps ─► pixel motion ─► YOLOv8 (only while moving) ──┐        │
                                              ▲ zones/arming from /data/settings.json      │        │
                                              │                                            ▼        │
                     live frame ─► /live/frame.jpg (only while someone watches)    event start:     │
                     simulate button ◄─ /live/simulate_motion                      snapshot, ntfy,  │
                                                                                   HA event/MQTT    │
                     number plates (fast-alpr) on moving / parking vehicles ───► plate push / HA    │
                     event end ─► Finalizer stitches segments ─► /recordings/YYYY-MM-DD/<stem>.mp4  │
                     Housekeeper: trims buffer, retention / free-space pruning                      │
                     └──────────────────────────────────────────────────────────────────────────────┘
                                                        │ finished .mp4 files
                     ┌──────────── camwatch-facematch ──▼────────────────────────────────────────────┐
                     │ new clips ─► YuNet face detect + SFace embeddings ─► compare with             │
                     │ /photos/<Person>/* ─► <stem>.faces.json, crops, sightings, ntfy, HA events     │
                     │ library change ─► debounced re-check of all clips that contain faces          │
                     └───────────────────────────────────────────────────────────────────────────────┘
                     ┌──────────── camwatch-presence ────────────────────────────────────────────────┐
                     │ scans clip sidecars ─► MariaDB visits/visitors, arrived/left from tracks,      │
                     │ daily summary push                                                             │
                     └───────────────────────────────────────────────────────────────────────────────┘
                     ┌──────────── camwatch-webui (Flask + waitress, :8080) ─────────────────────────┐
                     │ clips/timeline/filters, player, star/delete, manual face tagging, people &    │
                     │ photo library, plates, zones editor, settings, presence log, live view,       │
                     │ simulate motion, Home Assistant setup guide                                   │
                     └───────────────────────────────────────────────────────────────────────────────┘
```

### Containers (`docker-compose.yml`)

All four run the same image `camwatch:latest`. **Only `recorder` has `build: .`**; the others use `image: camwatch:latest` + `pull_policy: never`, so the image is built once (building it once per service in parallel can fill a small root disk).

| Service | Container | Command | Mounts | Healthcheck |
|---|---|---|---|---|
| recorder | camwatch-recorder | `python recorder.py` | recordings (rw), `buffer` volume, `live` volume, data (rw) | `/tmp/healthy` (frames arriving) **and** `/tmp/recording` (video being written) touched within 2 min |
| facematch | camwatch-facematch | `python facematch.py` | recordings (rw), photos (**ro**), data (rw) | none |
| presence | camwatch-presence | `python presence.py` | recordings (**ro**), data (**ro**), `/run/mysqld` | `/tmp/healthy` touched within 2 min = scan loop alive |
| webui | camwatch-webui | `python webui.py` | recordings, photos, data (rw), `live` volume, `/run/mysqld`; port `${WEB_PORT:-8080}:8080` | HTTP GET `/healthz` |

Named volumes: `camwatch_buffer` (rolling segments; on the root disk on purpose so the data disk isn't written constantly) and `camwatch_live` (latest frame + simulate trigger file).

Host paths come from `.env`: `RECORDINGS_PATH` → `/recordings`, `PHOTOS_PATH` → `/photos`, `DATA_PATH` → `/data`.

### Multiple cameras (up to 4)

- Four fixed slots in `docker-compose.yml`: `recorder` (slot 1) and `recorder-2..4`, each with `CAMERA_SLOT` and its own buffer volume, all running `camslot.py`. The launcher reads `settings.camera_slots()` (slot 1 = `CAMERA_NAME`/`RTSP_URL` from `.env`, URLs overridable; slots 2-4 = `cameras` in `settings.json`), sets `CAMERA_NAME`, `RTSP_URL`, `DETECT_URL`, `PRIMARY_CAMERA` (+ `PRUNE_RECORDINGS=false` for 2-4) and execs `recorder.py`. An empty slot waits and touches `/tmp/idle`, which the healthcheck accepts.
- The recorder compares `settings.camera_key()` for its slot on every settings change; when it differs it exits (`os._exit(0)`) once no event is open or being saved, and Docker's restart policy starts the launcher with the new settings. No Docker socket in any container.
- `settings.json` holds camera and MQTT passwords, so `settings.update()` writes it mode 600. The web UI only ever sends URLs with the password replaced by `••••••` (`mask_url`) and puts the stored password back on save/test (`unmask_url`). *Test picture* grabs one frame with ffmpeg (20 s timeout).
- Only the primary recorder prunes recordings (one pruner for the shared disk) and moves legacy timelapse frames.
- Each recorder writes `/live/<camera>/` (`frame.jpg`, `watching`, `simulate_motion`, `info.json` at start, `alive` every 10 s). The web UI lists the enabled cameras from settings; online = `alive` younger than 60 s.
- Clip stems are `<camera>_HHMMSS`; the sidecar has `"camera"`. `webui.camera_of(stem)` gets the camera from the stem.
- Zones in `settings.json` have an optional `"camera"`; no field = the primary camera (`settings.zones_for`). Saving zones for one camera keeps the others'.
- Timelapse frames are `/data/timelapse/frames/<camera>/<day>/`, videos `<day>-<camera>-timelapse.mp4` / `-highlights.mp4` (old names without camera = primary).
- Web: `?camera=` on `/live`, `/live.jpg`, `/live.mjpg`, `/zones`, `/`, `/api/visits`, `/api/days`, `/api/heatmap.jpg`; `/api/cameras`; `/api/status` has `cameras`. Unknown camera → 404.

### Host-side extras (`extras/`, optional, systemd)

| File | Purpose |
|---|---|
| `extras/feed/feed.py` + `extras/systemd/camwatch-feed.service` | Read-only JSON API of recent visits, thumbnails, face crops and videos for dashboard panels (port 8091). No login: only IPs in `FEED_ALLOW` get answers. Reads the recording sidecars directly. Needs `python3-pil`. |
| `extras/db-backup.sh` + `extras/systemd/camwatch-db-backup.{service,timer}` | Nightly (01:30) `mariadb-dump` of the presence database to `$DATA_PATH/db-backup/<db>-YYYY-MM-DD.sql.gz`, keeps `DB_BACKUP_KEEP_DAYS` (14). Puts a consistent copy inside the data folder, so a file-level / Proxmox backup of `DATA_PATH` (plus `PHOTOS_PATH`) is a complete backup. Restore: `gunzip -c <dump> \| mariadb`. Status push on failure. |
| `extras/icloud-sync.sh` + `extras/systemd/icloud-sync.{service,timer}` | Every 2 min copies newly **starred** clips to an SMB share that iCloud for Windows uploads (`ICLOUD_SHARE`, `ICLOUD_CRED` in `.env`). Each clip is sent once; failures retry and push a warning after 24 h. Needs `smbclient`. |

---

## 3. Source layout

```
├── HANDOVER.md          this file
├── README.md            setup and usage
├── deploy.sh            install Docker if missing, copy files to /opt/camwatch, build, start
├── Dockerfile           deps + face models (downloaded) + plate models (downloaded) + models/ + app/
├── docker-compose.yml
├── requirements.txt     opencv-python-headless, numpy, flask, waitress, onnxruntime, paho-mqtt, fast-alpr, PyMySQL
├── .env.example         documented configuration template (copy to .env)
├── models/
│   ├── yolov8s-coco.onnx   YOLOv8s, 80 COCO classes, exported with Ultralytics (opset 12, 640×640), default
│   ├── yolov8n-coco.onnx   YOLOv8n, same export, faster / less accurate
│   └── README.txt
├── app/
│   ├── common.py        env helpers, logging, ntfy client, retention/pruning, clip URLs, delete_event
│   ├── settings.py      runtime settings shared via /data/settings.json (arming, zones, loitering, known plates)
│   ├── recorder.py      live pipeline (segmenter, frame reader, motion, objects, events, parking, plates, HA, ntfy)
│   ├── objects.py       YOLOv8 ONNX object detector (onnxruntime)
│   ├── plates.py        number-plate reading (fast-alpr) + per-event tally + backfill CLI
│   ├── tracks.py        backfills <stem>.track.json (detection paths) for older clips
│   ├── facematch.py     offline face identification worker + CLI
│   ├── presence.py      presence log in MariaDB + daily summary
│   ├── homeassistant.py MQTT discovery/states/events + webhook
│   ├── webui.py         Flask app; HTML templates inline in TEMPLATES (DictLoader)
│   └── wallview.html    the /view page (plain HTML/JS, served as-is; `__ARMED__` is filled in)
└── extras/              optional host services (see above)
```

Models in the image:

| Model | Purpose | Source | Location |
|---|---|---|---|
| `face_detection_yunet_2023mar.onnx` | face detection | OpenCV model zoo (downloaded at build) | `/models` |
| `face_recognition_sface_2021dec.onnx` | 128-d face embeddings | OpenCV model zoo | `/models` |
| `yolov8s-coco.onnx` / `yolov8n-coco.onnx` | objects (person, car, …) | Ultralytics YOLOv8 exported to ONNX (`models/`) | `/models` |
| `yolo-v9-t-640-license-plates-end2end.onnx` | plate detection | fast-alpr / open-image-models (downloaded at build) | `/root/.cache/open-image-models/` |
| `cct_s_v2_global.onnx` | plate OCR | fast-plate-ocr (downloaded at build) | `/root/.cache/fast-plate-ocr/` |

Licenses: YOLOv8 (Ultralytics) is **AGPL-3.0**; YuNet/SFace Apache-2.0; fast-alpr and its models MIT. Keep the AGPL in mind before distributing.

YOLOv8s vs YOLOv8n: in a replay of ~1,300 frames, v8s found people in ~15 % more frames (partly hidden, IR night, frame edges) at ~175 ms vs ~65 ms per pass on a 4-core CPU. Switch with `OBJECT_MODEL`. `objects.py` also accepts person-only exports (5 output rows instead of 84).

---

## 4. The recorder (`app/recorder.py`)

Threads:

| Thread | Job |
|---|---|
| `Segmenter` | Keeps its `Popen` so the housekeeper can kill a hung ffmpeg. `ffmpeg -rtsp_transport tcp -timeout 10000000 -i RTSP_URL -map 0:v:0 [-map 0:a:0?] -c copy -f segment -segment_time 2 -segment_format matroska -reset_timestamps 1 -strftime 1 /buffer/%Y%m%d-%H%M%S.mkv`, restarted with backoff (2 to 60 s). Matroska because mpegts can't carry G.711 audio. |
| `FrameReader` | `cv2.VideoCapture(DETECT_URL)` with 15 s timeouts; `grab()`s every frame, `retrieve()`s at `DETECT_FPS`, so analysis uses the newest frame (no growing lag). Reconnects on failure. |
| `Finalizer` | Waits until the segment covering the event end is closed, concatenates the segments overlapping `[start - PRE_ROLL, end]` to `<stem>.mp4` (`-c:v copy -c:a aac -movflags +faststart`, `.mkv` fallback). Writes `.part` then renames (atomic for other services). Writes `<stem>.json`. |
| `Housekeeper` | Every 10 s: **recording watchdog** (no new buffer data for `RECORDING_STALL_SECONDS`, default 60 → status push + HA `recording_stalled`, kill ffmpeg so it restarts, retried every 2 × stall time; recovery → `recording_resumed`; touches `/tmp/recording` while healthy) and deletes unneeded buffer segments; every 10 min runs `prune_recordings()` (§7). |

Main loop (once per new frame, ~5/s):

1. **Settings reload** (every 2 s when `settings.json` changed): zones, arming, loitering, known plates; publishes `armed` to HA.
2. **Camera watchdog**: no frame for `OFFLINE_AFTER_SECONDS` → "offline" status push + HA `camera_offline` (also when disarmed); recovery → "back online".
3. **Live view**: if the web UI touched `/live/watching` within 10 s, write `/live/frame.jpg` (max 5/s).
4. **Simulate**: `/live/simulate_motion` → next 6 s count as detections (event marked `test`).
5. **Pixel motion** (`MotionDetector`): downscale to `DETECT_WIDTH`, grey + blur, running-average background, threshold, dilate, mask ignore zones. Changes > `MOTION_MAX_AREA` are lighting/IR switches (re-baseline). In `objects` mode a much lower gate (`MOTION_GATE_AREA`, default half of `OBJECT_MIN_AREA`) decides when YOLO looks, so small/distant people aren't missed; the HA `motion` sensor uses `MOTION_MIN_AREA`. With trigger zones, only boxes centred in one count.
6. **Object confirmation** (YOLO via onnxruntime): every `OBJECT_INTERVAL` while there is motion / an event / pending hits, and once a minute regardless (keeps the parked-vehicle tracker fresh). Filters: `OBJECT_CONFIDENCE`, `OBJECT_MIN_AREA`, box centre not in an ignore zone, per-class NMS, and with trigger zones the **bottom-centre** (feet/wheels) must be inside one.
7. **StationaryFilter**: non-person/animal detections matching an existing track (IoU ≥ 0.6) older than `STATIONARY_SECONDS` are dropped (parked cars). Vehicles present at startup count as parked. People and animals are never filtered.
8. **Event start** when `OBJECT_MIN_HITS` of the last `OBJECT_WINDOW` YOLO passes found something (or `MOTION_MIN_FRAMES` motion frames in `motion` mode). The clip name (`stem` = `<CAMERA_NAME>_HHMMSS[-n]`) is reserved immediately so pushes can link to the clip page before the clip exists. Snapshot `<stem>.jpg` written at once; push with the snapshot scaled to `NOTIFY_WIDTH` (if armed and outside `NOTIFY_COOLDOWN_SECONDS`; tests always push); HA event per newly seen label (and again when a label enters a new zone), HA snapshot + `last_event`.
9. **During the event**: loitering (continuous presence for `loiter_seconds`) → one urgent push + HA `loitering`; plates.
10. **Event end** after `POST_ROLL_SECONDS` without detections, or at `MAX_EVENT_SECONDS`.

**Packages** (`app/packages.py`, `PackageWatcher`): for zones of type `package`, the empty look is learned while no event runs; `PACKAGE_QUIET_SECONDS` after a visit with a person the zone is compared on colour (Lab a/b), surface texture and large local brightness changes (shadows, daylight and IR switches are rejected); a new object of `PACKAGE_MIN_AREA`..`PACKAGE_MAX_AREA` that is unchanged `PACKAGE_CONFIRM_SECONDS` later = delivered; after a later visit the zone looking empty again = picked up. Push with a before/now picture, HA `package_delivered` / `package_picked_up`, `<stem>.package-<kind>.jpg`, `packages` entry in `<stem>.json`, `/data/packages.jsonl`. Heuristic, validated on synthetic scenes only; tune with the `PACKAGE_*` settings.

**Number plates**: while a *moving* vehicle is detected, at most every `PLATE_INTERVAL`, fast-alpr reads the full frame; only plates inside a moving vehicle's box count (ignores parked cars). `PlateTally` confirms a plate after 2 identical reads or one with OCR confidence ≥ 0.97 and merges one-character variants; known plates match with Levenshtein ≤ 1 (5+ characters). Push (`PLATE_NOTIFY` all/unknown/none, known = low priority), HA `plate`, `last_plate`, `/data/plates.jsonl`, crops in `<stem>_plates/`.

**Parking zones** (`ParkingMonitor`): every `PARKING_CHECK_SECONDS` checks whether a vehicle's bottom-centre is inside each zone of type `parking` (ignore zones are *not* applied here). A change that holds `PARKING_CONFIRM_SECONDS` is a car `arrived` / `left`, added to the running event or starting one that begins 20 s before the change. On arrival the plate is read off the parked car and remembered for the departure. Stored in `<stem>.json` as `vehicles: [...]`; push + HA `vehicle_arrived` / `vehicle_left`. The first look after a restart only sets the state.

**Tracks**: the recorder writes `<stem>.track.json` (every detection's foot point over time, 0..1 coordinates, including up to 6 s before the event). `tracks.py` backfills older clips from the video.

---

## 5. Face matching (`app/facematch.py`)

- Every `FACE_SCAN_INTERVAL` picks clips without `<stem>.faces.json` older than `FACE_SETTLE_SECONDS` (`.part` files never). Respects `FACE_ACTIVE_HOURS`. Runs at `nice 10`.
- Samples `FACE_SAMPLE_FPS` frames per second of video, downscales to ≤ 1920 px, YuNet detection (score ≥ 0.85, size ≥ `FACE_MIN_SIZE`), SFace embedding, cosine similarity against the library; ≥ `FACE_MATCH_THRESHOLD` = known. Unknown faces are clustered (≥ 0.45 = same person) so one stranger gives one entry. Writes `<stem>.faces.json` and crops in `<stem>_faces/` (wiped on re-analysis).
- Reports: `sightings.jsonl`, push "Identified: …" (`FACE_NOTIFY_KNOWN`) / "Unknown person" (`FACE_NOTIFY_UNKNOWN`), HA `identified` / `unknown_face`, retained `last_identified`.
- **Library**: `/photos/<PersonName>/**/*.{jpg,jpeg,png,webp,bmp}`; embeddings cached in `/data/library_cache.json` by path + mtime + size (`emb: null` = no face found; shown on the People page). Reference photos are tried at widths 640, 1280, 1920: **close-up portraits only detect reliably at small widths.** The largest face in a photo is used.
- **Automatic re-check** when the library changes (`FACE_RECHECK_ON_LIBRARY_CHANGE`): after `FACE_RECHECK_DELAY` quiet seconds, clips with `faces_seen > 0` are re-analysed without pushes or HA events; sightings only for newly found people.
- Calibration seen in testing: genuine matches ~0.49 to 0.65, non-matches ≤ 0.38; matches against a reference crop taken from the same clip score ~0.98 (circular). Overhead/driveway cameras often see no usable face (back turned, too far, < 40 px).

CLI (`/opt/camwatch`):
```bash
sudo docker compose exec facematch python facematch.py --once            # pending clips now
sudo docker compose exec facematch python facematch.py --once --force    # everything (sends pushes!)
sudo docker compose exec facematch python facematch.py --file /recordings/<day>/<stem>.mp4
# quiet full re-run (stop the service first to avoid two workers)
sudo docker compose stop facematch
sudo docker compose run --rm -e FACE_NOTIFY_KNOWN=false -e FACE_NOTIFY_UNKNOWN=false -e FACE_SETTLE_SECONDS=0 \
     facematch python facematch.py --once --force
sudo docker compose start facematch
```

---

## 5c. Strangers, search, household alerts

- **Recurring strangers** (`app/strangers.py`, run by facematch every `STRANGER_EVERY` s or when `/data/strangers.refresh` exists): embeddings of all untagged unknown-face crops of the last `STRANGER_DAYS` days (cache `/data/stranger_cache.json`), single-linkage groups at cosine >= `STRANGER_SIMILARITY`, groups seen in 2+ clips written to `/data/strangers.json` with a "probably <name>" hint (library similarity >= `STRANGER_HINT`). Web UI `/strangers`: name a group (every clip tagged via `tag_face()`, first 5 crops into the library, which triggers the re-check) or hide it (`/data/strangers_hidden.json`).
- **Search** (`app/search.py`): facematch indexes up to `SEARCH_BATCH` new clips per pass, `SEARCH_FRAMES` CLIP ViT-B/32 image embeddings each (snapshot + frames from the video, `/data/search_index.npz`, float16). `/search?q=` embeds "a photo of <q>" with the text model (loaded lazily in the web UI) and ranks clips by their best frame. Models via fastembed, baked into the image under `/models/fastembed` (~580 MB). `SEARCH_ENABLED=false` turns indexing off.
- **Search objects**: index version 2 adds crops of every person / vehicle / animal (YOLO, up to `SEARCH_OBJECTS` per frame) next to the whole frames, so small details match; clips on version 1 are re-indexed in the background (`version` array in the npz).
- **Timelapse** (`app/timelapse.py`): the recorder saves a 960 px frame every `TIMELAPSE_INTERVAL` s to `/data/timelapse/frames/<day>/`; `NightlyBuilder` (recorder thread, after `TIMELAPSE_BUILD_AT`) builds `/data/timelapse/<day>-timelapse.mp4` (~`TIMELAPSE_SECONDS`, 10..60 fps) and `<day>-highlights.mp4` (`HIGHLIGHT_SECONDS` of each non-test recording from just before the detection, 1280 px, caption "HH:MM who" with drawtext/DejaVu), then deletes the frames; videos older than `TIMELAPSE_KEEP_DAYS` are pruned. `/timelapse` plays them and can build today so far.
- **Share** (`app/share.py`): `POST /clip/<day>/<stem>/share` (faces = strangers | all | none, plates) queues one job at a time. Faces in a wide view are often too small for the face detector, so heads are found via people: YOLO person boxes on the full-resolution frame, top third pixelated (in "strangers" mode YuNet looks inside that head crop and keeps it only for a clear library match); plates via `open_image_models.create_detector` on the full frame; every other frame, boxes kept for two passes, output scaled to 1280 px. A first version detected faces on the 1280 px frame and missed small faces entirely, verified on real footage; audio dropped; libx264 to `/data/shares/<id>.mp4` (kept `SHARE_KEEP_DAYS`). "Strangers" keeps a face only at library similarity >= threshold + `SHARE_KNOWN_MARGIN`. Status `GET /api/share/<id>`, download `GET /shares/<file>`; buttons on the clip page and in the wall view tag sheet.
- **Household alerts** (`app/household.py`): a person alert is held up to `HOUSEHOLD_WAIT_SECONDS` while faces inside the person boxes are matched against the library embeddings (`/data/library_cache.json`, written by facematch). Only known faces (optionally limited to `HOUSEHOLD`) -> one quiet push ("Alex is at the camera", priority low, or min with `HOUSEHOLD_ALERTS=silent`); an unknown face -> the normal alert at once; no face by the deadline or event end -> the normal alert. `HOUSEHOLD_ALERTS=normal` = previous behaviour.
- **LAN without password**: Settings toggle `lan_no_auth` skips HTTP Basic auth for direct requests from the trusted networks (`settings.trusted_networks()`: the list edited under Settings → Login - home LAN, VPN subnets, each with a name; before the first save `LAN_NETWORKS`; default 192.168/16, 10/8; Docker's 172.16/12 deliberately excluded). Requests carrying proxy headers (`X-Forwarded-For`, `Forwarded`, `X-Real-IP`, `X-Forwarded-Host`) always need the password. The Settings page shows whether the current device counts as LAN.
- **Push buttons and snooze** (`app/alerts.py`): every detection push has *Open clip*, *Star* and *Snooze 1h* (ntfy `http` actions). The buttons call `POST /a/<star|snooze>?c&d&s&e&sig` without a login: `sig` is an HMAC (secret `/data/action_secret`, made on first use) over action, camera, day, stem and expiry (`ACTION_LINK_HOURS`, 24). Needs `WEB_BASE_URL` reachable from the phone. Snooze = `settings.snooze[camera]` epoch; every push of that camera is skipped (recording/HA go on); Settings → Snooze has 1/4/12 h and Resume.
- **One visit across cameras**: recorders call `alerts.claim()` right before a push; `/data/recent_alerts.json` (flock) holds the last 10 min. Same kind (person/vehicle/animal) on another camera within `ALERT_MERGE_SECONDS` (90) of that visit's last sighting -> no push, `"linked": {camera, clip}` in the clip json. A loud alert never merges into a quiet household one. The web UI groups independently (`day_groups()`: clips of 2+ cameras whose gaps are <= 90 s), shown as 🔗 tags, "Same visit" + *Play all* on the clip page, `visit` in `/api/visits`.
- **Unusual activity** (`app/unusual.py`): per camera, history = clip sidecars of the previous `UNUSUAL_HISTORY_DAYS` (28) days, re-read hourly in a thread. Unusual = this kind never seen on this camera within +-`UNUSUAL_WINDOW_MINUTES` (60) of this time of day (weekdays/weekends apart), or seen then but never in this zone (only zones with history count, so new zones don't alarm). Silent until `UNUSUAL_MIN_DAYS` (14) of history. Setting `unusual_alerts` off / armed / always (also when disarmed); unusual loud alerts are urgent, never merged, `"unusual"` reason in the clip json, HA event `unusual`.
- **Find cameras** (`app/onvif.py`): WS-Discovery multicast doesn't leave the Docker bridge, so `scan()` tries TCP 554/8554 on every address of a private subnet (<= /22, default = the /24 of the address the browser used), then probes ONVIF on 80/8000/8080/2020/8899/888. `streams()` logs in with a WS-Security digest (clock offset taken from the camera), GetDeviceInformation, GetCapabilities (Media XAddr, host replaced by the address we reach), GetProfiles, GetStreamUri per profile; URLs get the login URL-encoded. Routes `/settings/cameras/scan`, `/settings/cameras/onvif` (private addresses only); dialog on each camera card.
- **Notifications in Settings**: `settings.ntfy()` (server, topic, status topic, token or user/password, priority; else `NTFY_*` from .env). `common.Ntfy` re-reads it when settings.json changes. Host scripts source `extras/ntfy.sh`, which overlays the saved values with python3 + shlex. *Save & send a test push* reports the error text.
- **Phone home** `/m` (`app/mobile.html`, static, data from `/api/status` + `/api/visits`): attention list built client-side from `cameras` (offline), `unusual_today`, `packages_waiting`, `strangers` (group count), `offsite` (enabled + last error) and `snoozed`; live strip refreshes only the camera in view every 5 s; status every 30 s, visits every 60 s. Manifest `start_url` is `/m`.
- **Camera finder discovery**: `onvif.discover()` sends the WS-Discovery Probe to each address (UDP 3702) - unicast replies pass Docker's NAT, unlike multicast - giving maker/model (`onvif://www.onvif.org/name|hardware/` scopes) and the ONVIF port; `scan()` merges that with the RTSP port check.
- **Phone app**: `/manifest.webmanifest`, `/sw.js` (no caching, offline message only), icons in `app/static/`; all served without login. The service worker only registers in a secure context (HTTPS or localhost): on plain http phones can still add a home-screen icon.
- **Off-site storage** (`app/offsite.py`, container `offsite`; rclone v1.75.2 in the image, checksum-pinned in the Dockerfile). Destination = rclone remote `camwatch` in `/data/rclone.conf` (mode 600, holds the credentials; S3 secrets are plain text there - rclone only obscures password-type fields, reversibly). Encryption (default on) = crypt remote `camwatch-crypt` over `<path>/encrypted` with keys camwatch generates (`secrets.token_urlsafe`); kept when options change; the recovery download (`/settings/offsite/recovery`) reveals them. **Always `--obscure`** on `config create`: rclone otherwise stores long base64-looking passwords unobscured (found in testing - the recovery keys would have been wrong). Connecting: `config create --non-interactive` + `config update --continue --state --result` for follow-up questions (iCloud 2FA code, OneDrive drive choice) shown generically in the UI. OAuth (Drive/OneDrive/Dropbox): `rclone authorize --auth-no-open-browser` waits on 127.0.0.1:53682 in the web UI container; the UI reads the provider URL from rclone's local redirect, the user pastes back the `http://127.0.0.1|localhost:53682/?code=` address, the web UI forwards it to the waiting rclone and takes the token. iCloud: Apple ID + password, 2FA asked next; needs Advanced Data Protection off; the trust token expires ~monthly (errors get a "reconnect" hint, failure push after `OFFSITE_FAIL_PUSH_HOURS`). Layout: `clips/<day>/` (people / all, last `keep_days`), `starred/<day>/` (forever), `timelapse/`, `db-backup/`; `rclone copy --files-from-raw --no-traverse` (unchanged files skipped), `rclone delete --min-age <keep>d` for retention. Alarms: `send_alert` (loud, not test) -> `offsite.queue_alarm` -> `/data/offsite/queue/*.json`; snapshot uploaded at once, clip when its video + json exist, given up after 30 min (left to the nightly run). Nightly at `OFFSITE_BATCH_AT` (03:30) or on *Upload now* (`/data/offsite/run_now`); retry after 15 min on failure; status in `/data/offsite/status.json`. Tested end to end against `rclone serve s3` / `serve sftp` in a throwaway container (`test_offsite_real.py` approach); Google/Dropbox/Microsoft/Apple flows verified up to the sign-in page only.

## 6. Presence log (`app/presence.py`)

"Who came and when", in MariaDB (`DB_NAME`, `DB_USER`, `DB_PASSWORD`; socket `/run/mysqld`).

- Every `PRESENCE_SCAN_INTERVAL` scans `/recordings/*/` and (re)imports events whose `.json`, `.faces.json`, `.labels.json` or `.track.json` changed (mtime signature in `visits.source_sig`, plus a hash of the house/street/parking zones). Names fill in once facematch has run or someone tags the clip.
- Tables `visits` (one row per event) and `visitors` (person/vehicle/animal, `name` or NULL, source face/manual/plate/detection, detail, confidence, direction); view `presence_log` (one line per non-test visit with a `who` summary). Deleted clips keep their visit (`clip_deleted = 1`).
- **Arrived / left**: person detections from the track are split into paths (nearest recent path within reach; a 3 s gap ends a path; < 3 points ignored). The first/last **house** or **street** zone a path touches (within 0.06 frame heights) gives `arrived` (street→house), `left` (house→street) or `visited` (street→house→street, e.g. a delivery). Cars use the `vehicles` entries from the parking monitor (or, for backfilled clips, the parking zone in the first/last 3 s of the track).
- Web UI **Log** page (`/log`): last seen per name, visits per day, range/kind/person filters.
- **Weekly report**: `/report` page and a low-priority push at `WEEKLY_SUMMARY` ("sun 20:00"), both from `weekly_report()`; preview with `presence.py --week [YYYY-MM-DD] [--send]`.
- **Daily summary** at `DAILY_SUMMARY_TIME`: low-priority push with the day's events, identified people (count, first-last time), unidentified visits, door visits, car arrivals/departures and animals; opens `/log`. A restart after that time doesn't resend. Preview/send by hand: `sudo docker compose run --rm --no-deps presence python presence.py --summary [YYYY-MM-DD] [--send]`.
- Re-import everything: `sudo mariadb camwatch -e "UPDATE visits SET source_sig=''"`.

---

## 7. Data formats

### Recordings: `$RECORDINGS_PATH/YYYY-MM-DD/`

| File | Written by | Content |
|---|---|---|
| `<stem>.mp4` (or `.mkv`) | recorder | the clip (video copied from the camera, audio AAC) |
| `<stem>.mp4.part` | recorder | temporary during concat |
| `<stem>.jpg` | recorder (event start) | full-resolution snapshot |
| `<stem>.json` | recorder | `{camera, start, end, peak_motion, labels:{label:conf}, zones, loitering, test, plates:[…], vehicles:[…], video}` |
| `<stem>.track.json` | recorder / tracks.py | detection foot points over time |
| `<stem>.faces.json` | facematch | `{video, processed_at, duration_s, frames_sampled, faces_seen, known:[…], unknown:[…]}` or `{video, error}` |
| `<stem>_faces/`, `<stem>_plates/` | facematch / recorder | crops |
| `<stem>.labels.json` | webui | manual person tags |
| `<stem>.star` | webui | starred: never auto-deleted |

`delete_event(folder, stem)` removes `stem.*`, `_faces/` and `_plates/`.

### Data: `$DATA_PATH/`

`settings.json` (§8.2), `library_cache.json` (safe to delete), `sightings.jsonl`, `plates.jsonl`, and the iCloud sync state files if that extra is used.

### Photos: `$PHOTOS_PATH/<Person>/…`

Managed on the People page (uploads validated with `cv2.imdecode`). "This is them" on a clip copies the face crop into the person's folder.

### Retention (`prune_recordings`, every 10 min)

1. Starred clips: never deleted.
2. Clips with an identified or tagged person: `RETENTION_KEEP_DAYS`.
3. Others: `RETENTION_DAYS`.
4. Free space < `MIN_FREE_GB`: oldest untagged first, then oldest identified.

---

## 8. Configuration

### 8.1 `.env` (apply with `sudo docker compose up -d`)

Every key is documented with its default in [.env.example](.env.example). Groups: camera (`CAMERA_NAME`, `RTSP_URL`, `DETECT_URL`, `TZ`, `RECORD_AUDIO`), host paths, ntfy, motion detection, object detection, number plates, recording & retention, face matching, Home Assistant (`MQTT_*`, `HA_WEBHOOK_URL` - starting values only: once saved on the Settings page, `settings.integration()` uses those, and `homeassistant.py` reconnects within 10 s), web UI (`WEB_PORT`, `WEB_BASE_URL`, `WEB_USER`, `WEB_PASSWORD`), presence log (`DB_*`, `PRESENCE_SCAN_INTERVAL`, `PARKING_*`), daily summary, iCloud sync (`ICLOUD_SHARE`, `ICLOUD_CRED`). `env()` treats empty values as unset.

### 8.2 Runtime settings: `$DATA_PATH/settings.json` (no restart; polled every 2 s)

Edited by the web UI (Settings, Zones, Plates) and the HA Armed switch.
```jsonc
{
  "mode": "armed | disarmed | schedule",
  "schedule": "22:00-07:00",          // armed window for schedule mode, may wrap midnight
  "loiter_seconds": 30,               // 0 = off
  "zones": [{"name": "…", "type": "ignore|trigger|house|street|parking", "points": [[x, y], …]}],   // 0..1
  "plates": [{"plate": "AB12345", "name": "…"}]
}
```
Zone types: **package** (doorstep: parcel delivered / picked up, see `app/packages.py`), **ignore** (excluded from motion/detection), **trigger** (only detections inside count; each becomes an HA sensor), **house** / **street** (presence log directions), **parking** (car arrived/left). Disarmed = recording, HA events and offline alerts continue; only detection pushes stop. A legacy `MOTION_MASK` in `.env` is imported once as ignore zones.

---

## 9. Integrations

**ntfy**: health messages (camera offline/online, recording stalled/resumed, database backup failed) use `Ntfy.status()`: tag `status`, sent to `NTFY_STATUS_TOPIC` if set, else the alert topic, so dashboards watching the alert topic can ignore them. `common.Ntfy.send()` PUTs the JPEG with `Filename`/`Message` headers (RFC 2047 for non-ASCII), falls back to POST; `Click` + "Open clip" action link to `/clip/<day>/<stem>` (`WEB_BASE_URL`).

**Home Assistant via MQTT** (recorder owns discovery and LWT): base topic `camwatch/<camera>/…`, discovery `homeassistant/<component>/camwatch_<camera>/<key>/config`, device "camwatch <camera>".

| Entity | Topic(s) |
|---|---|
| `switch.…_armed` | `…/armed`, command `…/armed/set` |
| `binary_sensor.…_motion` | `…/motion` |
| `binary_sensor.…_<label>` per `DETECT_OBJECTS` | `…/<label>` |
| `binary_sensor.…_zone_<name>` per trigger zone | `…/zone_<name>` |
| `binary_sensor.…_camera_online` | `…/online` |
| `camera.…_last_event` | `…/snapshot` (JPEG, retained) |
| `sensor.…_last_event_time`, `…_last_identified`, `…_last_plate` | `…/last_event`, `…/last_identified`, `…/last_plate` |
| `event.…_detection` | `…/event` (JSON with `event_type`) |
| availability | `…/availability` (LWT) |

Event types: each detected label, `motion`, `loitering`, `plate`, `vehicle_arrived`, `vehicle_left`, `identified`, `unknown_face`, `camera_offline`, `camera_online`, `recording_stalled`, `recording_resumed`, `test`. Payload `{event_type, camera, time, armed?, clip_url, snapshot_url, …}` plus type-specific fields.

**Webhook**: with `HA_WEBHOOK_URL` every event payload is also POSTed as JSON.

The web UI page `/homeassistant` renders a setup guide with the real entity ids, MJPEG camera config (`/live.mjpg`, `/live.jpg`), a dashboard card and automations.

---

## 10. Web UI routes (`app/webui.py`)

| Route | Purpose |
|---|---|
| `GET /` | clips by day, timeline, label filter, cross-day `?person=`, `?plate=`, `?starred=1` |
| `GET /clip/<day>/<stem>` | player, detections, plates, faces ("This is them"), tags, star, delete |
| `POST /clip/<day>/<stem>/label`, `/label/<i>/delete`, `/star`, `/delete` | |
| `GET /media/<day>/<path>` | videos/images with Range support |
| `GET /dashboard` | **dashboard**: status strip (camera, events today/7 days, people seen today, last event, packages waiting, disk) and a tile for every page; `GET /api/status` feeds it |
| `GET /report?week=YYYY-MM-DD&label=` | weekly report (per day/hour, people, cars, packages, door visits, animals, heatmap); data from `presence.weekly_report()` |
| `GET /api/heatmap.jpg?days=N` or `?from=&to=` `&label=person` | density of detection foot points from `<stem>.track.json`, drawn over the newest snapshot (cached) |
| `GET /api/clip/<day>/<stem>` | faces/tags/plates/star of one clip (wall view tag sheet) |
| `GET /timelapse`, `POST /timelapse/build`, `GET /timelapse/file/<name>` | daily timelapse + highlights |
| `POST /clip/<day>/<stem>/share`, `GET /api/share/<id>`, `GET /shares/<file>` | blurred shareable copy |
| `GET /search?q=` | search recordings by description (CLIP) |
| `GET /strangers`, `POST /strangers/name`, `/strangers/hide` | recurring unknown faces |
| `GET /view` | **wall view** (`app/wallview.html`): phone/tablet page in a dark "Wall" panel style: live snapshot every 4 s / ▶ Live MJPEG (auto-stop after 2 min), filter chips, recordings per day with infinite scroll, full-screen player with swipe, pull-to-refresh, add-to-home-screen meta |
| `GET /api/days`, `/api/visits?day=`, `/api/thumb/<day>/<stem>.jpg?w=` | JSON / thumbnails for the wall view (non-test recordings; visits cached by sidecar mtimes) |
| `GET /live`, `/live.mjpg`, `/live.jpg[?w=]` | live view (~5 fps detection frames); `w` scales the still |
| `POST /simulate-motion` | end-to-end test (real clip + real push) |
| `GET/POST /people…` | photo library |
| `GET/POST /plates`, `POST /plates/<p>/delete` | known and seen plates |
| `GET /zones`, `POST /zones` | zone editor over the live image |
| `GET/POST /settings`, `POST /arm` | arming, schedule, loitering |
| `GET /log` | presence log |
| `GET /homeassistant` | HA setup guide |
| `GET /healthz` | health (no auth) |

HTTP Basic auth when `WEB_PASSWORD` is set. Path inputs are validated (`DAY_RE`, `STEM_RE`, `NAME_RE`; crop paths must resolve inside the clip folder).

---

## 11. Operations

```bash
cd /opt/camwatch
sudo docker compose ps                         # status / health
sudo docker compose logs -f recorder           # also: facematch, presence, webui
sudo docker compose up -d                      # apply .env changes
sudo docker compose up -d --build              # rebuild after code changes (or: sudo ./deploy.sh)
sudo docker builder prune -af && sudo docker image prune -f   # reclaim space after builds
```

Code is baked into the image: after editing `app/`, rebuild, otherwise the containers keep running the old code (compare with `docker exec camwatch-recorder md5sum /app/recorder.py`). Keep files **LF**, not CRLF (`grep -rlU $'\r' .`). There is no test suite; use the checklist below.

One-offs:
```bash
sudo docker compose run --rm recorder python latency.py [--b <direct-rtsp-url>]  # stream health; delay A vs B (move in front of the camera)
sudo docker compose exec recorder python plates.py [--force] [YYYY-MM-DD ...]      # plates in existing clips
sudo docker compose run --rm recorder python tracks.py [--force|--file …]          # backfill tracks
```

Verification after a change:
1. `docker compose ps`: recorder `healthy` within ~2 min (frames arriving).
2. Web UI Live page shows the picture.
3. Live → "Simulate motion": a "test" push arrives; a clip tagged `test` appears ~20 s later.
4. `/homeassistant` renders; Zones page shows zones over the live image; Log page lists visits.

---

## 12. Security & privacy

- Set `WEB_PASSWORD`. `/healthz` is exempt; HA's MJPEG camera and push links need the same login.
- No CSRF protection on POST forms: keep the web UI LAN-only; **never expose port 8080 to the internet**; use a VPN for remote access.
- The feed extra has no login; restrict `FEED_ALLOW` to the panels that need it.
- RTSP URLs often contain credentials or tokens; anyone who learns them can view the camera.
- On public ntfy.sh, knowing the topic means reading the alerts (incl. snapshots): use a long random topic, access tokens or a self-hosted server.
- Face recognition and plate logging process third parties' personal data (visitors, passers-by); point the camera at your own property and keep retention short (GDPR in the EU).
- `.env` is `600 root`; never commit it (`.gitignore` excludes it).

---

## 13. Gotchas and lessons learned

- **CRLF**: files edited on Windows can end up with CRLF; `deploy.sh` then fails with `set: pipefail\r: invalid option`.
- **Disk during builds**: building the same image once per service plus build cache can fill a small root disk; build once and prune after every build.
- **YuNet and large faces**: close-up portraits give "no face" at 1920 px; detection works at 640 px (the library loader tries 640 → 1280 → 1920).
- **Parked cars** in view: handled by ignore zones, `StationaryFilter`, plate reads only inside moving vehicle boxes, and in the plate backfill only plates that moved during the clip. Parking zones deliberately ignore the ignore zones.
- MQTT/HA: the discovery code exists but should be verified against your broker after setup.

---

## 14. Ideas not implemented

- go2rtc for full-FPS live view with audio and a single shared RTSP connection per camera.
- CPU headroom for 4 cameras: one shared detector, substreams by default, OpenVINO on an Intel iGPU.
- Alert rules per camera/zone (garden only at night, driveway only cars).
- Camera tamper/health: covered, moved, blurry lens, IR failure.
- Sound events (glass break, smoke alarm, barking).
- Several logins with roles; audit log.
- Storage page with per-camera usage and days left; export/import of settings; privacy masks.
- "That's <name>" push button (needs face identification during the event, not after it).
