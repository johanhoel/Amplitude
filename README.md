# Amplitude

Johan's AV, audio and home-lab projects, one folder each. Every folder has
its own README, changelog and setup.

| Project | What it does |
|---------|--------------|
| [dstreamer](dstreamer/) | Streams AirPlay audio to a Dante network, using the Virgil engine (Inferno-based) in Docker. [Latest changes](dstreamer/CHANGELOG.md) |
| [dstreamer-desktop](dstreamer-desktop/) | macOS and Windows apps that show DStreamer status and meters and start or stop the engine. [Latest changes](dstreamer-desktop/CHANGELOG.md) |
| [panels](panels/) | Home Deck: wall panels, phone pages, Studio, boards, cameras and the Android app for the home lab. [Latest changes](panels/CHANGELOG.md) |
| [CamWatch](CamWatch/) | Self-hosted camera recorder: up to 4 RTSP cameras, person/vehicle detection, face recognition, ntfy pushes, Home Assistant, off-site copies and a web UI with phone pages. [Latest changes](CamWatch/CHANGELOG.md) |

## Linux and Raspberry Pi

One script installs any of the three on a Debian or Ubuntu machine or a
Raspberry Pi:

```bash
curl -fsSL https://raw.githubusercontent.com/johanhoel/amplitude/main/installers/linux/setup.sh | sudo bash -s camwatch
```

There is no Mac or Windows installer. Both existed and both were removed;
[installers/README.md](installers/README.md) says why, and what to do if you
only have a Mac.

## Layout

```
amplitude/
  dstreamer/   one folder per project
  panels/          Home Deck
  CamWatch/        camera recorder
  README.md        this index
```

To add a project, create a new top-level folder, put everything it needs
inside it, and add a row to the table above with a link to its `CHANGELOG.md`.

Every README has the same shape - Screenshots, Features, Install, Use,
How it is built, Troubleshooting, Notes - so one project reads like the next.
[AGENTS.md](AGENTS.md) has the template and the screenshot rules.

## Planning

Issues and pull requests are tracked on one GitHub Project board for the whole
repository, not one board per folder. Each item carries an **Area** field
(`Home Deck`, `CamWatch`, `DStreamer`, `Desktop`, `Installers`), so a single
project's work is a filter rather than a separate board. Work that crosses two
projects - the CamWatch feed behind the Home Deck camera panel, say - then has
somewhere to live.

## Working on a project

```bash
git clone https://github.com/johanhoel/amplitude.git
cd amplitude/<project>      # then follow that project's README
```

Changes go on a short-lived branch and are merged into `main`.
