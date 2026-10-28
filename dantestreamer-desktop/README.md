# DanteStreamer Desktop

DanteStreamer Controller is an app for Windows and macOS. It sets up and
watches DanteStreamer, which sends sound to Dante speakers and amplifiers.

It works in two setups:

- **A. This computer plays to the speakers.** The PC or Mac joins the Dante
  network itself and sends its own sound (Spotify, a browser, everything) to
  the speakers. You need nothing besides the computer and the speakers.
- **B. A DanteStreamer box on the network.** DanteStreamer runs on another
  computer, usually a small Linux box that phones play to with AirPlay. The
  app watches it from your PC or Mac.

What the app shows and does:

- The device name, engine state, network address, clock state and leader,
  sample rate, channels, dropouts in the last hour and the apps playing.
- Live meters for every transmit and receive channel, from -60 to 0 dBFS,
  with the channel names from Dante Controller.
- Start, Stop and Restart audio buttons, and Open web panel for settings,
  routing and diagnostics.
- Find on network: lists DanteStreamer boxes, so you don't type addresses.
- Several DanteStreamers in one list (add, edit, remove).

## Screenshots

Not taken yet. They will go in `docs/screenshots/`: the start page, the
Status tab and the Meters tab, on Windows and macOS.

## Download

Get the newest `desktop-v1.0.…` release from the
[Releases page](https://github.com/johanhoel/Amplitude/releases).

- **Windows:** download `DanteStreamerController-windows.zip`, unzip it and
  run `DanteStreamerController.exe`. Windows 10 or 11, 64-bit. Nothing else
  to install. If Windows SmartScreen says it protected your PC, click
  *More info* and then *Run anyway*.
- **macOS:** download `DanteStreamer-macos.zip`, unzip it and drag
  `DanteStreamer.app` to Applications. macOS 12 or later, Apple silicon or
  Intel. If macOS says it cannot check the app, right-click it, choose
  *Open*, then *Open* again. The release notes say whether this build is
  notarized; a notarized build opens without that step.

## Connect to your DanteStreamer

The first time the app opens, it shows a start page with the two setups.
Follow the one that matches yours.

### A. This computer plays to the Dante speakers

You need the computer, the Dante speakers or amplifier, and a network switch
or router they are all plugged into. A wired network works best; Dante over
Wi-Fi drops out.

DanteStreamer uses Virgil as its Dante engine. Virgil is free and has its
own installer.

**Windows**

1. In DanteStreamer Controller, click **Download Virgil**. This opens
   Virgil's releases page. Under the newest release, download
   `Virgil-<version>-win64-setup.exe` and run it.
2. Windows asks whether to allow Virgil on the network. Click **Allow**
   (private networks are enough).
3. Back in DanteStreamer Controller, click **Use this computer**. Within a
   second the Status tab shows the device name and the clock. The clock
   turns green (`ptp-locked`) once it hears your Dante speakers.
4. Send the PC's sound to Dante. Click the arrow next to the clock on the
   taskbar, right-click the **Virgil** icon and choose **Desktop audio…**.
   Click **Add…** and pick **Default output device** to send everything the
   PC plays. To send one app only, pick **App** and type its name, for
   example `spotify.exe` or `chrome.exe`. Set the channel to **1** (stereo:
   transmit channels 1 and 2).
5. Open **Dante Controller** (free from
   [Audinate](https://www.audinate.com/products/software/dante-controller)).
   In the *Routing* tab, find your speakers in the left column and this PC
   along the top. Click the squares where the speakers' inputs meet this
   PC's transmit channels 1 and 2. A green tick means the route works.
6. Play something. The Meters tab in DanteStreamer Controller moves on
   transmit 1 and 2, and the speakers play.

**macOS**

1. In DanteStreamer Controller, click **Download Virgil**. Under the newest
   release, download `Virgil-<version>-macos.pkg` and open it. Follow the
   installer.
2. If macOS asks whether Virgil may accept incoming network connections,
   click **Allow**.
3. In DanteStreamer Controller, click **Use this Mac**. The Status tab shows
   the device name and the clock. The clock turns green (`ptp-locked`) once
   it hears your Dante speakers.
4. Send the Mac's sound to Dante. Click the **Virgil** icon in the menu bar
   and choose **Desktop audio…**. Click **Add…** and pick **Default output
   device**, or one app such as **Spotify** or **Safari**. Set the channel
   to **1**. The first time, macOS asks whether Virgil Control may record
   this computer's audio: click **Allow**. This step needs macOS 14.2 or
   later.
5. Route it in **Dante Controller** as in step 5 for Windows.
6. Play something. The meters on transmit 1 and 2 move and the speakers
   play.

Good to know:

- The sound also keeps playing on the computer's own speakers. Turn those
  down; it does not change what goes to Dante.
- Sound through Desktop audio is about 60 to 80 ms late. That is fine for
  music and video, not for playing an instrument live.
- Virgil starts with the computer, so after a restart there is nothing to
  do.

### B. A DanteStreamer box on the network

The box's control panel only answers on the box itself until you turn on
remote access. You do that once, on the box.

**On the DanteStreamer box** (in the folder with `docker-compose.yml`):

1. Open the `.env` file in a text editor, for example `nano .env`. If there
   is no `.env` yet, copy the example first: `cp .env.example .env`.
2. Add a line with a password of at least 8 characters, without spaces:

   ```
   REMOTE_PASSWORD=choose-a-password
   ```

3. Save the file and apply it:

   ```bash
   docker compose up -d
   ```

   The log (`docker compose logs`) now says "Remote access on".

**In DanteStreamer Controller** (Windows or Mac):

1. Click **+ Add** (Windows) or the **+** button (Mac).
2. Click **Find on network**. The app lists the DanteStreamer boxes it
   finds and fills in the first one. If nothing shows up, type the box's IP
   address in **Host or IP**.
3. Keep port **8480**. Type the password from step 2 and click **Save**.
4. The Status tab fills in within a second.

The password goes over the network unencrypted (plain HTTP). Use this on
your own network or through a VPN, not across the internet.

Without remote access, an SSH tunnel also works: run
`ssh -L 8480:127.0.0.1:8480 <user>@<box>` on your computer, keep it open,
and add host `localhost` without a password.

### When it does not connect

The app shows a red line at the top. What it means:

| The app says | Do this |
|---|---|
| Virgil is not running on this computer | Install Virgil (setup A, step 1). If it is installed, start *Virgil Control* from the Start menu or Applications. |
| *Host* does not accept connections on port 8480 | Remote access is off on the box. Do setup B on the box, then try again. |
| Wrong or missing password | Select the host, click **Edit** and type `REMOTE_PASSWORD` from the box's `.env` file. |
| Too many wrong passwords | Wait a minute, then fix the password. |
| Cannot reach *host* (timed out) | The box is off, on another network, or the IP address changed. Click **Find on network** again. |
| No DanteStreamer found | The box is off or on another network segment. Type its IP address instead; your router's list of devices shows it. |
| Clock stays `free-run` or `stopped` | Virgil does not hear a Dante clock. Check that the speakers are on and on the same network, and that the computer uses the wired adapter (Virgil's *Settings…*). |

## Where the app keeps its settings

- Windows: `%APPDATA%\DanteStreamerController\instances.json`. Passwords in
  it are encrypted for your Windows user.
- macOS: the app's user defaults; passwords are in the login keychain.

## Try the app without Dante equipment

`tools/mock_virgil.py` answers like Virgil, with moving meters on transmit 1
and 2. Run it on any computer with Python 3 and add that computer's IP:

```bash
python3 dantestreamer-desktop/tools/mock_virgil.py                    # port 8480, no password
python3 dantestreamer-desktop/tools/mock_virgil.py --password testtest
```

## Building

See [macos/README.md](macos/README.md) and
[windows/README.md](windows/README.md). The CI workflow is
`.github/workflows/build-desktop.yml`. Each push to `main` that touches
this folder builds both apps and publishes a prerelease
`desktop-v1.0.<run>`.

The macOS job uses these repository secrets (Settings, Secrets and
variables, Actions):

| Secret | Used for |
|---|---|
| `DEVELOPER_ID_CERT_BASE64`, `DEVELOPER_ID_CERT_PASSWORD` | The Developer ID Application certificate (.p12, base64) and its password. Required. |
| `DEVELOPER_ID_TEAM` or `APPLE_TEAM_ID` | Team ID, part of the certificate name. Required. |
| `APPLE_ID`, `APPLE_APP_PASSWORD` | Notarization with an Apple ID and an app-specific password from appleid.apple.com. The same secrets `installers.yml` uses. |
| `APPLE_API_KEY_ID`, `APPLE_API_ISSUER_ID`, `APPLE_API_KEY_BASE64` | Notarization with an App Store Connect API key instead (the .p8 file in base64). |

Without one of the two notarization sets, the job signs the app, skips
notarization and shows a warning on the run page.

## License

GPLv3, same as DanteStreamer.
