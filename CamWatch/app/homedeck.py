"""The link with Home Deck (panels/ in the amplitude repository) and its Studio. Optional: without a key nothing changes.

CamWatch makes the key (Settings -> Home Deck). In the Studio you enter CamWatch's address and the key. From then on
Home Deck calls POST /api/link/sync about once a minute:
  it sends    {"devices": [{"ip", "name", "vendor", "mac"}], "people": ["anna", ...]}   (its network list and people)
  it gets     {"cameras": [{"name", "slot", "online"}], "people": [{"name", "last_seen", "camera"}]}
CamWatch keeps what Home Deck sent in DATA_DIR/homedeck.json. The camera finder uses the devices: it names the
cameras it finds, and it lists devices from camera makers that the scan missed. The People page lists Home Deck's people
who have no photos yet. The Studio lists the cameras (with the online dot and the health watch) and when a person
was last seen. Home Deck needs no address here: only Home Deck calls, CamWatch only answers.
"""
import datetime as dt
import ipaddress
import json
import os
import re
import secrets
import time
from pathlib import Path

import settings
from common import env

FILE = Path(env("DATA_DIR", "/data")) / "homedeck.json"
SIGHTINGS = Path(env("DATA_DIR", "/data")) / "sightings.jsonl"
# Makers whose devices are cameras, as Pi-hole names them (from the MAC address) or as people name them
CAMERA_MAKERS = ("reolink", "hikvision", "dahua", "axis", "amcrest", "hanwha", "uniview", "foscam", "annke", "lorex",
                 "vivotek", "mobotix", "imou", "ezviz", "wyze", "eufy", "swann", "geovision", "milesight")
# Not in the list: makers that also sell many other devices (Ubiquiti access points, TP-Link plugs)
CAMERA_NAME = re.compile(r"(\b|_|-)(cam|cams|camera|kamera|ipcam)(\b|_|-|\d)", re.I)    # "cam-garage", "Kamera 2"
MAC_RE = re.compile(r"^[0-9a-f]{2}(:[0-9a-f]{2}){5}$")
PERSON_RE = re.compile(r"^[\w .'-]{1,40}$")
STALE = 600                 # a sync older than this counts as gone: Settings says the link is quiet


def key(conf=None):
    return ((conf or settings.load()).get("homedeck") or {}).get("key", "")


def new_key():
    k = secrets.token_urlsafe(24)
    settings.update(homedeck={"key": k})
    return k


def remove():
    settings.update(homedeck={})
    FILE.unlink(missing_ok=True)


def authorized(header):
    """True when the request carries this CamWatch's link key ("Authorization: Bearer <key>")."""
    k = key()
    scheme, _, given = (header or "").partition(" ")
    return bool(k) and scheme.lower() == "bearer" and secrets.compare_digest(given.strip(), k)


def _private_ip(text):
    try:
        ip = ipaddress.ip_address(str(text))
        return str(ip) if ip.is_private else None
    except ValueError:
        return None


def save_sync(data):
    """Keep what Home Deck sent: checked, trimmed, at most 1000 devices and 50 people."""
    devices = []
    for d in (data.get("devices") or [])[:1000]:
        ip = _private_ip(d.get("ip"))
        if not ip:
            continue
        mac = str(d.get("mac") or "").lower()
        devices.append({"ip": ip, "name": str(d.get("name") or "")[:60], "vendor": str(d.get("vendor") or "")[:80],
                        "mac": mac if MAC_RE.match(mac) else ""})
    people = sorted({str(p).strip()[:40] for p in (data.get("people") or [])[:50] if PERSON_RE.match(str(p).strip())})
    FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps({"at": time.time(), "devices": devices, "people": people}), encoding="utf-8")
    os.replace(tmp, FILE)


def synced():
    """What Home Deck sent last: {"at", "devices", "people", "fresh"}; {} before the first sync."""
    try:
        data = json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    data["fresh"] = time.time() - data.get("at", 0) < STALE
    return data


def is_camera(device):
    text = f"{device.get('vendor', '')} {device.get('name', '')}".lower()
    return any(re.search(rf"\b{m}", text) for m in CAMERA_MAKERS) or bool(CAMERA_NAME.search(device.get("name", "")))


def devices_by_ip():
    return {d["ip"]: d for d in synced().get("devices", [])}


def camera_devices():
    """Devices from Home Deck's network list that look like cameras."""
    return [d for d in synced().get("devices", []) if is_camera(d)]


def last_seen(names):
    """{name: {"at", "camera"}} from the newest lines of sightings.jsonl (what facematch and the web UI log)."""
    seen = {}
    try:
        lines = SIGHTINGS.read_text(encoding="utf-8").splitlines()[-5000:]
    except OSError:
        return seen
    for line in reversed(lines):
        try:
            s = json.loads(line)
        except ValueError:
            continue
        name = s.get("name")
        if name in names and name not in seen:
            stem = str(s.get("video", "")).rsplit("/", 1)[-1]
            seen[name] = {"at": s.get("at"), "camera": stem.rsplit("_", 1)[0] if "_" in stem else ""}
            if len(seen) == len(names):
                break
    return seen


def status(cameras, people):
    """The answer to a sync: the cameras that are on, and the people in the face library with when they were seen."""
    seen = last_seen(set(people))
    return {"at": dt.datetime.now().isoformat(timespec="seconds"),
            "cameras": [{"name": c["name"], "slot": c.get("slot"), "online": c["online"]} for c in cameras],
            "people": [{"name": p, "last_seen": seen.get(p, {}).get("at"), "camera": seen.get(p, {}).get("camera", "")}
                       for p in people]}
