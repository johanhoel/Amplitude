# Installers for Windows and Mac

CamWatch, Home Deck and DanteStreamer run on Linux.
These installers set up a small Linux system on a Windows PC or a Mac and install the project in it.
You download one file and double-click it.

| Project | Windows | Mac |
|---|---|---|
| CamWatch | `CamWatch-Setup.exe` | `CamWatch.dmg` |
| Home Deck | `HomeDeck-Setup.exe` | `HomeDeck.dmg` |
| DanteStreamer | `DanteStreamer-Setup.exe` | `DanteStreamer.dmg` |

The files are on the [Releases page](https://github.com/johanhoel/amplitude/releases).

> ⚠️ DanteStreamer needs direct access to the network for its clock (PTP) and its audio.
> In WSL and in a Mac virtual machine, audio can drop out or stay silent. A Linux computer or a Raspberry Pi works better.

## Windows 10 (version 2004 or newer) and Windows 11

1. Run `<Project>-Setup.exe`.
2. Windows shows **Windows protected your PC**, because the file is not signed.
   Click **More info**, then **Run anyway**.
3. Windows asks for administrator rights. Click **Yes**.
4. Without WSL on the PC, the installer adds it, and Windows restarts once.
   After the restart, the installer goes on by itself.
5. The installer downloads Ubuntu and installs the project. The first time takes 5 to 20 minutes.
6. At the end, the browser opens the project. A shortcut is on the desktop.
   CamWatch also shows its login. The installer keeps it in `/root/camwatch-login.txt` in the Linux system.

What the installer sets up:
- A Linux system in WSL with the project's name, e.g. `CamWatch`. Its files are in `%LOCALAPPDATA%\Amplitude\CamWatch`.
- A hidden task that starts it when you log in.
- `networkingMode=mirrored` in `%USERPROFILE%\.wslconfig`, so phones reach the project through the PC's address.
  This needs Windows 11 22H2 or newer. On Windows 10, only the PC itself reaches the project.
- An entry in **Settings → Apps**. **Uninstall** removes everything, recordings included.

Run the installer again to update the project. The settings stay.

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

On Apple Silicon, the projects run as arm64. CamWatch and DanteStreamer have had little testing there.

## For the developer: building and signing

The workflow `.github/workflows/installers.yml` builds all six files:
- **Run it by hand:** Actions → installers → Run workflow. The files are under the run's **Artifacts**.
- **Publish a release:** push a tag like `installers-v1`. The files then appear on the Releases page.

The Windows files are not signed. The Mac files are signed and notarized when these repository secrets exist
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
