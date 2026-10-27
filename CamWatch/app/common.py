"""Shared helpers: env config, logging, ntfy client, recording retention."""
import base64
import functools
import json
import logging
import os
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

VIDEO_EXT = {".mp4", ".mkv"}


def env(name, default=None, cast=str):
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    try:
        return cast(value.strip())
    except ValueError:
        raise SystemExit(f"Invalid value for {name}: {value!r}")


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def setup_logging(name):
    logging.basicConfig(
        level=env("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    return logging.getLogger(name)


def _header(value):
    """ntfy accepts RFC 2047 encoded headers for non-ASCII text (e.g. names with å/ø/é)."""
    value = value.replace("\n", " ")
    if value.isascii():
        return value
    return "=?UTF-8?B?" + base64.b64encode(value.encode()).decode() + "?="


class Ntfy:
    """ntfy server, topic and login come from the Settings page (else .env) and are re-read when they change."""

    def __init__(self, log):
        self.log = log
        self.conf_mtime = None
        self.last_error = None
        self._refresh()
        if not self.topic:
            log.warning("no ntfy topic set (Settings -> Notifications) - notifications disabled")

    def _refresh(self):
        import settings  # settings imports common
        mtime = settings.mtime()
        if mtime == self.conf_mtime:
            return
        self.conf_mtime = mtime
        cfg = settings.ntfy()
        self.base, self.topic, self.token = cfg["url"], cfg["topic"], cfg["token"]
        self.user, self.password = cfg["user"], cfg["password"]
        # Health messages (camera offline, recording stalled) can go to their own topic so that
        # dashboards watching the alert topic only react to detections. Empty = the alert topic.
        self.status_topic = cfg["status_topic"] or self.topic
        self.alert_priority = cfg["priority"]   # detections; other messages choose their own

    def status(self, message, title, tags="warning", priority="default"):
        self._refresh()
        """A system-health message: tagged "status", sent to NTFY_STATUS_TOPIC if set."""
        return self.send(message, title=title, tags=f"status,{tags}", priority=priority, topic=self.status_topic)

    def _auth(self):
        if self.token:
            return {"Authorization": f"Bearer {self.token}"}
        if self.user and self.password:
            raw = f"{self.user}:{self.password}".encode()
            return {"Authorization": "Basic " + base64.b64encode(raw).decode()}
        return {}

    def send(self, message, title=None, tags=None, priority=None, image=None, filename="snapshot.jpg", click=None,
             topic=None, actions=()):
        """Publish a notification. `image` is JPEG bytes sent as an attachment, `click` a URL opened on tap,
        `actions` extra ntfy action buttons ("http, Label, URL, method=POST")."""
        self._refresh()
        topic = topic or self.topic
        if not topic:
            self.last_error = "no topic set"
            return False
        url = f"{self.base}/{urllib.parse.quote(topic)}"
        headers = self._auth()
        if title:
            headers["Title"] = _header(title)
        if tags:
            headers["Tags"] = tags
        if priority:
            headers["Priority"] = str(priority)
        buttons = list(actions)
        if click:
            headers["Click"] = click
            buttons.insert(0, f"view, Open clip, {click}")
        if buttons:
            headers["Actions"] = "; ".join(buttons[:3])   # ntfy shows at most 3

        attempts = []
        if image:
            attempts.append(("PUT", image, {**headers, "Filename": filename, "Message": _header(message)}))
        attempts.append(("POST", message.encode(), headers))

        for method, body, hdrs in attempts:
            req = urllib.request.Request(url, data=body, headers=hdrs, method=method)
            try:
                with urllib.request.urlopen(req, timeout=20) as resp:
                    resp.read()
                self.last_error = None
                return True
            except (urllib.error.URLError, OSError) as exc:
                self.last_error = str(exc)
                self.log.warning("ntfy %s failed: %s", "attachment" if method == "PUT" else "message", exc)
        return False


APP_DIR = Path(__file__).resolve().parent


@functools.lru_cache(maxsize=1)
def app_version():
    """{"version", "commit", "date", "text"}. The version is app/VERSION (bumped for each release); the commit comes
    from app/BUILD, which `git archive` fills in for every release, or from git itself in a development checkout."""
    def read(name):
        try:
            return (APP_DIR / name).read_text(encoding="utf-8").strip()
        except OSError:
            return ""
    version = read("VERSION") or "dev"
    commit, date = "", ""
    build = read("BUILD")
    if build and not build.startswith("$Format"):
        commit, _, date = build.partition(" ")
    else:
        import subprocess
        try:
            out = subprocess.run(["git", "log", "-1", "--format=%h %cs"], cwd=APP_DIR, capture_output=True, text=True,
                                 timeout=5)
            if out.returncode == 0 and out.stdout.strip():
                commit, _, date = out.stdout.strip().partition(" ")
        except (OSError, subprocess.SubprocessError):
            pass
    text = f"{version} ({commit})" if commit else version
    return {"version": version, "commit": commit, "date": date, "text": text}


def clip_url(day, stem):
    base = env("WEB_BASE_URL", "")
    return f"{base.rstrip('/')}/clip/{day}/{urllib.parse.quote(stem)}" if base else None


def delete_event(folder, stem, log):
    """Remove a recording plus its sidecars (.jpg, .json, .faces.json, .labels.json, …) and face/plate crops."""
    for sibling in folder.iterdir():
        if sibling.is_file() and sibling.name.startswith(stem + "."):
            sibling.unlink(missing_ok=True)
    for crops in (folder / f"{stem}_faces", folder / f"{stem}_plates"):
        if crops.is_dir():
            shutil.rmtree(crops, ignore_errors=True)
    log.info("deleted recording %s/%s", folder.name, stem)


def _identified(folder, stem):
    """True if someone was recognised automatically or tagged by hand."""
    for name, key in ((f"{stem}.faces.json", "known"), (f"{stem}.labels.json", None)):
        try:
            data = json.loads((folder / name).read_text())
        except (FileNotFoundError, ValueError):
            continue
        if (data.get(key) if key else data):
            return True
    return False


def prune_recordings(rec_dir, retention_days, keep_days, min_free_gb, log):
    """Starred clips are never deleted. Clips with identified people are kept `keep_days`,
    others `retention_days`. When disk space runs low, plain clips go first (oldest first)."""
    rec_dir = Path(rec_dir)
    plain, identified = [], []
    for p in rec_dir.rglob("*"):
        if p.suffix.lower() not in VIDEO_EXT or not p.is_file():
            continue
        stem = p.name[: -len(p.suffix)]
        if (p.parent / f"{stem}.star").exists():
            continue
        try:
            entry = (p.stat().st_mtime, p.parent, stem)
        except FileNotFoundError:
            continue
        (identified if _identified(p.parent, stem) else plain).append(entry)

    now = time.time()
    remaining = []
    for clips, days in ((plain, retention_days), (identified, keep_days)):
        for mtime, folder, stem in sorted(clips):
            if days > 0 and mtime < now - days * 86400:
                delete_event(folder, stem, log)
            else:
                remaining.append((clips is identified, mtime, folder, stem))

    for _, _, folder, stem in sorted(remaining):  # plain before identified, oldest first
        if min_free_gb <= 0 or shutil.disk_usage(rec_dir).free / 1e9 >= min_free_gb:
            break
        delete_event(folder, stem, log)

    for day in rec_dir.iterdir():
        if day.is_dir() and not any(day.iterdir()):
            day.rmdir()
