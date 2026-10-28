"""Runtime settings changed from the web UI / Home Assistant, shared via DATA_DIR/settings.json.

    mode            armed | disarmed | schedule   (disarmed = record but don't push alerts)
    schedule        "HH:MM-HH:MM" window in which schedule mode is armed (may wrap midnight)
    loiter_seconds  extra alert when an object stays in view this long (0 = off)
    zones           [{"name", "type", "points": [[x, y], ...], "camera"}]  (0..1 coordinates; no camera = the primary one)
                    house/street zones are only used by the presence log (arrived / left)
    plates          known number plates [{"plate", "name"}]
    lan_no_auth     skip the web UI password for direct requests from the trusted networks
    trusted_networks [{"net", "label"}] networks for lan_no_auth (home LAN, VPN ...); not saved yet = LAN_NETWORKS
    cameras         [{"slot", "name", "rtsp_url", "detect_url", "enabled"}]  camera slots 2-4 (slot 1 = .env camera,
                    its URLs can be overridden here). Holds camera passwords: the file is kept readable by root only.
    integration     {"mqtt_host", "mqtt_port", "mqtt_user", "mqtt_password", "ha_webhook_url"}
    ntfy            {"url", "topic", "status_topic", "token", "user", "password", "priority"} push notifications
                    set on the Settings page; a key that was never saved falls back to .env
"""
import datetime as dt
import json
import os
import re
import threading
from pathlib import Path

from common import env

PATH = Path(env("DATA_DIR", "/data")) / "settings.json"
DEFAULTS = {"mode": "armed", "schedule": "22:00-07:00", "loiter_seconds": 30, "zones": [], "plates": [], "lan_no_auth": False}
_lock = threading.Lock()


def raw():
    try:
        return json.loads(PATH.read_text())
    except (FileNotFoundError, ValueError):
        return {}


def load():
    return {**DEFAULTS, **raw()}


def update(**changes):
    with _lock:
        data = {**load(), **changes}
        PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.chmod(0o600)
        os.replace(tmp, PATH)
        return data


def mtime():
    try:
        return PATH.stat().st_mtime
    except FileNotFoundError:
        return 0.0


def in_window(window, now=None):
    try:
        start, end = (dt.time.fromisoformat(t.strip()) for t in window.split("-"))
    except ValueError:
        return True
    t = (now or dt.datetime.now()).time()
    return start <= t < end if start <= end else t >= start or t < end


def is_armed(data):
    mode = data.get("mode", "armed")
    if mode == "disarmed":
        return False
    if mode == "schedule":
        return in_window(data.get("schedule", ""))
    return True


def primary_camera():
    """The camera configured in .env (the original one); zones without a "camera" field belong to it."""
    return env("PRIMARY_CAMERA") or env("CAMERA_NAME", "camera")


def zones_for(conf, camera):
    """The zones drawn for one camera."""
    primary = primary_camera()
    return [z for z in conf.get("zones", []) if z.get("camera", primary) == camera]


# ---------- cameras ----------

MAX_CAMERAS = 4
CAMERA_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_]{0,23}$")


def camera_slots(conf=None):
    """All camera slots, slot 1 first: [{"slot", "name", "rtsp_url", "detect_url", "enabled"}].
    Slot 1 is the camera from .env (its name is fixed, its URLs can be overridden in Settings, and it can be switched
    off like the others). A slot only records when it is enabled and has a name and an RTSP URL."""
    saved = {c.get("slot"): c for c in (conf or load()).get("cameras", [])}
    slots = []
    for slot in range(1, MAX_CAMERAS + 1):
        c = saved.get(slot, {})
        if slot == 1:
            cam = {"name": primary_camera(), "rtsp_url": c.get("rtsp_url") or env("RTSP_URL") or "",
                   "detect_url": c["detect_url"] if "detect_url" in c else env("DETECT_URL") or "",
                   "enabled": c.get("enabled", True)}
        else:
            cam = {"name": c.get("name", ""), "rtsp_url": c.get("rtsp_url", ""), "detect_url": c.get("detect_url", ""),
                   "enabled": c.get("enabled", True)}
        cam["enabled"] = bool(cam["enabled"] and cam["name"] and cam["rtsp_url"])
        slots.append({"slot": slot, **cam})
    return slots


def default_camera(conf=None):
    """The camera pages show when none is chosen: the first one that is on (camera 1 can be switched off)."""
    return next((c["name"] for c in camera_slots(conf) if c["enabled"]), primary_camera())


def pruning_camera(conf=None):
    """The one recorder that deletes old recordings from the shared disk: the first camera that is on."""
    return default_camera(conf)


def camera_key(cam):
    """What a recorder restarts for when it changes."""
    return cam["name"], cam["rtsp_url"], cam["detect_url"], cam["enabled"]


# ---------- Home Assistant / network ----------

INTEGRATION_ENV = {"mqtt_host": "MQTT_HOST", "mqtt_port": "MQTT_PORT", "mqtt_user": "MQTT_USER",
                   "mqtt_password": "MQTT_PASSWORD", "ha_webhook_url": "HA_WEBHOOK_URL"}


def integration(conf=None):
    """MQTT broker and Home Assistant webhook: as saved on the Settings page, else from .env."""
    saved = (conf or load()).get("integration") or {}
    out = {key: str(saved[key]) if key in saved else env(name) or "" for key, name in INTEGRATION_ENV.items()}
    out["mqtt_port"] = int(out["mqtt_port"] or 1883)
    return out


NTFY_ENV = {"url": "NTFY_URL", "topic": "NTFY_TOPIC", "status_topic": "NTFY_STATUS_TOPIC", "token": "NTFY_TOKEN",
            "user": "NTFY_USER", "password": "NTFY_PASSWORD", "priority": "NTFY_PRIORITY"}
NTFY_PRIORITIES = ("min", "low", "default", "high", "urgent")


def ntfy(conf=None):
    """Push notification settings: as saved on the Settings page, else from .env."""
    saved = (conf or load()).get("ntfy") or {}
    out = {key: str(saved[key]) if key in saved else env(name) or "" for key, name in NTFY_ENV.items()}
    out["url"] = (out["url"] or "https://ntfy.sh").rstrip("/")
    if out["priority"] not in NTFY_PRIORITIES:
        out["priority"] = "high"
    if out["topic"] == "CHANGE_ME":
        out["topic"] = ""
    return out


def web_base_url(conf=None):
    """The web address pushes link to (clips, push buttons, Home Assistant). Set in Settings -> Notifications,
    else WEB_BASE_URL from .env. Empty: pushes have no links."""
    saved = ((conf or load()).get("ntfy") or {}).get("link_url")
    return (saved if saved is not None else env("WEB_BASE_URL", "") or "").strip().rstrip("/")


def storage(conf=None):
    """How long clips stay and how much disk stays free: as saved in Settings -> Storage, else from .env.
    {"retention_days": plain clips, "keep_days": clips with identified people, "min_free_gb"}; 0 days = no limit."""
    saved = (conf or load()).get("storage") or {}
    out = {}
    for key, name, default, kind in (("retention_days", "RETENTION_DAYS", 30, int),
                                      ("keep_days", "RETENTION_KEEP_DAYS", 90, int),
                                      ("min_free_gb", "MIN_FREE_GB", 20, float)):
        try:
            out[key] = kind(saved[key] if key in saved else env(name, default))
        except (TypeError, ValueError):
            out[key] = default
    return out


def trusted_networks(conf=None):
    """[{"net", "label"}] whose devices skip the password when lan_no_auth is on: as saved in Settings, else LAN_NETWORKS."""
    conf = conf or load()
    if "trusted_networks" in conf:
        return conf["trusted_networks"]
    legacy = (conf.get("integration") or {}).get("lan_networks") or env("LAN_NETWORKS") or "192.168.0.0/16,10.0.0.0/8"
    return [{"net": n.strip(), "label": ""} for n in legacy.split(",") if n.strip()]
