# Amplitude

Johan's AV, audio and home-lab projects, one folder each. Every folder has
its own README, changelog and setup.

| Project | What it does |
|---------|--------------|
| [dstreamer](dstreamer/) | Streams AirPlay audio to a Dante network, using the Virgil engine (Inferno-based) in Docker. [Latest changes](dstreamer/CHANGELOG.md) |
| [dstreamer-desktop](dstreamer-desktop/) | macOS and Windows apps that show DStreamer status and meters and start or stop the engine. [Latest changes](dstreamer-desktop/CHANGELOG.md) |
| [panels](panels/) | Home Deck: wall panels, phone pages, Studio, boards, cameras and the Android app for the home lab. [Latest changes](panels/CHANGELOG.md) |
| [CamWatch](CamWatch/) | Self-hosted camera recorder: up to 4 RTSP cameras, person/vehicle detection, face recognition, ntfy pushes, Home Assistant, off-site copies and a web UI with phone pages. [Latest changes](CamWatch/CHANGELOG.md) |

## Windows and Mac

Each project has an installer for Windows (`.exe`) and for Mac (`.dmg`) on the
[Releases page](https://github.com/johanhoel/amplitude/releases). It sets up a small
Linux system on the computer and installs the project in it. How it works: [installers/README.md](installers/README.md).

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

Every project's README has a Screenshots section with one screenshot per
feature, updated whenever a feature changes. 
## Working on a project

```bash
git clone https://github.com/johanhoel/amplitude.git
cd amplitude/<project>      # then follow that project's README
```

Changes go on a short-lived branch and are merged into `main`.
