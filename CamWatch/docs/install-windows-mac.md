# CamWatch on Windows and macOS

CamWatch runs on Linux.
On Windows and on a Mac, you run it in a small Linux system on the same computer.
The steps below set that up.

> ⚠️ These two ways are not tested as much as a Linux server.
> Please report what works and what does not: **💡 Request a feature** at the bottom of every CamWatch page.

## Before you start

- **The computer must stay on.** CamWatch records only while the computer runs. Switch off sleep mode.
- **Use a wired network if you can.** A camera stream needs a steady connection.
- **Disk space:** plan about 10–30 GB per camera per week. It depends on the camera.
- **Camera search does not work here.** The search in Settings cannot see through the Linux layer.
  Enter the camera's address yourself, or use **Find** with the camera's IP address.

## Windows 10 and 11

Windows has a built-in Linux system: WSL.

1. Open **PowerShell as administrator** and install Ubuntu:

   ```powershell
   wsl --install -d Ubuntu-24.04
   ```

   Restart the computer when Windows asks.
   Ubuntu then opens and asks for a user name and a password. Choose them.

2. Let phones and other computers reach CamWatch.
   Create the file `C:\Users\<you>\.wslconfig` with this text:

   ```ini
   [wsl2]
   networkingMode=mirrored
   ```

   Then run `wsl --shutdown` in PowerShell and open Ubuntu again.

3. In Ubuntu, switch on systemd. The update button and Storage need it:

   ```bash
   printf '[boot]\nsystemd=true\n' | sudo tee /etc/wsl.conf
   ```

   Run `wsl --shutdown` in PowerShell and open Ubuntu again.

4. In Ubuntu, install CamWatch as on a Linux server (see the README, **Install**):

   ```bash
   sudo apt update && sudo apt install -y git mariadb-server
   git clone https://github.com/johanhoel/amplitude.git && cd amplitude/CamWatch
   cp .env.example .env && nano .env
   sudo ./deploy.sh
   ```

   Put the recordings on a Windows disk with lots of space, e.g. `RECORDINGS_PATH=/mnt/d/camwatch/recordings` for drive D.

5. Open `http://localhost:8080` on the Windows computer.
   Other devices use the computer's address, e.g. `http://192.168.1.20:8080`.
   Windows Firewall asks once. Allow private networks.

6. Start CamWatch when Windows starts:
   open **Task Scheduler**, create a task **At log on** that runs `wsl.exe -d Ubuntu-24.04 --exec true`.
   Docker in Ubuntu then starts CamWatch by itself.

## macOS (Intel and Apple Silicon)

On a Mac, a small Ubuntu machine runs in **Multipass**, a free tool from Ubuntu.

1. Install Multipass from <https://multipass.run> (or `brew install multipass`).

2. Create the Ubuntu machine. `en0` is the Mac's network; use `en1` when the Mac uses Wi-Fi on that port.
   The machine then gets its own address on your home network, so phones and cameras reach it:

   ```bash
   multipass launch 24.04 --name camwatch --cpus 4 --memory 4G --disk 200G --network en0
   ```

3. Open the machine and install CamWatch as on a Linux server (see the README, **Install**):

   ```bash
   multipass shell camwatch
   sudo apt update && sudo apt install -y git mariadb-server
   git clone https://github.com/johanhoel/amplitude.git && cd amplitude/CamWatch
   cp .env.example .env && nano .env
   sudo ./deploy.sh
   ```

4. Find the machine's address and open CamWatch:

   ```bash
   multipass info camwatch
   ```

   Use the address on your home network (not the 192.168.64.x one), e.g. `http://192.168.1.30:8080`.

5. The recordings live inside the machine (the 200 GB from step 2).
   To use an external disk or a NAS, use **Settings → Storage → Network share**.

6. After a restart of the Mac, check that the machine runs: `multipass list`.
   When it says Stopped, run `multipass start camwatch`. Docker then starts CamWatch by itself.

## Updates

Updates work the same everywhere: **Settings → Updates → Update now**,
or the green **⬆ Update** button in the top bar.
