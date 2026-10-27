# dantestreamer: latest changes

Newest first.

## 2026-10-27

- `BUILD_AND_TEST.md` rewritten: how the image is built, what to run after
  each kind of change, and five checks (tested on the running host). The
  screenshot script is now in the repo as `tools/screenshots.py`. Removed
  `DOCKER_SETUP.md`, `MULTI_SOURCE_AUDIO.md`, `DANTE_PLAYER_PROJECT.md`
  and `VIRGIL_API_REFERENCE.md`: plans for a custom Virgil fork and Google
  Cast that were never built, and the README covers the rest.
- README rewritten to match what runs: AirPlay to Dante through Virgil,
  the panel and API on port 8480, `.env` names, real ports and
  troubleshooting. Removed the Google Cast, port 8080, systemd,
  Kubernetes and Raspberry Pi package instructions, which never existed.
- Screenshots of the control panel in the README: status, meters,
  diagnostics, routing, settings and the phone view
- Editable names: Dante device, AirPlay and channel names set in `.env`
  (see `.env.example`); Virgil's live config moves to `data/` so renames
  and Stop/Start are saved
- Add DanteStreamer
