# Product

<!-- impeccable:product-schema 1 -->

Scope: DStreamer only, covering `dstreamer/` (engine and web control panel) and
`dstreamer-desktop/` (Windows and macOS clients). The `panels/` and `CamWatch/`
projects in this repository are out of scope and have no product record yet.

## Platform

web

## Users

People running a Dante audio network who want AirPlay sources on it. The
primary user installs DStreamer themselves, routes it in Dante Controller, and
expects it to keep working unattended afterwards.

Two usage setups are confirmed, and they imply different users:

- A DStreamer box on the network, usually a small Linux host that phones and
  Macs play to over AirPlay. The user administers it from another machine.
- A Windows PC or Mac that joins the Dante network itself and sends its own
  system audio to the speakers.

The product is built for general release, not only for its author's home lab.
Someone who has never seen it installs from a GitHub release and gets no
help from the author, so first run, discovery and failure messages carry the
same weight as the running state.

## Product Purpose

DStreamer puts AirPlay audio into a Dante network. It appears in Dante
Controller as an ordinary Dante device with 8 transmit and 8 receive channels
by default, and AirPlay plays on transmit 1 and 2, which the user routes to any
Dante speaker, amp or mixer.

It succeeds when a phone can play to a Dante system without the user learning
anything new about Dante, and when a dropout tells the user what caused it.

## Positioning

A Dante endpoint built from open-source parts that runs on ordinary Linux
hardware in Docker, with no Audinate hardware or licensed virtual soundcard.
The Dante side is Virgil, a virtual soundcard on Inferno; AirPlay comes in
through Shairport Sync. The combination of an AirPlay receiver and a Dante
transmitter in one container is what a neighbouring product could not copy
without assembling the same stack.

## Operating Context

- The engine runs as one Docker container on a Linux host.
- Signal path: AirPlay source, then Shairport Sync, then the ALSA `virgil`
  device, then Virgil, then the Dante network on transmit 1 and 2.
- Dante Controller is the system of record for device names, channel names and
  routing. Renames made there persist across restarts.
- The web control panel at `http://127.0.0.1:8480/` is Virgil Control, part of
  Virgil, not code this project authored. It serves a REST API on the same port
  and has a phone view. The panel and API listen on the host only; remote
  access is an SSH tunnel on the same port.
- The desktop clients find engines over Bonjour, advertised as
  `DStreamer._raop._tcp.local`.
- Installation is from GitHub releases: a signed, notarized Mac `.dmg`, and a
  shell script for Linux and the Raspberry Pi. No Windows build - DStreamer
  cannot reach the wire for its PTP clock there.

## Capabilities and Constraints

Confirmed capabilities:

- Up to 128 channels each way at 44.1, 48, 88.2 or 96 kHz. Default is 8 by 8 at
  48 kHz.
- Follows the network's Dante clock leader, and leads the clock itself when no
  other device does.
- Device, AirPlay and channel names set in one `.env` file.
- Control panel covering clock status, per-channel level meters both
  directions, dropout diagnostics with causes and an event log, routing, and
  settings including start and stop.
- Desktop clients show device name, engine state, network address, clock state
  and leader, sample rate, channels, dropouts in the last hour, and the apps
  playing; live meters from -60 to 0 dBFS using Dante Controller's channel
  names; Start, Stop and Restart; Open web panel; Find on network; and several
  DStreamers in one list.

Constraints:

- The desktop clients are real surfaces but fall outside impeccable's platform
  guidance, which covers web, iOS and Android. Windows is WPF and XAML on
  .NET 8, Windows 10 or later. macOS is Swift, a universal arm64 and x86_64
  binary, macOS 12 or later. Web guidance needs translating for both.
- The macOS app ships signed with a Developer ID and notarized by Apple.
  Distribution depends on both, so anything bundled inside the app has to be
  signable.
- Virgil is GPLv3 and ships inside both desktop apps, pinned to a known version
  and commit.
- The only web surface is Virgil Control, which this project does not own.
  Changing its design means forking Virgil and carrying the patches, not
  editing code in this repository. The screenshots under
  `dstreamer/docs/screenshots/` are of that third-party panel. The interfaces
  DStreamer does author are the Windows and macOS clients.
- macOS bundle identifier is `com.dstreamer.controller`.
- Terminology follows Dante's, not an invented vocabulary: transmit and receive
  channels, clock leader, sample rate, dropouts.

Undecided: no pricing, licensing terms for DStreamer itself, or support
commitment has been established.

## Brand Commitments

- The name is DStreamer, renamed from DanteStreamer in October 2026. The
  desktop app is DStreamer Controller.
- Dante is Audinate's protocol, not part of the product name. References to
  Dante, DanteInstance and Dante models mean the protocol and stay as they are.
- All prose follows the no-AI-slop rules recorded in `AGENTS.md`: lead with the
  point, stay concrete, no banned filler words, no em dashes by habit, plain
  formatting. This applies to UI text as much as to documentation.

## Evidence on Hand

- Engine control panel screenshots exist at `dstreamer/docs/screenshots/`:
  status, meters, diagnostics, routing, settings, and a phone panel.
- Desktop client screenshots do not exist yet. `dstreamer-desktop/README.md`
  records them as not taken.
- `AGENTS.md` requires a screenshot for every user-facing feature, kept current
  in the same change that alters the feature.
- No testimonials, user research, usage numbers, benchmarks or case studies
  exist. Future work must not invent them.

## Product Principles

1. A stranger has to get from install to audio alone. The author is not
   available to explain anything.
2. Dante Controller owns names and routing. DStreamer reflects what is there
   rather than offering a competing place to set it.
3. A dropout names its cause. Diagnostics are a feature of the product, not a
   log for the author.
4. The web panel, the Windows client and the macOS client state the same truth
   about an engine, in the same words.
5. Speak Dante's vocabulary. Users arrive already knowing it, and renaming its
   concepts costs them more than it gains.
