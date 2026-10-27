# CamWatch: latest changes

Newest first.

## 2026-10-27

- README: install clones `amplitude` and works in `CamWatch/` (the old command pointed at a standalone repo)
- README: screenshots of every page (desktop and phone), from demo data with `dev/screenshots.py`
- Camera 1 can be switched off (removed) like the other cameras
- Version indicator (2026.10.27) on every page and in `/api/version`
- release.sh no longer stops silently when `.env` has no `CAMWATCH_PREFIX`

## 2026-10-26

- Camera passwords: the masked password (••••••) always stands for the whole saved password; half-edited masks
  are refused, and passwords with `/ # ? @` are kept exactly
- Staging on the data disk with a fake camera, releases with automatic rollback, CI workflow
- Tests in the repo (`tests/run.py`) and AGENTS.md for coding agents
- Phone home screen (`/m`): what needs attention, swipeable live cameras, today and recent visits
- Camera finder: scans the network (ONVIF discovery shows maker and model) and fills in the stream addresses
- Off-site storage: copies to iCloud Drive, Google Drive, OneDrive, Dropbox, Backblaze B2, S3 or a NAS through
  rclone; encrypted by default, alarms uploaded at once, the rest nightly; "Sign in again" keeps the keys
- One visit across cameras (one push, Play all), Star / Snooze 1h buttons on pushes, unusual-activity alerts,
  ntfy settings in the web UI, installable phone app
- Settings: camera cards, trusted networks for login without password, cameras and Home Assistant/MQTT set in
  the web UI
- Multiple cameras (up to 4)
- Timelapse and highlights, shareable blurred copies (heads and plates pixelated), search by objects
- Every page restyled in the dark "Wall" look

## 2026-10-25

- Recurring strangers, search by description, quiet pushes for the household, optional no-password login on the LAN
- Dashboard, weekly report, heatmap, package detection, tagging from the wall view
- Wall view (`/view`): phone/tablet Cameras page
- Recording watchdog, status alerts, number plate cleanup, Home Assistant event types, database backup
- Add CamWatch
