"""CamWatch Studio (/studio): one list of every camera and every device, draft + apply, undo.

Setting a camera up meant four separate forms on the Settings page - add a slot, scan the
network, probe ONVIF, test a URL - and none of them showed what the house actually has. The
Studio is the one list: the cameras in slots, the devices Home Deck sends (homedeck.py) and
the ones a scan found. It is the same shape as Home Deck's own Studio, so the two apps work
the same way round.

Changes are collected in a draft and applied together, because a camera is rarely one edit:
a found camera needs a slot, a name and a stream address, and applying each of those on its
own restarts the recorder three times. Every apply keeps the camera list it replaced, so the
last one can be put back.

Nothing here writes settings except apply(). draft() and preview() are safe to call on every
page load.
"""
import json
import os
import re
import time
from pathlib import Path

import settings
from common import env

DIR = Path(env("DATA_DIR", "/data")) / "studio"
DRAFT = DIR / "draft.json"
HISTORY = DIR / "history.json"
KEEP = 10                       # applies kept for undo; only the newest can be put back


def _read(path, fallback):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, ValueError):
        return fallback


def _write(path, data):
    # Several containers share /data: a half-written draft read by another one looks like a
    # corrupt draft, so write beside it and rename.
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    os.replace(tmp, path)


def host_of(url):
    """The address out of an rtsp url, without the login: rtsp://u:p@192.168.1.81:554/s -> 192.168.1.81."""
    rest = (url or "").partition("://")[2]
    rest = rest.rpartition("@")[2] or rest
    return re.split(r"[:/?]", rest, maxsplit=1)[0]


def inventory(cameras, conf=None):
    """[{kind, key, name, ip, slot, online, added, maker, mac}] - every camera slot, then every
    device Home Deck knows that is not already one of them. cameras is webui.cameras()."""
    import homedeck

    conf = conf or settings.load()
    live = {c["name"]: c for c in cameras}
    items, taken = [], {}
    for c in settings.camera_slots(conf):
        if not c["name"] and not c["rtsp_url"]:
            continue                                  # an empty slot is not a thing you own
        ip = host_of(c["rtsp_url"])
        if ip:
            taken[ip] = c["name"]
        items.append({"kind": "camera", "key": f"slot{c['slot']}", "name": c["name"], "ip": ip,
                      "slot": c["slot"], "enabled": c["enabled"], "added": True,
                      "online": bool(live.get(c["name"], {}).get("online")),
                      "maker": "", "mac": ""})
    for d in homedeck.synced().get("devices", []):
        ip = d.get("ip") or ""
        if not ip or ip in taken:
            continue
        maker = (d.get("vendor") or "").split(",")[0]
        # Pi-hole only knows a name for devices that asked it something; the rest arrive
        # nameless, and the maker reads better as a heading than the address repeated twice.
        items.append({"kind": "device", "key": f"ip{ip}", "name": d.get("name") or maker or ip, "ip": ip,
                      "slot": None, "enabled": False, "added": False, "online": None,
                      "maker": maker, "mac": d.get("mac") or "",
                      "camera_like": homedeck.is_camera(d)})
    return items


def free_slots(conf=None):
    used = {c["slot"] for c in settings.camera_slots(conf) if c["name"] or c["rtsp_url"]}
    return [s for s in range(1, settings.MAX_CAMERAS + 1) if s not in used]


def attention(items, conf=None):
    """The short list at the top: what is wrong, and what is worth doing next."""
    import homedeck

    out = []
    for i in items:
        if i["kind"] == "camera" and i["enabled"] and not i["online"]:
            out.append({"level": "bad", "text": f"{i['name']} is offline"})
    waiting = [i for i in items if i["kind"] == "device" and i.get("camera_like")]
    if waiting:
        names = ", ".join(i["name"] for i in waiting[:3])
        out.append({"level": "warn",
                    "text": f"{len(waiting)} camera{'s' if len(waiting) > 1 else ''} on the network "
                            f"not added yet ({names})"})
    if not homedeck.key(conf):
        out.append({"level": "info", "text": "Home Deck is not linked, so this list is only the cameras "
                                             "(Settings -> Home Deck)"})
    n = len(draft()["changes"])
    if n:
        out.append({"level": "info", "text": f"{n} change{'s' if n > 1 else ''} waiting to be applied"})
    return out


# ---- the draft -------------------------------------------------------

def draft():
    d = _read(DRAFT, {"changes": []})
    return d if isinstance(d, dict) and isinstance(d.get("changes"), list) else {"changes": []}


def masked(changes, mask):
    """The draft as the browser may see it: stream addresses carry the camera password."""
    out = []
    for c in changes:
        c = dict(c)
        for k in ("rtsp_url", "detect_url"):
            if c.get(k):
                c[k] = mask(c[k])
        out.append(c)
    return out


def describe(change):
    k = change["kind"]
    if k == "add":
        return f"add {change['name']} as camera {change['slot']}"
    if k == "rename":
        return f"rename camera {change['slot']} to {change['name']}"
    if k == "remove":
        return f"remove camera {change['slot']}"
    return f"switch camera {change['slot']} {'on' if k == 'enable' else 'off'}"


def add_change(change):
    """Put one change in the draft. Returns an error message, or None."""
    kind = change.get("kind")
    if kind not in ("add", "rename", "remove", "enable", "disable"):
        return "unknown change"
    try:
        slot = int(change.get("slot") or 0)
    except (TypeError, ValueError):
        return "unknown camera"
    if not 1 <= slot <= settings.MAX_CAMERAS:
        return "unknown camera"
    entry = {"kind": kind, "slot": slot, "at": int(time.time())}
    if kind in ("add", "rename"):
        name = (change.get("name") or "").strip().lower()
        if slot == 1 and kind == "rename":
            return "camera 1 keeps the name it was installed with"
        if not settings.CAMERA_NAME_RE.match(name):
            return "the name must be lowercase letters, digits or _ (max 24)"
        entry["name"] = name
    if kind == "add":
        for field in ("rtsp_url", "detect_url"):
            url = (change.get(field) or "").strip()
            if url and not url.lower().startswith(("rtsp://", "rtsps://")):
                return "stream addresses start with rtsp://"
            entry[field] = url
        if not entry["rtsp_url"]:
            return "enter the stream address"
    d = draft()
    # One change per camera per kind: pressing Add twice is a correction, not two cameras.
    d["changes"] = [c for c in d["changes"] if not (c["slot"] == slot and c["kind"] == kind)]
    d["changes"].append(entry)
    error = preview_error(d["changes"])
    if error:
        return error
    _write(DRAFT, d)
    return None


def drop_change(index):
    d = draft()
    if not 0 <= index < len(d["changes"]):
        return "that change is already gone"
    d["changes"].pop(index)
    _write(DRAFT, d)
    return None


def clear():
    _write(DRAFT, {"changes": []})


# ---- applying --------------------------------------------------------

def preview(changes, conf=None):
    """The 'cameras' setting that applying these changes would write."""
    conf = conf or settings.load()
    slots = {c["slot"]: dict(c) for c in settings.camera_slots(conf)}
    gone = set()
    for ch in changes:
        s = slots[ch["slot"]]
        if ch["kind"] == "add":
            s.update(name=ch.get("name") or s["name"], rtsp_url=ch["rtsp_url"],
                     detect_url=ch["detect_url"], enabled=True)
            gone.discard(ch["slot"])
        elif ch["kind"] == "rename":
            s["name"] = ch["name"]
        elif ch["kind"] == "remove":
            gone.add(ch["slot"])
        else:
            s["enabled"] = ch["kind"] == "enable"
    out = []
    for slot in range(1, settings.MAX_CAMERAS + 1):
        c = slots[slot]
        if slot in gone:
            if slot == 1:
                out.append({"slot": 1, "enabled": False})     # camera 1 switches off; it never leaves
            continue
        if slot == 1:
            entry = {"slot": 1} if c["enabled"] else {"slot": 1, "enabled": False}
            if c["rtsp_url"] != (env("RTSP_URL") or ""):
                entry["rtsp_url"] = c["rtsp_url"]
            if c["detect_url"] != (env("DETECT_URL") or ""):
                entry["detect_url"] = c["detect_url"]
            out.append(entry)
        elif c["name"] or c["rtsp_url"]:
            out.append({"slot": slot, "name": c["name"], "rtsp_url": c["rtsp_url"],
                        "detect_url": c["detect_url"], "enabled": bool(c["enabled"])})
    return out


def preview_error(changes, conf=None):
    """Why these changes cannot be applied together, or None. Two cameras cannot share a name."""
    conf = conf or settings.load()
    try:
        cams = preview(changes, conf)
    except KeyError:
        return "unknown camera"
    names = [c.get("name") or settings.primary_camera() for c in cams]
    for n in names:
        if names.count(n) > 1:
            return f"the name {n} is already used"
    for c in cams:
        if c.get("enabled", True) and c["slot"] != 1 and not c.get("rtsp_url"):
            return f"camera {c['slot']} needs a stream address (or switch it off)"
    return None


def apply():
    """Write the draft. Returns (changes_applied, error)."""
    changes = draft()["changes"]
    if not changes:
        return [], "nothing to apply"
    conf = settings.load()
    error = preview_error(changes, conf)
    if error:
        return [], error
    before = conf.get("cameras", [])
    settings.update(cameras=preview(changes, conf))
    history = _read(HISTORY, [])
    history.insert(0, {"at": int(time.time()), "cameras": before,
                       "changes": [describe(c) for c in changes]})
    _write(HISTORY, history[:KEEP])
    clear()
    return [describe(c) for c in changes], None


def history():
    return _read(HISTORY, [])


def undo():
    """Put back the camera list the newest apply replaced. Returns an error, or None."""
    past = _read(HISTORY, [])
    if not past:
        return "there is nothing to undo"
    settings.update(cameras=past[0]["cameras"])
    _write(HISTORY, past[1:])
    return None
