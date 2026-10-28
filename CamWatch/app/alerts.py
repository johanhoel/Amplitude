"""Push alert helpers shared by the recorders (one per camera) and the web UI.

  * Snooze: no pushes from one camera until a time (settings "snooze": {camera: epoch}); recording and Home
    Assistant carry on.
  * Action links: the Star / Snooze buttons on a push call the web UI without a login. Each link is signed
    (HMAC, secret in DATA_DIR/action_secret) for one action on one clip and expires after ACTION_HOURS.
  * One visit, one push: someone walking past several cameras within MERGE_SECONDS gets one push, from the first
    camera. The recorders share DATA_DIR/recent_alerts.json for that. A loud alert (stranger) is never merged
    into a quiet household one.
"""
import hashlib
import hmac
import json
import os
import secrets
import time
import urllib.parse
from pathlib import Path

from common import env

DATA_DIR = Path(env("DATA_DIR", "/data"))
SECRET_FILE = DATA_DIR / "action_secret"
RECENT_FILE = DATA_DIR / "recent_alerts.json"
MERGE_SECONDS = env("ALERT_MERGE_SECONDS", 90, int)
ACTION_HOURS = env("ACTION_LINK_HOURS", 24, int)
SNOOZE_MINUTES = 60

VEHICLES = {"car", "truck", "bus", "motorcycle", "bicycle"}
ANIMALS = {"dog", "cat", "bird", "horse", "sheep", "cow", "bear"}

try:
    import fcntl
except ImportError:  # Windows (tests): no locking
    fcntl = None


def kind_of(labels):
    """person / vehicle / animal / motion: what a visit is about, for merging and for unusual activity."""
    labels = set(labels)
    if "person" in labels:
        return "person"
    if labels & VEHICLES:
        return "vehicle"
    if labels & ANIMALS:
        return "animal"
    return "motion"


# ---------- snooze ----------

def snoozed_until(conf, camera, now=None):
    """Epoch until which this camera's pushes are snoozed, or None."""
    until = (conf.get("snooze") or {}).get(camera)
    return until if until and until > (now or time.time()) else None


# ---------- signed action links ----------

def _secret():
    try:
        return SECRET_FILE.read_bytes()
    except FileNotFoundError:
        pass
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:   # several containers may get here at once: the first one creates it
        fd = os.open(SECRET_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(secrets.token_hex(32).encode())
    except FileExistsError:
        time.sleep(0.2)
    return SECRET_FILE.read_bytes()


def _sign(action, camera, day, stem, exp):
    payload = f"{action}|{camera}|{day}|{stem}|{exp}".encode()
    return hmac.new(_secret(), payload, hashlib.sha256).hexdigest()[:32]


def action_url(action, camera, day, stem):
    """URL for a push button, or None without a link address (Settings -> Notifications; the phone must reach it)."""
    import settings  # settings imports common, alerts is imported by settings' users
    base = settings.web_base_url()
    if not base:
        return None
    exp = int(time.time()) + ACTION_HOURS * 3600
    query = urllib.parse.urlencode({"c": camera, "d": day, "s": stem, "e": exp, "sig": _sign(action, camera, day, stem, exp)})
    return f"{base}/a/{action}?{query}"


def verify(action, camera, day, stem, exp, sig):
    try:
        exp = int(exp)
    except (TypeError, ValueError):
        return False
    return exp > time.time() and hmac.compare_digest(_sign(action, camera, day, stem, exp), sig or "")


def push_actions(camera, day, stem):
    """ntfy action buttons (besides "Open clip") for an alert."""
    out = []
    for action, label in (("star", "Star"), ("snooze", "Snooze 1h")):
        url = action_url(action, camera, day, stem)
        if url:
            out.append(f"http, {label}, {url}, method=POST, clear=true")
    return out


# ---------- one visit, one push ----------

def claim(camera, kind, loud, day, stem, now=None):
    """Register an alert about to be pushed. Returns the alert of another camera that belongs to the same visit
    (same kind within MERGE_SECONDS of its last sighting; a loud alert only matches loud ones) - then this alert
    should not be pushed - or None."""
    if MERGE_SECONDS <= 0:
        return None
    now = now or time.time()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(RECENT_FILE.with_suffix(".lock"), "a") as lock:
        if fcntl:
            fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            entries = json.loads(RECENT_FILE.read_text())
        except (FileNotFoundError, ValueError):
            entries = []
        entries = [e for e in entries if now - e["last"] < 600]
        other = next((e for e in reversed(entries) if e["camera"] != camera and e["kind"] == kind
                      and now - e["last"] <= MERGE_SECONDS and (e["loud"] or not loud)), None)
        if other:
            other["last"] = now          # the visit goes on: a third camera still merges
        entries.append({"camera": camera, "kind": kind, "loud": loud, "day": day, "stem": stem, "at": now, "last": now,
                        "first": other["first"] if other else f"{day}/{stem}"})
        tmp = RECENT_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(entries))
        os.replace(tmp, RECENT_FILE)
    return {"camera": other["camera"], "clip": other["first"]} if other else None
