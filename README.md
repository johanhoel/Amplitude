# Amplitude

A collection of AV and audio projects. Each project lives in its own folder
with its own README, Dockerfile and config.

| Project | What it does |
|---------|--------------|
| [dantestreamer](dantestreamer/) | Streams AirPlay audio to a Dante network, using the Virgil engine (Inferno-based) in Docker |

## Layout

```
amplitude/
  dantestreamer/   one folder per project
  README.md        this index
```

To add a project, create a new top-level folder, put everything it needs
inside it, and add a row to the table above.

## Working on a project

```bash
git clone https://github.com/johanhoel/amplitude.git
cd amplitude/dantestreamer
docker compose up -d --build
```

Changes go on a short-lived branch and are merged into `main` by pull request.
