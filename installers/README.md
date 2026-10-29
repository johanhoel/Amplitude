# Installers for Mac, and the Linux script behind them

CamWatch, Home Deck and DStreamer run on Linux.
The Mac installer sets up a small Linux machine and installs the project in it.
You download one file and double-click it.

| Project | Mac |
|---|---|
| CamWatch | `CamWatch.dmg` |
| Home Deck | `HomeDeck.dmg` |
| DStreamer | `DStreamer.dmg` |

The files are on the [Releases page](https://github.com/johanhoel/amplitude/releases).
On a Linux machine or a Raspberry Pi, skip all of this and run
[`linux/setup.sh`](linux/setup.sh) directly.

## There is no Windows installer

There was one, and it is gone on purpose.

DStreamer needs direct access to the network for its PTP clock and its audio.
and the audio arrives with gaps - measured at roughly 2 ms, several times a
minute, which is audible. No setting closes that, because the clock cannot
see the wire.

CamWatch and Home Deck would have worked, but keeping a Windows path alive
for two of three projects meant maintaining an installer nobody could test
without a Windows machine - and the one bug it did ship, a version check that
that reason.

> DStreamer in a Mac virtual machine has the same problem in a milder form.
> For anything you actually listen to, use a Linux box or a Raspberry Pi.

## macOS (Intel and Apple Silicon)

1. Open `<Project>.dmg` and drag the app to **Applications**.
2. Open the app. Terminal opens and shows the progress.
3. Without Multipass on the Mac, the installer adds it. macOS asks for your password once.
4. The installer creates a Linux machine named after the project and installs the project in it.
   The first time takes 5 to 20 minutes.
5. At the end, the browser opens the project.

The Linux machine gets its own address on your home network, so phones and cameras reach it.
After a restart of the Mac, open the app again and choose **1** to start and update it.
Choose **2** to remove the project with all its data.

On Apple Silicon, the projects run as arm64. CamWatch and DStreamer have had little testing there.

## For the developer: building and signing

The workflow `.github/workflows/installers.yml` builds all six files:
- **Run it by hand:** Actions → installers → Run workflow. The files are under the run's **Artifacts**.
- **Publish a release:** push a tag like `installers-v1`. The files then appear on the Releases page.

The Mac files are signed and notarized when these repository secrets exist
(Settings → Secrets and variables → Actions):

| Secret | What it is |
|---|---|
| `MACOS_CERT_P12` | Your **Developer ID Application** certificate with its private key, exported from Keychain Access as `.p12`, then base64: `base64 -i cert.p12 \| pbcopy` |
| `MACOS_CERT_PASSWORD` | The password you chose for the `.p12` export |
| `APPLE_ID` | The email address of your Apple developer account |
| `APPLE_TEAM_ID` | Your team ID, from developer.apple.com → Membership |
| `APPLE_APP_PASSWORD` | An app-specific password from appleid.apple.com → Sign-In and Security |

To get the certificate: developer.apple.com → Certificates → **+** → **Developer ID Application**.
Create it with a request from Keychain Access, download it and double-click it.
Then export it from Keychain Access (**My Certificates**) as `.p12`.

All installers run [`linux/setup.sh`](linux/setup.sh) inside the Linux system.
You can also use it directly on a Debian or Ubuntu machine:

```bash
curl -fsSL https://raw.githubusercontent.com/johanhoel/amplitude/main/installers/linux/setup.sh | sudo bash -s camwatch
```
