# camwatch - guide for coding agents

Read this first. Deep details (architecture, data formats, every setting): [HANDOVER.md](HANDOVER.md).

## What this is

Self-hosted camera recorder: RTSP cameras -> motion + YOLO -> clips on disk, ntfy pushes, face matching, presence log
(MariaDB), Home Assistant (MQTT), off-site copies (rclone), web UI. Python 3.12, Flask + waitress, OpenCV, onnxruntime.
One Docker image (`camwatch:latest`), several containers (`docker-compose.yml`). Runs on a Proxmox LXC.

## Map

| File | What | Notes |
|---|---|---|
| `app/recorder.py` | one camera: buffer, motion, detection, events, alerts | started via `app/camslot.py` (4 slots) |
| `app/webui.py` | all web routes **and the HTML templates** (`TEMPLATES` dict near the end) | 2800 lines: search before reading |
| `app/settings.py` | `settings.json`: modes, zones, cameras, ntfy, MQTT, trusted networks | single source for runtime settings |
| `app/alerts.py` | snooze, signed push buttons, one push per visit | shared by recorders + web UI |
| `app/offsite.py` | rclone uploads, destination setup | its own container |
| `app/onvif.py` | camera finder (scan, WS-Discovery, ONVIF streams) | stdlib only |
| `app/facematch.py`, `strangers.py`, `household.py` | faces | |
| `app/presence.py` | visits -> MariaDB, daily/weekly summary | |
| `app/dashboard.html`, `wallview.html`, `mobile.html` | static pages served as-is, data via `/api/*` | |
| `tests/` | the gate - see below | |

## Rules

1. **Run the tests before you say you're done:** `python tests/run.py --quick` (about 1 min). Run the full
   `python tests/run.py` when you touched search, share, timelapse or models. All must pass. Never weaken or delete a
   check to make it pass - fix the code, or say why the check is wrong.
2. **Add a test for every change** in the matching `tests/test_*.py` (they are plain scripts: print lines starting
   with `PASS` / `FAIL`; `test_webui.py` builds fake recordings others reuse through `runpy`).
3. **Match the surrounding code**: plain functions, few comments that explain *why*, user-facing text in plain
   English (it is shown in the web UI and in pushes), no new dependencies without a good reason
   (`requirements.txt` is baked into a 3 GB image).
4. **Secrets never reach the browser or the logs**: camera URLs are shown with `mask_url()`, passwords as empty
   fields that keep the saved value. `settings.json` and `rclone.conf` are mode 600.
5. **Small, focused changes.** One feature per branch. Don't reformat files you don't change.
6. **You never deploy and never touch the server.** No SSH, no `docker compose` on the live system. A human merges
   and deploys (`extras/release.sh`, see below).

## Gotchas (each one cost a real bug)

- rclone: always `config create ... --obscure` - otherwise long base64-looking passwords are stored unobscured.
- rclone errors end in usage text / multi-line JSON: use `offsite._clean_error()`.
- Only the `recorder` service has `build:`; the others reuse the image. Never build per service (fills the disk).
- Files must be LF (shell scripts break with CRLF). `.gitattributes` enforces it.
- WS-Discovery multicast does not leave the Docker bridge; unicast probes do (`onvif.discover`).
- `webui.day_visits()` returns copies of cached dicts - never mutate `visit_json()` results.
- Several recorder containers share `/data` and `/recordings`: shared files need atomic writes (`tmp` + `os.replace`)
  or `flock` (`alerts.claim`).
- The web UI must stay usable at 375 px wide (phone) - check `/m`, `/view` and Settings.

## Running things locally

```
python tests/run.py --quick                     # the gate
python tests/run.py -k offsite -v               # one area, all output
python tests/serve_fake.py                      # web UI with fake data on http://127.0.0.1:18765
```

Setup once: `powershell -File dev/setup.ps1` (Windows) - creates `.venv` with the app requirements.

## Deploying (humans only)

Version: `app/VERSION` (date, e.g. `2026.10.27`) - bump it with each release. The commit is added automatically:
`app/BUILD` is filled in by `git archive` (`.gitattributes` export-subst). Shown in every page footer and `/api/version`.

Staging (fake camera, separate data) and production run on the LXC; `extras/release.sh` builds, starts, waits for
health and rolls back automatically if a container doesn't become healthy. See HANDOVER.md section 11.
