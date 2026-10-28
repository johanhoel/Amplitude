#!/usr/bin/env python3
"""Update CamWatch from GitHub when Settings -> Updates asks for it. Runs on the host, not in a container.

systemd starts it (camwatch-update.path watches DATA_PATH/update/request.json, see extras/systemd/). It reads the
request (which commit), downloads that commit from GitHub with the access key saved in Settings, takes the CamWatch
folder out of it and pipes it into that version's extras/release.sh, which keeps a backup and rolls back by itself.
Progress goes to DATA_PATH/update/status.json, which the web UI shows.

    update.py /opt/camwatch            handle a waiting request (what systemd runs)
    update.py /opt/camwatch --hello    only write "helper installed" into status.json (deploy.sh runs this)
Standard library only (the host's python3).
"""
import datetime as dt
import io
import json
import os
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
TARGET = "production" if DIR == Path("/opt/camwatch") else "staging"


def now():
    return dt.datetime.now().isoformat(timespec="seconds")


def status(**changes):
    UPDATE.mkdir(parents=True, exist_ok=True)
    try:
        data = json.loads(STATUS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    data.update(changes, helper=True)
    tmp = STATUS.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, STATUS)


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


def main():
    if HELLO:
        status(hello=now())
        return 0
    try:
        req = json.loads(REQUEST.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    REQUEST.unlink(missing_ok=True)       # systemd's path unit fires while the file exists
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


if __name__ == "__main__":
    sys.exit(main())
