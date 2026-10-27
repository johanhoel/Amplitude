# Amplitude

A collection of AV and audio projects. Each project lives in its own folder
with its own README, Dockerfile and config.

| Project | What it does |
|---------|--------------|
| [dantestreamer](dantestreamer/) | Streams AirPlay audio to a Dante network, using the Virgil engine (Inferno-based) in Docker. [Latest changes](dantestreamer/CHANGELOG.md) |
| [panels](panels/) | Home Deck: wall panels, phone pages, Studio, boards, cameras and the Android app for the home lab. [Latest changes](panels/CHANGELOG.md) |
| [CamWatch](CamWatch/) | Self-hosted camera recorder: up to 4 RTSP cameras, person/vehicle detection, face recognition, ntfy pushes, Home Assistant, off-site copies and a web UI with phone pages. [Latest changes](CamWatch/CHANGELOG.md) |

## Layout

```
amplitude/
  dantestreamer/   one folder per project
  panels/          Home Deck
  CamWatch/        camera recorder
  README.md        this index
```

To add a project, create a new top-level folder, put everything it needs
inside it, and add a row to the table above.

Every project's README has a **Screenshots** section showing each of its
features, kept up to date as features change. See [AGENTS.md](AGENTS.md)
for the format.

## Working on a project

```bash
git clone https://github.com/johanhoel/amplitude.git
cd amplitude/dantestreamer
docker compose up -d --build
```

Changes go on a short-lived branch and are merged into `main` by pull request.
