#!/usr/bin/env python3
"""The host helper behind Settings -> Updates and Settings -> Storage. Runs on the host, not in a container.

systemd starts it (camwatch-update.path watches DATA_PATH/update/request.json, see extras/install-updater.sh). The web
UI cannot run Docker or mount disks, so it writes a request and this script does the work:
  {"action": "update", "sha"}     download that commit from GitHub with the access key saved in Settings, take the
                                  CamWatch folder out of it and pipe it into that version's extras/release.sh, which
                                  keeps a backup and rolls back by itself. Progress: update/status.json.
  {"action": "storage", "path", "copy", "network": {...} or absent}
                                  move the recordings: mount the network share first when one is given (NFS or SMB,
                                  kept in /etc/fstab, Docker waits for it at boot), copy the recordings (rsync), stop,
                                  copy the newest clips, point RECORDINGS_PATH in .env there, start. Switches back
                                  when the start fails. The old copy stays. Progress: update/storage.json.
  {"action": "disks"}             only refresh update/host.json: disks, the recordings folder, whether mounting works.

    update.py /opt/camwatch            handle a waiting request (what systemd runs)
    update.py /opt/camwatch --hello    only write "helper installed" (deploy.sh and release.sh run this)
Standard library only (the host's python3).
"""
import datetime as dt
import io
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

DIR = Path(sys.argv[1] if len(sys.argv) > 1 else "/opt/camwatch")
HELLO = "--hello" in sys.argv


def env_value(name, default=""):
    value = ""
    try:
        for line in (DIR / ".env").read_text(encoding="utf-8").splitlines():
            if line.startswith(f"{name}="):
                value = line.split("=", 1)[1].strip()
    except OSError:
        pass
    return value or default


DATA = Path(env_value("DATA_PATH", "/mnt/hdd/camwatch/data"))
UPDATE = DATA / "update"
REQUEST, STATUS = UPDATE / "request.json", UPDATE / "status.json"
STORAGE, HOST = UPDATE / "storage.json", UPDATE / "host.json"
SYSTEM_DIRS = {"bin", "boot", "dev", "etc", "lib", "lib32", "lib64", "proc", "run", "sbin", "sys", "usr", "var", "tmp"}
NET_ROOT = Path("/mnt/camwatch-net")
TARGET = "production" if DIR == Path("/opt/camwatch") else "staging"


def now():
    return dt.datetime.now().isoformat(timespec="seconds")


def write_json(path, data):
    UPDATE.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def status(path=STATUS, **changes):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    data.update(changes, helper=True)
    write_json(path, data)


def source():
    """Repository, folder and access key as saved in Settings -> Updates (settings.json)."""
    try:
        saved = json.loads((DATA / "settings.json").read_text(encoding="utf-8")).get("update") or {}
    except (OSError, ValueError):
        saved = {}
    return saved.get("repo") or "johanhoel/Amplitude", saved.get("folder") or "CamWatch", saved.get("token") or ""


def download(repo, sha, token):
    tarball = os.environ.get("UPDATE_TARBALL")      # tests: a local file instead of GitHub
    if tarball:
        return Path(tarball).read_bytes()
    req = urllib.request.Request(f"https://api.github.com/repos/{repo}/tarball/{sha}",
                                 headers={"Accept": "application/vnd.github+json", "User-Agent": "camwatch-updater",
                                          **({"Authorization": f"Bearer {token}"} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return r.read()
    except urllib.error.HTTPError as exc:
        if token and exc.code in (401, 403):
            return download(repo, sha, "")      # an old or wrong key: a public repository answers without one
        hint = " - check the access key in Settings -> Updates" if exc.code in (401, 403, 404) else ""
        raise RuntimeError(f"GitHub answered {exc.code} for commit {sha[:7]}{hint}") from None
    except OSError as exc:
        raise RuntimeError(f"GitHub is not reachable: {exc}") from None


def folder_tar(data, folder):
    """The project folder out of GitHub's tarball (<repo>-<sha>/<folder>/...), as a tar of its contents."""
    out = io.BytesIO()
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as src, tarfile.open(fileobj=out, mode="w") as dst:
        found = False
        for m in src.getmembers():
            parts = m.name.split("/", 2)
            if len(parts) < 3 or parts[1] != folder or not parts[2]:
                continue
            if m.issym() or m.islnk() or ".." in parts[2].split("/"):
                continue
            found = True
            m.name = parts[2]
            dst.addfile(m, src.extractfile(m) if m.isfile() else None)
    if not found:
        raise RuntimeError(f"the download has no {folder}/ folder")
    return out.getvalue()


def disks():
    """The host's disks as df sees them, without system, Docker and boot mounts."""
    try:
        out = subprocess.run(["df", "-PT", "-B1", "-x", "tmpfs", "-x", "devtmpfs", "-x", "overlay", "-x", "squashfs",
                              "-x", "efivarfs"], capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    found = []
    for line in out.splitlines()[1:]:
        parts = line.split(None, 6)
        if len(parts) < 7 or not parts[2].isdigit():
            continue
        device, fs, size, _, free, _, mount = parts
        if mount.startswith(("/boot", "/var/lib/docker", "/run", "/snap", "/proc", "/sys", "/dev")):
            continue
        found.append({"mount": mount, "fs": fs, "device": device, "size": int(size), "free": int(free),
                      "network": fs in ("nfs", "nfs4", "cifs", "smb3", "fuse.sshfs")})
    return found


def can_mount():
    """(True, "") when this host may mount NFS/SMB shares; else (False, why). Unprivileged LXC containers may not."""
    try:
        first = Path("/proc/self/uid_map").read_text().split()
        if first[:2] != ["0", "0"]:
            return False, "lxc-unprivileged"
    except (OSError, IndexError):
        pass
    if getattr(os, "geteuid", lambda: 0)() != 0:
        return False, "not-root"
    return True, ""


def write_host():
    ok, why = can_mount()
    write_json(HOST, {"at": now(), "recordings": env_value("RECORDINGS_PATH", "/mnt/hdd/camwatch/recordings"),
                      "disks": disks(), "can_mount": ok, "mount_problem": why, "hostname": platform.node()})


def set_env(name, value):
    """Set NAME=value in .env (keeps the other lines; the file stays readable by root only)."""
    path = DIR / ".env"
    lines, done = [], False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{name}="):
            if not done:
                lines.append(f"{name}={value}")
                done = True
            continue
        lines.append(line)
    if not done:
        lines.append(f"{name}={value}")
    tmp = path.with_suffix(".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def compose(*args, timeout=1800):
    return subprocess.run(["docker", "compose", *args], cwd=DIR, capture_output=True, text=True, timeout=timeout)


def healthy(tries=60):
    """Every container up, those with a healthcheck healthy (like release.sh)."""
    import time
    states = ""
    for _ in range(tries):
        states = compose("ps", "-a", "--format", "{{.Name}} {{.Status}}", timeout=60).stdout
        if states and not any(w in states for w in ("health: starting", "unhealthy", "Restarting", "Exited", "Created")):
            return True, states
        time.sleep(5)
    return False, states


def copy_tree(old, new, step):
    """rsync old/ into new/, with the percentage in storage.json."""
    import re
    import time
    proc = subprocess.Popen(["rsync", "-rlt", "--info=progress2", "--no-inc-recursive", f"{old}/", f"{new}/"],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    last, buf = 0.0, b""
    while True:
        chunk = proc.stdout.read(4096)
        if not chunk:
            break
        buf = (buf + chunk)[-400:]
        found = re.findall(rb"(\d+)%", buf)
        if found and time.time() - last > 5:
            last = time.time()
            status(STORAGE, message=f"{step}: {int(found[-1])}% copied")
    err = proc.stderr.read().decode(errors="replace")
    if proc.wait() != 0:
        raise RuntimeError(f"copying failed: {err.strip()[-300:]}")


def check_target(new, old):
    if not (new.is_absolute() or new.as_posix().startswith("/")) or ".." in new.parts:
        return "enter a full folder path, e.g. /mnt/disk2/camwatch/recordings"
    if len(new.parts) < 3 or new.parts[1] in SYSTEM_DIRS:
        return f"{new} is a system folder - pick a folder on a data disk"
    if new == old:
        return "the recordings are in this folder already"
    if old in new.parents or new in old.parents:
        return "the new folder cannot be inside the old one (or the other way round)"
    if new == DATA or DATA in new.parents or new in DATA.parents:
        return "pick a folder outside the data folder"
    return None


def apt_install(package):
    status(STORAGE, message=f"installing {package}")
    env = {**os.environ, "DEBIAN_FRONTEND": "noninteractive"}
    for cmd in (["apt-get", "update", "-q"], ["apt-get", "install", "-y", "-q", package]):
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=900, env=env)
        if p.returncode != 0:
            raise RuntimeError(f"installing {package} failed: {(p.stderr or p.stdout).strip()[-300:]}")


def mount_share(net):
    """Mount an NFS or SMB share under /mnt/camwatch-net/<name>, kept in /etc/fstab. Returns the mount folder."""
    import re
    ok, why = can_mount()
    if not ok:
        raise RuntimeError("this server cannot mount network shares (an unprivileged Proxmox container) - "
                           "mount the share on the Proxmox host and pass it in, as Settings -> Storage shows")
    kind, server, share = net.get("kind"), str(net.get("server", "")).strip(), str(net.get("share", "")).strip().strip("/")
    if kind not in ("nfs", "smb") or not re.fullmatch(r"[A-Za-z0-9.:\[\]-]{1,253}", server) \
            or not re.fullmatch(r"[\w .$/-]{1,200}", share) or ".." in share.split("/"):
        raise RuntimeError("check the server and the share name")
    name = re.sub(r"[^a-z0-9]+", "-", f"{server}-{share}".lower()).strip("-")[:60]
    point = NET_ROOT / name
    point.mkdir(parents=True, exist_ok=True)
    if kind == "nfs":
        if not shutil.which("mount.nfs"):
            apt_install("nfs-common")
        source, fstype, opts = f"{server}:/{share}", "nfs", "_netdev,nofail,hard,timeo=150"
    else:
        if not shutil.which("mount.cifs"):
            apt_install("cifs-utils")
        cred = Path("/etc/camwatch") / f"smb-{name}.cred"
        cred.parent.mkdir(mode=0o700, exist_ok=True)
        cred.write_text(f"username={net.get('user', '')}\npassword={net.get('password', '')}\n", encoding="utf-8")
        os.chmod(cred, 0o600)
        source, fstype = f"//{server}/{share.replace(' ', chr(92) + '040')}", "cifs"
        opts = f"_netdev,nofail,credentials={cred},uid=0,gid=0,file_mode=0660,dir_mode=0770"
    line = f"{source} {point} {fstype} {opts} 0 0"
    fstab = Path("/etc/fstab")
    lines = [l for l in fstab.read_text(encoding="utf-8").splitlines() if f" {point} " not in l]
    fstab.write_text("\n".join(lines + [f"# camwatch network storage (Settings -> Storage)", line]) + "\n", encoding="utf-8")
    subprocess.run(["systemctl", "daemon-reload"], capture_output=True, timeout=60)
    if subprocess.run(["mountpoint", "-q", str(point)]).returncode != 0:
        status(STORAGE, message=f"connecting to {source}")
        p = subprocess.run(["mount", str(point)], capture_output=True, text=True, timeout=120)
        if p.returncode != 0:
            fstab.write_text("\n".join(lines) + "\n", encoding="utf-8")       # don't keep a share that doesn't work
            raise RuntimeError(f"connecting to {source} failed: {(p.stderr or p.stdout).strip()[-300:]}")
    # Docker starts the containers only once the share is there: else they would record onto the empty folder
    dropin = Path("/etc/systemd/system/docker.service.d/camwatch-storage.conf")
    dropin.parent.mkdir(parents=True, exist_ok=True)
    dropin.write_text(f"# written by camwatch (Settings -> Storage)\n[Unit]\nRequiresMountsFor={point}\n", encoding="utf-8")
    subprocess.run(["systemctl", "daemon-reload"], capture_output=True, timeout=60)
    return point


def move_storage(req):
    old = Path(env_value("RECORDINGS_PATH", "/mnt/hdd/camwatch/recordings"))
    copy = req.get("copy", True) is not False
    status(STORAGE, state="running", old=str(old), path=None, started=now(), finished=None, message="starting", log="")
    stopped = switched = False
    try:
        if req.get("network"):
            new = mount_share(req["network"]) / "camwatch-recordings"
        else:
            new = Path(str(req.get("path", "")).rstrip("/") or "/")
        status(STORAGE, path=str(new), message="checking the new folder")
        problem = check_target(new, old)
        if problem:
            raise RuntimeError(problem)
        new.mkdir(parents=True, exist_ok=True)
        probe = new / ".camwatch-write-test"
        probe.write_text("ok")
        probe.unlink()
        if copy and old.is_dir():
            need = int(subprocess.run(["du", "-sb", str(old)], capture_output=True, text=True,
                                      timeout=3600).stdout.split()[0] or 0)
            free = shutil.disk_usage(new).free
            if need > free * 0.95:
                raise RuntimeError(f"not enough space: the recordings need {need / 1e9:.1f} GB, "
                                   f"the new place has {free / 1e9:.1f} GB free")
            copy_tree(old, new, "copy 1 of 2 (CamWatch keeps recording)")
        status(STORAGE, message="stopping CamWatch for a moment")
        compose("stop")
        stopped = True
        if copy and old.is_dir():
            copy_tree(old, new, "copy 2 of 2 (the newest clips)")
        set_env("RECORDINGS_PATH", str(new))
        switched = True
        status(STORAGE, message="starting CamWatch with the new folder")
        compose("up", "-d", "--remove-orphans")
        good, states = healthy()
        if not good:
            raise RuntimeError("CamWatch did not start with the new folder\n" + states)
        write_host()
        kept = f" The old copy stays in {old}: delete it when you are sure." if copy and old.is_dir() else ""
        status(STORAGE, state="done", finished=now(), message=f"the recordings are now in {new}.{kept}")
        return 0
    except (RuntimeError, OSError, ValueError, IndexError, subprocess.SubprocessError) as exc:
        if switched:
            set_env("RECORDINGS_PATH", str(old))
        if stopped:
            compose("up", "-d", "--remove-orphans")
        back = " CamWatch uses the old folder again." if stopped else " Nothing changed."
        status(STORAGE, state="failed", finished=now(), message=f"{str(exc).splitlines()[0]}.{back}",
               log=str(exc)[-3000:])
        return 1
    finally:
        write_host()


def update(req):
    sha = str(req.get("sha", ""))
    if not (7 <= len(sha) <= 40 and all(c in "0123456789abcdef" for c in sha)):
        status(state="failed", finished=now(), message=f"not a commit: {sha!r}")
        return 1
    repo, folder, token = source()
    status(state="running", sha=sha, version=req.get("version", ""), started=now(), finished=None,
           message=f"downloading {sha[:7]} from GitHub", log="")
    try:
        code = folder_tar(download(repo, sha, token), folder)
        with tarfile.open(fileobj=io.BytesIO(code)) as t:
            release = t.extractfile("extras/release.sh").read()
        script = Path(tempfile.mkdtemp(prefix="camwatch-update-")) / "release.sh"
        script.write_bytes(release)
        status(message="installing: backup, build, start, health check (a few minutes)")
        proc = subprocess.run([shutil.which("bash") or "bash", str(script), TARGET], input=code, capture_output=True, timeout=3600)
        log = (proc.stdout + proc.stderr).decode(errors="replace")[-6000:]
        if proc.returncode == 0:
            status(state="done", finished=now(), message=f"updated to {req.get('version', '')} ({sha[:7]})", log=log)
            return 0
        rolled = "rolled back" in log
        status(state="failed", finished=now(), log=log,
               message="the new version did not start - " + ("the previous version runs again" if rolled else "see the log"))
        return 1
    except (RuntimeError, OSError, tarfile.TarError, KeyError, subprocess.SubprocessError) as exc:
        status(state="failed", finished=now(), message=str(exc))
        return 1


def main():
    write_host()
    if HELLO:
        status(hello=now())
        return 0
    try:
        req = json.loads(REQUEST.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    REQUEST.unlink(missing_ok=True)       # systemd's path unit fires while the file exists (it may hold a password)
    action = req.get("action", "update")
    if action == "disks":
        return 0
    if action == "storage":
        return move_storage(req)
    return update(req)


if __name__ == "__main__":
    sys.exit(main())
