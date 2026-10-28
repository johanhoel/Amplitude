"""Web UI: browse and play recordings, tag people manually, delete clips."""
import datetime as dt
import io
import ipaddress
import json
import re
import secrets
import shutil
import subprocess
import threading
import time
import zipfile
from pathlib import Path

from flask import Flask, Response, abort, redirect, render_template, request, send_from_directory, url_for
from jinja2 import DictLoader
from waitress import serve

import cv2
import numpy as np

import alerts
import feature_requests
import offsite
import settings
import updates
from plates import match_known, normalize
from common import VIDEO_EXT, app_version, delete_event, env, setup_logging

log = setup_logging("webui")

REC_DIR = Path(env("RECORDINGS_DIR", "/recordings"))
PHOTOS_DIR = Path(env("PHOTOS_DIR", "/photos"))
DATA_DIR = Path(env("DATA_DIR", "/data"))
LIVE_DIR = Path(env("LIVE_DIR", "/live"))   # one folder per camera, written by its recorder
CAMERA = env("CAMERA_NAME", "camera")       # the primary camera (.env)
CAMERA_RE = re.compile(r"^[a-z0-9][a-z0-9_]{0,23}$")
WEB_USER = env("WEB_USER", "admin")
WEB_PASSWORD = env("WEB_PASSWORD")
# "No password on the home network" (Settings) only trusts these networks. Docker's own 172.16/12 range is left out
# on purpose: with some setups every request seems to come from the Docker bridge.

DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
STEM_RE = re.compile(r"^[\w.-]+$")
NAME_RE = re.compile(r"^[\w .'-]{1,40}$")
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024


# ---------- data access ----------

def load_json(path, default=None):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, ValueError):
        return default


def check(day, stem=None):
    if not DAY_RE.match(day) or (stem is not None and not STEM_RE.match(stem)):
        abort(404)
    return REC_DIR / day


def cameras():
    """[{name, primary, online}] of the cameras that are on (Settings -> Cameras), in slot order."""
    return [{"name": c["name"], "primary": c["slot"] == 1,
             "online": time.time() - _mtime(LIVE_DIR / c["name"] / "alive") < 60}
            for c in settings.camera_slots() if c["enabled"]]


MASK = "••••••"


def split_login(url):
    """rtsp://user:password@host/... -> ("rtsp://", user, password, "host/...") or None without a password.
    Split by hand at the last @: camera passwords are often typed as-is with / # ? @ in them, which a URL parser
    takes for the start of the path, query or fragment (and then masks or keeps the wrong part)."""
    scheme, sep, rest = (url or "").partition("://")
    userinfo, at, host = rest.rpartition("@")
    if not sep or not at or ":" not in userinfo or not re.match(r"^[\w\[]", host):
        return None
    user, _, password = userinfo.partition(":")
    return f"{scheme}://", user, password, host


def mask_url(url):
    """The URL with its password hidden, for showing it in the browser."""
    login = split_login(url)
    if not login:
        return url or ""
    prefix, user, _, host = login
    return f"{prefix}{user}:{MASK}@{host}"


class MaskError(ValueError):
    pass


def unmask_url(url, old):
    """A URL sent back from the Settings page: put the stored password back where it was masked.
    The mask only stands for the whole saved password - a half-edited mask would otherwise be saved literally."""
    if MASK[0] not in url:
        return url
    login, old_login = split_login(url), split_login(old)
    if not login or login[2] != MASK:
        raise MaskError("replace the whole •••••• with the new password, or leave it as it is")
    if not old_login:
        raise MaskError("there is no saved password to keep - type the password instead of ••••••")
    prefix, user, _, host = login
    return f"{prefix}{user}:{old_login[2]}@{host}"


def lan_networks():
    nets = []
    for n in settings.trusted_networks():
        try:
            nets.append(ipaddress.ip_network(n["net"], strict=False))
        except ValueError:
            pass
    return nets


DOCKER_NETS = ipaddress.ip_network("172.16.0.0/12")


def parse_network(text):
    """A trusted network typed on the Settings page -> (network, error)."""
    try:
        net = ipaddress.ip_network(text.strip(), strict=False)
    except ValueError:
        return None, f"{text}: not a network - write it like 192.168.1.0/24 or 10.8.0.0/24"
    if net.prefixlen < (8 if net.version == 4 else 32):
        return None, f"{net}: too large - that would let a big part of the internet in without a password"
    return net, None


def camera_arg():
    """The camera chosen with ?camera= (or a form field); the first camera that is on when not given."""
    name = request.values.get("camera")
    if not name:
        return settings.default_camera()
    if not CAMERA_RE.match(name) or name not in {c["name"] for c in cameras()}:
        abort(404)
    return name


def camera_of(stem):
    """Camera name of a clip: everything before the _HHMMSS suffix."""
    return re.sub(r"_\d{6}(?:-\w+)?$", "", stem)


def days():
    if not REC_DIR.is_dir():
        return []
    return sorted((d.name for d in REC_DIR.iterdir() if d.is_dir() and DAY_RE.match(d.name)), reverse=True)


def people():
    if not PHOTOS_DIR.is_dir():
        return []
    return sorted(p.name for p in PHOTOS_DIR.iterdir() if p.is_dir() and not p.name.startswith("."))


def clip(day, stem):
    folder = REC_DIR / day
    video = next((f"{stem}{ext}" for ext in (".mp4", ".mkv") if (folder / f"{stem}{ext}").exists()), None)
    meta = load_json(folder / f"{stem}.json", {})
    faces = load_json(folder / f"{stem}.faces.json")
    labels = load_json(folder / f"{stem}.labels.json", [])

    m = re.search(r"_(\d{6})(?:-\d+)?$", stem)
    time = f"{m.group(1)[:2]}:{m.group(1)[2:4]}:{m.group(1)[4:]}" if m else stem
    duration = None
    if meta.get("start") and meta.get("end"):
        duration = int((dt.datetime.fromisoformat(meta["end"]) - dt.datetime.fromisoformat(meta["start"])).total_seconds())

    names = []
    for entry in (faces or {}).get("known", []) + labels:
        if entry["name"] not in names:
            names.append(entry["name"])
    detected = list((meta.get("labels") or {}).keys()) + (["test"] if meta.get("test") else [])
    minute = int(m.group(1)[:2]) * 60 + int(m.group(1)[2:4]) + int(m.group(1)[4:]) / 60 if m else 0
    return {
        "plates": [{**p, "name": (match_known(p["plate"], known_plates()) or {}).get("name")}
                   for p in meta.get("plates") or []],
        "detected": detected, "zones": meta.get("zones") or [], "loitering": meta.get("loitering"),
        "starred": (folder / f"{stem}.star").exists(), "minute": minute, "kind": kind_of(detected, names),
        "day": day, "stem": stem, "time": time, "video": video, "meta": meta, "faces": faces,
        "labels": labels, "names": names, "duration": duration,
        "snapshot": f"{stem}.jpg" if (folder / f"{stem}.jpg").exists() else None,
        "unknown": len((faces or {}).get("unknown", [])), "unusual": meta.get("unusual"),
        "camera": meta.get("camera") or camera_of(stem),
        "visit": [g for g in day_groups(day).get(stem, []) if g["stem"] != stem],
    }


VEHICLES = {"car", "truck", "bus", "motorcycle", "bicycle", "boat"}
ANIMALS = {"dog", "cat", "bird", "horse", "sheep", "cow", "bear"}


def kind_of(detected, names):
    if names:
        return "known"
    if "test" in detected:
        return "test"
    if "person" in detected:
        return "person"
    if VEHICLES & set(detected):
        return "vehicle"
    if ANIMALS & set(detected):
        return "animal"
    return "motion"


def known_plates():
    return settings.load().get("plates", [])


_groups = {}   # day -> (folder mtime, groups)


def day_groups(day):
    """Clips from several cameras that follow each other within ALERT_MERGE_SECONDS are one visit (someone walking
    from the driveway to the door): {stem: [{"stem", "camera", "time"}, ...in time order]} for each clip in such a visit."""
    folder = REC_DIR / day
    mtime = _mtime(folder)
    hit = _groups.get(day)
    if hit and hit[0] == mtime:
        return hit[1]
    rows = []
    for meta_path in folder.glob("*.json") if folder.is_dir() else []:
        if SIDECAR_RE.search(meta_path.name):
            continue
        meta = load_json(meta_path, {})
        try:
            start = dt.datetime.fromisoformat(meta["start"])
            end = dt.datetime.fromisoformat(meta.get("end") or meta["start"])
        except (KeyError, TypeError, ValueError):
            continue
        if not meta.get("test"):
            stem = meta_path.name[:-5]
            rows.append((start, end, stem, meta.get("camera") or camera_of(stem)))
    rows.sort()
    groups, current, current_end = {}, [], None

    def close():
        if len({r[3] for r in current}) > 1:
            members = [{"stem": r[2], "camera": r[3], "time": f"{r[0]:%H:%M:%S}"} for r in current]
            for r in current:
                groups[r[2]] = members
    for row in rows:
        if current and (row[0] - current_end).total_seconds() <= alerts.MERGE_SECONDS:
            current.append(row)
            current_end = max(current_end, row[1])
        else:
            close()
            current, current_end = [row], row[1]
    close()
    _groups[day] = (mtime, groups)
    return groups


def all_clips():
    return [c for d in days() for c in clips_for(d)]


def clips_for(day):
    folder = REC_DIR / day
    if not folder.is_dir():
        return []
    stems = {p.name[: -len(p.suffix)] for p in folder.iterdir() if p.suffix.lower() in VIDEO_EXT}
    return [clip(day, s) for s in sorted(stems, reverse=True)]


# ---------- auth ----------

def from_lan():
    """True for a direct request from the home network. Anything that came through a proxy (it adds forwarding
    headers, and from the outside it would look like a LAN address) never counts."""
    if any(h in request.headers for h in ("X-Forwarded-For", "Forwarded", "X-Real-IP", "X-Forwarded-Host")):
        return False
    try:
        ip = ipaddress.ip_address(request.remote_addr or "")
    except ValueError:
        return False
    return any(ip in net for net in lan_networks())


@app.before_request
def auth():
    if not WEB_PASSWORD or request.path in ("/healthz", "/manifest.webmanifest", "/sw.js") \
            or request.path.startswith(("/a/", "/static/")):
        return None     # app icon/manifest hold nothing private; /a/... are push buttons with their own signed token
    if settings.load().get("lan_no_auth") and from_lan():
        return None
    a = request.authorization
    if a and secrets.compare_digest(a.username or "", WEB_USER) and secrets.compare_digest(a.password or "", WEB_PASSWORD):
        return None
    return Response("Login required", 401, {"WWW-Authenticate": 'Basic realm="camwatch"'})


# ---------- routes ----------

@app.context_processor
def inject_status():
    conf = settings.load()
    return {"armed": settings.is_armed(conf), "arm_mode": conf["mode"], "app_version": app_version()}


@app.get("/")
def index():
    all_days = days()
    person = request.args.get("person") or None
    plate = normalize(request.args.get("plate")) or None
    starred = bool(request.args.get("starred"))
    label = request.args.get("label") or None
    camera = request.args.get("camera") or None
    if camera and not CAMERA_RE.match(camera):
        abort(404)
    day = request.args.get("day") or (all_days[0] if all_days else None)
    day_clips, labels = [], []
    if person or starred or plate:
        clips = [c for c in all_clips() if (not person or person in c["names"]) and (not starred or c["starred"])
                 and (not plate or any(p["plate"] == plate for p in c["plates"]))]
        heading = " · ".join(filter(None, ["Starred clips" if starred else None,
                                           f"Clips with {person}" if person else None,
                                           f"Clips with plate {plate}" if plate else None]))
    else:
        if day and not DAY_RE.match(day):
            abort(404)
        day_clips = clips_for(day) if day else []
        labels = sorted({d for c in day_clips for d in c["detected"]})
        clips = [c for c in day_clips if not label or label in c["detected"]]
        heading = day or "No recordings yet"
    if camera:
        clips = [c for c in clips if camera_of(c["stem"]) == camera]
        day_clips = [c for c in day_clips if camera_of(c["stem"]) == camera]
    return render_template("index.html", days=all_days, day=day, clips=clips, heading=heading, label=label,
                           labels=labels, starred=starred, person=person, plate=plate, people=people(),
                           timeline=day_clips, camera=camera, cameras=cameras())


@app.get("/clip/<day>/<stem>")
def clip_page(day, stem):
    folder = check(day, stem)
    c = clip(day, stem)
    if not c["video"] and not c["snapshot"]:
        abort(404)
    stems = [p.name[: -len(p.suffix)] for p in sorted(folder.iterdir()) if p.suffix.lower() in VIDEO_EXT]
    i = stems.index(stem) if stem in stems else -1
    newer = stems[i + 1] if 0 <= i < len(stems) - 1 else None
    older = stems[i - 1] if i > 0 else None
    return render_template("clip.html", c=c, days=days(), people=people(), newer=newer, older=older,
                           share=share_status(request.args["share"]) if request.args.get("share") else None)


# ---------- push buttons and snooze ----------

def snoozes(conf=None):
    """{camera: "HH:MM"} for the cameras whose pushes are snoozed now."""
    conf = conf or settings.load()
    out = {}
    for c in cameras():
        until = alerts.snoozed_until(conf, c["name"])
        if until:
            out[c["name"]] = dt.datetime.fromtimestamp(until).strftime("%H:%M")
    return out


def set_snooze(camera, minutes):
    snooze = {k: v for k, v in (settings.load().get("snooze") or {}).items() if v > time.time()}
    if minutes > 0:
        snooze[camera] = time.time() + minutes * 60
    else:
        snooze.pop(camera, None)
    settings.update(snooze=snooze)


@app.post("/a/<action>")
def push_button(action):
    """A button on a push notification. Valid only with the signature made for this action and clip."""
    a = request.args
    camera, day, stem = a.get("c", ""), a.get("d", ""), a.get("s", "")
    if action not in ("star", "snooze") or not alerts.verify(action, camera, day, stem, a.get("e"), a.get("sig")):
        return Response("This button has expired.", 403, mimetype="text/plain")
    folder = check(day, stem)
    if action == "star":
        (folder / f"{stem}.star").touch()
        return Response(f"Starred {day} {stem}", mimetype="text/plain")
    set_snooze(camera, alerts.SNOOZE_MINUTES)
    return Response(f"{camera}: no pushes for {alerts.SNOOZE_MINUTES} minutes", mimetype="text/plain")


@app.post("/snooze")
def snooze():
    camera = camera_arg()
    set_snooze(camera, max(0, min(24 * 60, request.form.get("minutes", type=int) or 0)))
    return redirect(request.referrer or url_for("settings_page"))


# ---------- shareable blurred copies (app/share.py) ----------

def share_status(job_id):
    import share
    job = share.jobs.get(job_id)
    if job is None:
        return None
    return {"id": job_id, "state": job["state"], "progress": round(job["progress"], 3), "error": job["error"],
            "url": url_for("share_file", name=job["file"]) if job["state"] == "done" else None}


@app.post("/clip/<day>/<stem>/share")
def share_clip(day, stem):
    import share
    folder = check(day, stem)
    c = clip(day, stem)
    if not c["video"]:
        abort(404)
    faces = request.form.get("faces", "strangers")
    if faces not in ("strangers", "all", "none"):
        abort(400)
    job_id = share.submit(folder / c["video"], day, stem, faces, request.form.get("plates", "1") == "1")
    if "application/json" in (request.headers.get("Accept") or ""):
        return as_json(share_status(job_id))
    return redirect(url_for("clip_page", day=day, stem=stem, share=job_id))


@app.get("/api/share/<job_id>")
def api_share(job_id):
    status = share_status(job_id)
    if status is None:
        abort(404)
    return as_json(status)


@app.get("/shares/<name>")
def share_file(name):
    import share
    if not re.match(r"^[\w.-]+\.mp4$", name):
        abort(404)
    return send_from_directory(share.OUT_DIR, name, as_attachment=True, conditional=True)


# ---------- daily timelapse + highlights (app/timelapse.py) ----------

_timelapse_job = {"running": False, "day": None, "error": None}


@app.get("/timelapse")
def timelapse_page():
    import timelapse
    today = dt.date.today().isoformat()
    cams = cameras()
    frames_today = {c["name"]: len(list((timelapse.FRAMES_DIR / c["name"] / today).glob("*.jpg"))) for c in cams}
    return render_template("timelapse.html", items=timelapse.available(settings.primary_camera()), job=_timelapse_job,
                           frames_today=frames_today, cameras=cams, interval=timelapse.INTERVAL,
                           build_at=timelapse.BUILD_AT, people=people())


@app.post("/timelapse/build")
def timelapse_build():
    """Build today so far, in the background (the nightly build replaces it)."""
    import timelapse
    if not _timelapse_job["running"]:
        day = dt.date.today().isoformat()

        def run():
            _timelapse_job.update(running=True, day=day, error=None)
            try:
                for c in cameras():
                    timelapse.build_day(day, log, keep_frames=True, camera=c["name"])
            except Exception as e:
                _timelapse_job["error"] = str(e)[:200]
            finally:
                _timelapse_job["running"] = False
        threading.Thread(target=run, daemon=True).start()
    return redirect(url_for("timelapse_page"))


@app.get("/timelapse/file/<name>")
def timelapse_file(name):
    import timelapse
    if not re.match(r"^\d{4}-\d{2}-\d{2}(-[a-z0-9_]+)?-(timelapse|highlights)\.mp4$", name):
        abort(404)
    return send_from_directory(timelapse.OUT_DIR, name, conditional=True, max_age=300)


@app.get("/live")
def live():
    return render_template("live.html", camera=camera_arg(), cameras=cameras(), people=people(), sent=request.args.get("sent"))


@app.get("/live.mjpg")
def live_stream():
    """MJPEG of the frames the recorder is analysing; the recorder only publishes while this is open."""
    live_dir = LIVE_DIR / camera_arg()

    def frames():
        last = 0.0
        waiting_since = time.time()
        while True:
            (live_dir / "watching").touch()
            try:
                mtime = (live_dir / "frame.jpg").stat().st_mtime
                data = (live_dir / "frame.jpg").read_bytes() if mtime != last else None
            except FileNotFoundError:
                mtime, data = 0.0, None
            if data:
                last = mtime
                waiting_since = time.time()
                yield b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n%s\r\n" % (len(data), data)
            elif time.time() - waiting_since > 20:
                return  # recorder isn't getting frames; the page shows an error
            time.sleep(0.1)

    live_dir.mkdir(parents=True, exist_ok=True)
    return Response(frames(), mimetype="multipart/x-mixed-replace; boundary=frame",
                    headers={"Cache-Control": "no-store"})


@app.get("/live.jpg")
def live_still():
    """Current camera frame as one JPEG (for Home Assistant camera entities)."""
    live_dir = LIVE_DIR / camera_arg()
    live_dir.mkdir(parents=True, exist_ok=True)
    frame = live_dir / "frame.jpg"
    asked = time.time()
    (live_dir / "watching").touch()
    while time.time() - asked < 3:
        try:
            if frame.stat().st_mtime >= asked - 1:
                break
        except FileNotFoundError:
            pass
        time.sleep(0.1)
    if not frame.exists():
        abort(503)
    data = frame.read_bytes()
    width = request.args.get("w", type=int)
    if width:
        data = resized_jpeg(cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR), width) or data
    return Response(data, mimetype="image/jpeg", headers={"Cache-Control": "no-store"})


def resized_jpeg(img, width, quality=78):
    """JPEG bytes of `img` scaled down to at most `width` px wide (120..1920); None if it can't be encoded."""
    if img is None:
        return None
    width = max(120, min(1920, width))
    h, w = img.shape[:2]
    if w > width:
        img = cv2.resize(img, (width, round(h * width / w)), interpolation=cv2.INTER_AREA)
    ok, jpg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return jpg.tobytes() if ok else None


@app.get("/healthz")
def healthz():
    return "ok"


# ---------- people (reference photo library) ----------

def person_dir(name):
    if not NAME_RE.match(name) or name.startswith("."):
        abort(404)
    return PHOTOS_DIR / name


def photo_status():
    """path -> True/False whether facematch found a face in it (None = not checked yet)."""
    cache = load_json(DATA_DIR / "library_cache.json", {})
    return {k: v.get("emb") is not None for k, v in cache.items()}


def save_uploads(folder, files):
    saved = 0
    folder.mkdir(parents=True, exist_ok=True)
    for f in files:
        data = f.read()
        if not data or cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR) is None:
            continue
        ext = Path(f.filename or "").suffix.lower()
        ext = ext if ext in IMG_EXT else ".jpg"
        (folder / f"upload_{dt.datetime.now():%Y%m%d_%H%M%S}_{saved}{ext}").write_bytes(data)
        saved += 1
    return saved


@app.get("/people")
def people_page():
    rows = []
    for name in people():
        photos = sorted(p for p in (PHOTOS_DIR / name).rglob("*") if p.suffix.lower() in IMG_EXT)
        rows.append({"name": name, "count": len(photos),
                     "cover": photos[0].relative_to(PHOTOS_DIR / name).as_posix() if photos else None})
    return render_template("people.html", rows=rows, people=people())


@app.post("/people")
def create_person():
    name = (request.form.get("name") or "").strip()
    folder = person_dir(name)
    folder.mkdir(parents=True, exist_ok=True)
    save_uploads(folder, request.files.getlist("photos"))
    return redirect(url_for("person_page", name=name))


@app.get("/people/<name>")
def person_page(name):
    folder = person_dir(name)
    if not folder.is_dir():
        abort(404)
    status = photo_status()
    photos = [{"file": p.relative_to(folder).as_posix(), "face": status.get(str(p))}
              for p in sorted(folder.rglob("*")) if p.suffix.lower() in IMG_EXT]
    sightings = []
    try:
        for line in (DATA_DIR / "sightings.jsonl").read_text().splitlines()[-2000:]:
            s = json.loads(line)
            if s.get("name") == name:
                sightings.append(s)
    except (FileNotFoundError, ValueError):
        pass
    return render_template("person.html", name=name, photos=photos, people=people(),
                           sightings=list(reversed(sightings))[:20])


@app.get("/people/<name>/photo/<path:file>")
def person_photo(name, file):
    return send_from_directory(person_dir(name), file, max_age=3600)


@app.post("/people/<name>/upload")
def upload_photos(name):
    save_uploads(person_dir(name), request.files.getlist("photos"))
    return redirect(url_for("person_page", name=name))


@app.post("/people/<name>/photo/<path:file>/delete")
def delete_photo(name, file):
    folder = person_dir(name)
    path = (folder / file).resolve()
    if folder.resolve() in path.parents and path.is_file():
        path.unlink()
    return redirect(url_for("person_page", name=name))


@app.post("/people/<name>/rename")
def rename_person(name):
    folder = person_dir(name)
    new = (request.form.get("new_name") or "").strip()
    target = person_dir(new)
    if target.exists():
        abort(400, "A person with that name already exists")
    folder.rename(target)
    return redirect(url_for("person_page", name=new))


@app.post("/people/<name>/delete")
def delete_person(name):
    folder = person_dir(name)
    if folder.is_dir():
        shutil.rmtree(folder)
    return redirect(url_for("people_page"))


# ---------- Home Assistant ----------

@app.get("/homeassistant")
def ha_page():
    base = settings.web_base_url() or request.host_url.rstrip("/")
    labels = [s.strip() for s in (env("DETECT_OBJECTS", "person") or "").split(",") if s.strip()]
    slug = re.sub(r"[^a-z0-9]+", "_", f"camwatch {CAMERA}".lower()).strip("_")
    person = (people() or ["Anna"])[0]
    first = labels[0] if labels else "motion"
    examples = {
        f"Notify phone when a {first} is detected (with snapshot and clip link)": f"""\
alias: camwatch - {first} detected
triggers:
  - trigger: state
    entity_id: event.{slug}_detection
conditions:
  - condition: template
    value_template: "{{{{ trigger.to_state.attributes.event_type == '{first}' }}}}"
actions:
  - action: notify.mobile_app_YOUR_PHONE
    data:
      title: "{first.title()} at the {CAMERA}"
      message: "{{{{ now().strftime('%H:%M') }}}}"
      data:
        image: "{{{{ trigger.to_state.attributes.snapshot_url }}}}"
        clickAction: "{{{{ trigger.to_state.attributes.clip_url }}}}"
        url: "{{{{ trigger.to_state.attributes.clip_url }}}}"
""",
        f"Do something when {person} is identified": f"""\
alias: camwatch - {person} is home
triggers:
  - trigger: state
    entity_id: event.{slug}_detection
conditions:
  - condition: template
    value_template: >
      {{{{ trigger.to_state.attributes.event_type == 'identified'
         and trigger.to_state.attributes.name == '{person}' }}}}
actions:
  - action: light.turn_on
    target:
      entity_id: light.YOUR_LIGHT
""",
        "Open the garage when a known car arrives": f"""\
alias: camwatch - known car arrives
triggers:
  - trigger: state
    entity_id: event.{slug}_detection
conditions:
  - condition: template
    value_template: >
      {{{{ trigger.to_state.attributes.event_type == 'plate'
         and trigger.to_state.attributes.known }}}}
actions:
  - action: cover.open_cover
    target:
      entity_id: cover.YOUR_GARAGE_DOOR
  - action: notify.mobile_app_YOUR_PHONE
    data:
      message: "{{{{ trigger.to_state.attributes.name }}}} arrived ({{{{ trigger.to_state.attributes.plate }}}})"
""",
        f"Turn on a light while a {first} is outside, after dark": f"""\
alias: camwatch - light on {first}
triggers:
  - trigger: state
    entity_id: binary_sensor.{slug}_{first.replace(' ', '_')}
    to: "on"
conditions:
  - condition: sun
    after: sunset
    before: sunrise
actions:
  - action: light.turn_on
    target:
      entity_id: light.YOUR_LIGHT
  - wait_for_trigger:
      - trigger: state
        entity_id: binary_sensor.{slug}_{first.replace(' ', '_')}
        to: "off"
        for: "00:02:00"
  - action: light.turn_off
    target:
      entity_id: light.YOUR_LIGHT
""",
        "Alert when the camera goes offline": f"""\
alias: camwatch - camera offline
triggers:
  - trigger: state
    entity_id: binary_sensor.{slug}_camera_online
    to: "off"
actions:
  - action: persistent_notification.create
    data:
      title: Camera offline
      message: "{CAMERA} has stopped sending video"
""",
    }
    webhook_example = f"""\
alias: camwatch - webhook
triggers:
  - trigger: webhook
    webhook_id: camwatch-CHANGE-ME-random
    allowed_methods: [POST]
    local_only: true
conditions:
  - condition: template
    value_template: "{{{{ trigger.json.event_type == '{first}' }}}}"
actions:
  - action: notify.mobile_app_YOUR_PHONE
    data:
      message: "{{{{ trigger.json.event_type }}}} at {{{{ trigger.json.time }}}}"
      data:
        image: "{{{{ trigger.json.snapshot_url }}}}"
        url: "{{{{ trigger.json.clip_url }}}}"
"""
    dashboard = f"""\
type: vertical-stack
cards:
  - type: picture-entity
    entity: camera.{slug}_live
    camera_view: live
    name: {CAMERA} live
  - type: picture-entity
    entity: camera.{slug}_last_event
    name: Last event
  - type: entities
    entities:
      - entity: binary_sensor.{slug}_{first.replace(' ', '_')}
      - entity: binary_sensor.{slug}_motion
      - entity: sensor.{slug}_last_identified
      - entity: sensor.{slug}_last_event_time
      - entity: binary_sensor.{slug}_camera_online
"""
    return render_template("ha.html", base=base, camera=CAMERA, labels=labels, people=people(),
                           mqtt=settings.integration()["mqtt_host"], webhook=bool(settings.integration()["ha_webhook_url"]), slug=slug,
                           prefix=env("MQTT_TOPIC_PREFIX", "camwatch"), auth=bool(WEB_PASSWORD),
                           examples=examples, webhook_example=webhook_example, dashboard=dashboard)


@app.post("/clip/<day>/<stem>/star")
def toggle_star(day, stem):
    folder = check(day, stem)
    star = folder / f"{stem}.star"
    if star.exists():
        star.unlink()
    elif any(folder.glob(f"{stem}.*")):
        star.touch()
    return redirect(request.referrer or url_for("clip_page", day=day, stem=stem))


@app.route("/settings", methods=["GET", "POST"])
def settings_page():
    if request.method == "POST":
        mode = request.form.get("mode")
        start, end = request.form.get("from", "22:00"), request.form.get("to", "07:00")
        if mode not in ("armed", "disarmed", "schedule") or not re.match(r"^\d\d:\d\d$", start) \
                or not re.match(r"^\d\d:\d\d$", end):
            abort(400)
        loiter = max(0, min(3600, int(request.form.get("loiter_seconds") or 0)))
        trusted, seen = [], set()
        for text, label in zip(request.form.getlist("net"), request.form.getlist("net_label")):
            if not text.strip():
                continue
            net, error = parse_network(text)
            if error:
                return settings_error(error)
            if str(net) not in seen:
                seen.add(str(net))
                trusted.append({"net": str(net), "label": label.strip()[:40]})
        unusual = request.form.get("unusual_alerts", "armed")
        if unusual not in ("off", "armed", "always"):
            abort(400)
        settings.update(mode=mode, schedule=f"{start}-{end}", loiter_seconds=loiter, unusual_alerts=unusual,
                        lan_no_auth=request.form.get("lan_no_auth") == "1", trusted_networks=trusted)
        return redirect(url_for("settings_page", saved=1) + "#login")
    conf = settings.load()
    start, _, end = conf["schedule"].partition("-")
    online = {c["name"]: c["online"] for c in cameras()}
    slots = [{**c, "rtsp_url": mask_url(c["rtsp_url"]), "detect_url": mask_url(c["detect_url"]),
              "online": online.get(c["name"]), "saved": bool(c["name"] and c["rtsp_url"])}
             for c in settings.camera_slots(conf)]
    integ = settings.integration(conf)
    try:
        client_ip = ipaddress.ip_address(request.remote_addr or "")
    except ValueError:
        client_ip = None
    networks = []
    for n in settings.trusted_networks(conf):
        net, _ = parse_network(n["net"])
        networks.append({**n, "here": bool(net and client_ip in net),
                         "docker": bool(net and net.version == 4 and net.overlaps(DOCKER_NETS))})
    suggest = None    # this device's own /24 (or /64), offered when it isn't in a trusted network yet
    if client_ip and not client_ip.is_loopback and not any(n["here"] for n in networks):
        suggest = str(ipaddress.ip_network(f"{client_ip}/{24 if client_ip.version == 4 else 64}", strict=False))
    return render_template("settings.html", conf=conf, start=start, end=end, people=people(),
                           saved=request.args.get("saved"), error=request.args.get("error"), mqtt=request.args.get("mqtt"),
                           on_lan=from_lan(), client=request.remote_addr, slots=slots, integ=integ,
                           networks=networks, suggest=suggest, has_password=bool(WEB_PASSWORD),
                           cams=cameras(), snoozed=snoozes(conf), scan_subnet=scan_default(),
                           nt=settings.ntfy(conf), ntfy_result=request.args.get("ntfy"), link_url=settings.web_base_url(conf), priorities=settings.NTFY_PRIORITIES,
                           off=offsite.options(conf), off_connected=offsite.connected(), off_status=offsite.status(),
                           off_types=offsite.TYPES, off_queue=len(list(offsite.QUEUE.glob("*.json"))) if offsite.QUEUE.is_dir() else 0,
                           upd=updates.options(conf), upd_status=updates.status())


def settings_error(message):
    """Back to the top of Settings, where the message is shown."""
    return redirect(url_for("settings_page", error=message))


@app.post("/settings/cameras")
def save_cameras():
    old = {c["slot"]: c for c in settings.camera_slots()}
    saved, names = [], set()
    for slot in range(1, settings.MAX_CAMERAS + 1):
        def field(key):
            return (request.form.get(f"{key}_{slot}") or "").strip()
        try:
            rtsp = unmask_url(field("rtsp"), old[slot]["rtsp_url"])
            detect = unmask_url(field("detect"), old[slot]["detect_url"])
        except MaskError as exc:
            return settings_error(f"Camera {slot}: {exc}")
        if any(u and not u.lower().startswith(("rtsp://", "rtsps://")) for u in (rtsp, detect)):
            return settings_error(f"Camera {slot}: stream addresses start with rtsp://")
        if slot == 1:
            name = settings.primary_camera()
            on = field("enabled") == "1"
            if on and not rtsp:
                return settings_error("Camera 1 needs a stream address (or switch it off)")
            entry = {"slot": 1} if on else {"slot": 1, "enabled": False}   # off: its name and recordings stay
            if rtsp != (env("RTSP_URL") or ""):      # only what differs from .env is stored
                entry["rtsp_url"] = rtsp
            if detect != (env("DETECT_URL") or ""):
                entry["detect_url"] = detect
        else:
            name = field("name").lower()
            if not name and not rtsp:
                continue                              # empty slot
            if not settings.CAMERA_NAME_RE.match(name):
                return settings_error(f"Camera {slot}: the name must be lowercase letters, digits or _ (max 24)")
            if not rtsp:
                return settings_error(f"Camera {slot}: enter the stream address")
            entry = {"slot": slot, "name": name, "rtsp_url": rtsp, "detect_url": detect,
                     "enabled": field("enabled") == "1"}
        if name in names:
            return settings_error(f"Camera {slot}: the name {name} is already used")
        names.add(name)
        saved.append(entry)
    settings.update(cameras=saved)
    return redirect(url_for("settings_page", saved="cameras") + "#cameras")


@app.post("/settings/cameras/test")
def test_camera():
    """Grab one picture from the address in the form (stored password filled in), to check a camera before saving."""
    slot = request.form.get("slot", type=int) or 0
    old = {c["slot"]: c for c in settings.camera_slots()}.get(slot, {})
    try:
        url = unmask_url((request.form.get("url") or "").strip(), old.get("rtsp_url"))
    except MaskError as exc:
        return Response(str(exc)[0].upper() + str(exc)[1:], 400, mimetype="text/plain")
    if not url.lower().startswith(("rtsp://", "rtsps://")):
        return Response("Enter an rtsp:// address first", 400, mimetype="text/plain")
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-rtsp_transport", "tcp", "-i", url,
           "-frames:v", "1", "-vf", "scale=640:-2", "-f", "image2", "-c:v", "mjpeg", "pipe:1"]
    try:
        out = subprocess.run(cmd, capture_output=True, timeout=20)
    except subprocess.TimeoutExpired:
        return Response("No picture within 20 seconds - check the address and that the camera is on", 502,
                        mimetype="text/plain")
    if out.returncode or not out.stdout:
        err = out.stderr.decode(errors="replace").strip().splitlines()
        msg = (err[-1] if err else "no picture").replace(url, mask_url(url))
        return Response(f"Camera did not answer: {msg}", 502, mimetype="text/plain")
    return Response(out.stdout, mimetype="image/jpeg", headers={"Cache-Control": "no-store"})


def scan_default():
    """The /24 of the address the browser used for camwatch: usually the LAN the cameras are on."""
    host = request.host.rsplit(":", 1)[0].strip("[]")
    try:
        ip = ipaddress.ip_address(host)
        if ip.version == 4 and ip.is_private and not ip.is_loopback:
            return str(ipaddress.ip_network(f"{ip}/24", strict=False))
    except ValueError:
        pass
    return "192.168.1.0/24"


@app.post("/settings/cameras/scan")
def scan_cameras():
    """Devices with an open RTSP port in a subnet, and whether they speak ONVIF."""
    import onvif
    try:
        found = onvif.scan(request.form.get("subnet") or scan_default())
    except ValueError as exc:
        return as_json({"error": str(exc)}), 400
    used = {}
    for c in settings.camera_slots():
        login = split_login(c["rtsp_url"])
        host = re.split(r"[:/?]", login[3] if login else c["rtsp_url"].partition("://")[2], maxsplit=1)[0]
        if host:
            used[host] = c["name"]
    return as_json({"found": [{**f, "used_by": used.get(f["ip"])} for f in found]})


@app.post("/settings/cameras/onvif")
def onvif_streams():
    """Log in to a camera over ONVIF and list its streams (with the login in the URLs, for the form)."""
    import onvif
    f = request.form
    ip = (f.get("ip") or "").strip()
    try:
        if not ipaddress.ip_address(ip).is_private:
            raise ValueError
        port = int(f.get("port") or 80)
    except ValueError:
        return as_json({"error": "enter the camera's LAN address"}), 400
    try:
        return as_json(onvif.streams(ip, port, (f.get("user") or "").strip(), f.get("password") or ""))
    except onvif.OnvifError as exc:
        return as_json({"error": str(exc)}), 502


@app.post("/settings/ntfy")
def save_ntfy():
    old = settings.ntfy()
    f = request.form
    url = (f.get("url") or "").strip().rstrip("/") or "https://ntfy.sh"
    topic, status_topic = (f.get("topic") or "").strip(), (f.get("status_topic") or "").strip()
    priority = f.get("priority") or "high"
    if not url.lower().startswith(("http://", "https://")):
        return settings_error("ntfy server: the address starts with https:// (e.g. https://ntfy.sh)")
    for t in (topic, status_topic):
        if t and not re.match(r"^[-_A-Za-z0-9]{1,64}$", t):
            return settings_error(f"ntfy topic {t}: letters, digits, - and _ only (max 64)")
    if priority not in settings.NTFY_PRIORITIES:
        abort(400)
    user = (f.get("user") or "").strip()
    token = (f.get("token") or "").strip() or ("" if f.get("clear_token") else old["token"])
    password = f.get("password") or ("" if f.get("clear_password") or not user else old["password"])
    link = (f.get("link_url") or "").strip().rstrip("/")
    if link and not re.match(r"^https?://[^\s/]+(:\d+)?(/\S*)?$", link):
        return settings_error("Link in pushes: enter the address you open camwatch with, e.g. http://192.168.1.20:8080")
    cfg = {"url": url, "topic": topic, "status_topic": status_topic, "token": token, "user": user,
           "password": password if user else "", "priority": priority, "link_url": link}
    settings.update(ntfy=cfg)
    result = None
    if f.get("test"):
        from common import Ntfy
        n = Ntfy(log)
        result = "ok" if n.send("If you see this, camwatch push notifications work.", title="camwatch test",
                                tags="white_check_mark", priority=priority) else (n.last_error or "failed")
    return redirect(url_for("settings_page", saved="ntfy", ntfy=result) + "#ntfy")


# ---------- updates (app/updates.py, extras/update.py on the host) ----------

@app.post("/settings/update")
def save_update():
    old, f = updates.options(), request.form
    repo, folder = (f.get("repo") or "").strip(), (f.get("folder") or "").strip().strip("/")
    branch = (f.get("branch") or "").strip() or "main"
    if not re.match(r"^[-\w.]+/[-\w.]+$", repo):
        return settings_error("Updates: the GitHub repository looks like owner/name")
    if not re.match(r"^[-\w. /]{1,100}$", folder) or ".." in folder or not re.match(r"^[-\w./]{1,100}$", branch):
        return settings_error("Updates: check the folder and the branch")
    token = (f.get("token") or "").strip() or ("" if f.get("clear_token") else old["token"])
    settings.update(update={"repo": repo, "folder": folder, "branch": branch, "token": token})
    updates.check(force=True)
    return redirect(url_for("settings_page", saved="update") + "#updates")


@app.route("/requests", methods=["GET", "POST"])
def requests_page():
    """Request a feature: kept here and sent to GitHub as an issue (app/feature_requests.py)."""
    sent = None
    if request.method == "POST":
        title = " ".join((request.form.get("title") or "").split())[:120]
        text = (request.form.get("text") or "").strip()[:5000]
        if not title or not text:
            return redirect(url_for("requests_page", error="Fill in what you want and tell us more."))
        sent = feature_requests.submit(title, text, " ".join((request.form.get("name") or "").split())[:60])
        log.info("feature request %r: %s", title, f"issue #{sent['number']}" if sent.get("number") else sent.get("error"))
        return redirect(url_for("requests_page", sent=sent["id"]))
    feature_requests.refresh_states()
    rows = feature_requests.load()
    sent = next((r for r in rows if r["id"] == request.args.get("sent")), None)
    opts = updates.options()
    return render_template("requests.html", rows=rows, sent=sent, error=request.args.get("error"),
                           repo=opts["repo"], has_token=bool(opts["token"]))


@app.post("/requests/<request_id>/resend")
def resend_request(request_id):
    row = feature_requests.resend(request_id)
    if row is None:
        abort(404)
    return redirect(url_for("requests_page", sent=request_id))


@app.get("/settings/update/key")
def update_key_page():
    """Step by step: make the GitHub access key for Settings -> Updates."""
    return render_template("update_key.html", upd=updates.options())


@app.get("/api/update")
def api_update():
    """Is there a newer camwatch on GitHub? Cached 10 minutes; ?force=1 asks GitHub again."""
    return as_json(updates.check(force=request.args.get("force") == "1"))


@app.get("/api/update/status")
def api_update_status():
    """What the host helper reports while it updates, plus the running version."""
    s = updates.status()
    return as_json({**{key: s.get(key) for key in ("helper", "state", "message", "started", "finished")},
                    "version": app_version()})


@app.post("/settings/update/run")
def run_update():
    sha = (request.form.get("sha") or "").strip()
    if not updates.status()["helper"]:
        return settings_error("Updates: the update helper is not installed on the server. Run sudo ./deploy.sh once.")
    if updates.status()["state"] in ("waiting", "running"):
        return redirect(url_for("settings_page") + "#updates")
    found = updates.check(force=True)
    latest = found.get("latest") or {}
    if found.get("error") or not found.get("newer") or latest.get("sha") != sha:
        return settings_error("Updates: " + (found.get("error") or "this version is no longer the newest - check again"))
    updates.request_update(sha, latest["version"])
    log.info("update to %s (%s) requested", latest["version"], sha[:7])
    return redirect(url_for("settings_page") + "#updates")


# ---------- off-site storage (app/offsite.py) ----------

PATH_RE = re.compile(r"^[\w .@/-]{1,200}$")
_connecting = {}     # the destination being connected: {"type", "path"} (one at a time)


def offsite_step(step):
    """A step of connecting, as JSON. "done" = save the destination, set up encryption, test it."""
    log.info("off-site connect (%s): %s%s", _connecting.get("type"), step["step"],
             f" {step.get('name')}" if step["step"] == "question" else f" - {step['error']}" if step.get("error") else "")
    if step["step"] == "done":
        opts = offsite.options()
        opts.update(type=_connecting["type"], path=_connecting["path"], enabled=True,
                    connected_at=dt.datetime.now().isoformat(timespec="seconds"))
        try:
            if opts["encrypt"]:
                offsite.ensure_crypt(opts["path"])
        except offsite.RcloneError as exc:
            return as_json({"step": "error", "error": f"encryption setup failed: {exc}"}), 502
        settings.update(offsite=opts)
        result = offsite.test(opts) or "ok"
        log.info("off-site connected to %s, test upload: %s", opts["type"], result)
        return as_json({"step": "done", "test": result})
    return as_json(step)


@app.post("/settings/offsite/connect")
def offsite_connect():
    f = request.form
    kind, path = f.get("type", ""), (f.get("path") or "").strip().strip("/")
    if kind not in offsite.TYPES:
        return as_json({"step": "error", "error": "choose where to store"}), 400
    if not PATH_RE.match(path) or ".." in path:
        return as_json({"step": "error", "error": "enter a folder (letters, digits, - _ . / only)"}), 400
    _connecting.clear()
    _connecting.update(type=kind, path=path)
    try:
        if offsite.TYPES[kind].get("oauth"):
            return as_json({"step": "oauth", "url": offsite.authorizer.start(kind)})
        fields = {name: (f.get(f"f_{name}") or "").strip() for name, _, _ in offsite.TYPES[kind]["fields"]}
        if kind == "s3":
            fields["provider"] = fields.get("provider") or "Other"
        return offsite_step(offsite.create_remote(kind, fields))
    except offsite.RcloneError as exc:
        log.warning("off-site connect (%s) failed: %s", _connecting.get("type"), exc)
        if not offsite.options()["type"]:
            offsite.disconnect()        # don't keep a half-made destination (with its password) around
        return as_json({"step": "error", "error": str(exc)}), 502


@app.post("/settings/offsite/oauth")
def offsite_oauth():
    if not _connecting:
        return as_json({"step": "error", "error": "press Connect again"}), 400
    try:
        token = offsite.authorizer.finish(request.form.get("pasted") or "")
        return offsite_step(offsite.create_remote(_connecting["type"], {}, token=token))
    except offsite.RcloneError as exc:
        log.warning("off-site connect (%s) failed: %s", _connecting.get("type"), exc)
        return as_json({"step": "error", "error": str(exc)}), 502


@app.post("/settings/offsite/answer")
def offsite_answer():
    if not _connecting:
        return as_json({"step": "error", "error": "press Connect again"}), 400
    try:
        return offsite_step(offsite.answer(request.form.get("state", ""), request.form.get("result", "")))
    except offsite.RcloneError as exc:
        log.warning("off-site connect (%s) failed: %s", _connecting.get("type"), exc)
        return as_json({"step": "error", "error": str(exc)}), 502


@app.post("/settings/offsite")
def offsite_save():
    f = request.form
    opts = offsite.options()
    try:
        keep = int(f.get("keep_days") or 30)
        bw = float(f.get("bwlimit_mbps") or 0)
        if not 1 <= keep <= 3650 or not 0 <= bw <= 1000:
            raise ValueError
    except ValueError:
        return settings_error("Off-site storage: keep 1-3650 days, bandwidth 0-1000 MB/s")
    encrypt = f.get("encrypt") == "1"
    opts.update(enabled=f.get("enabled") == "1", instant=f.get("instant") == "1", encrypt=encrypt, keep_days=keep,
                bwlimit_mbps=bw, what={k: f.get(f"what_{k}") == "1" for k in offsite.DEFAULTS["what"]})
    if encrypt and opts["type"] and offsite.connected():
        try:
            offsite.ensure_crypt(opts["path"])
        except offsite.RcloneError as exc:
            return settings_error(f"Off-site encryption: {exc}")
    settings.update(offsite=opts)
    return redirect(url_for("settings_page", saved="offsite") + "#offsite")


@app.post("/settings/offsite/test")
def offsite_test():
    if not offsite.connected():
        return as_json({"error": "not connected"}), 400
    return as_json({"result": offsite.test() or "ok"})


@app.post("/settings/offsite/run")
def offsite_run():
    offsite.STATE.mkdir(parents=True, exist_ok=True)
    offsite.RUN_NOW.touch()
    return redirect(url_for("settings_page", saved="offsite-run") + "#offsite")


@app.post("/settings/offsite/disconnect")
def offsite_disconnect():
    offsite.disconnect()
    settings.update(offsite={**offsite.options(), "type": "", "path": "", "enabled": False})
    return redirect(url_for("settings_page", saved="offsite-off") + "#offsite")


@app.get("/settings/offsite/recovery")
def offsite_recovery():
    opts = offsite.options()
    text = offsite.recovery_text(opts) if offsite.connected() else None
    if not text:
        abort(404)
    return Response(text, mimetype="text/plain", headers={
        "Content-Disposition": "attachment; filename=camwatch-offsite-keys.txt", "Cache-Control": "no-store"})


def mqtt_check(cfg):
    """Connect to the broker once; None when it works, else what went wrong."""
    import paho.mqtt.client as mqtt
    result, done = {}, threading.Event()

    def on_connect(client, userdata, flags, reason_code, properties):
        result["rc"] = reason_code
        done.set()
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"camwatch-settings-{secrets.token_hex(3)}")
    if cfg["mqtt_user"]:
        client.username_pw_set(cfg["mqtt_user"], cfg["mqtt_password"])
    client.on_connect = on_connect
    try:
        client.connect(cfg["mqtt_host"], cfg["mqtt_port"], keepalive=10)
    except (OSError, ValueError) as exc:
        return f"cannot reach {cfg['mqtt_host']}:{cfg['mqtt_port']} ({exc})"
    client.loop_start()
    done.wait(8)
    client.disconnect()
    client.loop_stop()
    if "rc" not in result:
        return "the broker did not answer"
    return f"the broker refused the login ({result['rc']})" if result["rc"].is_failure else None


@app.post("/settings/integration")
def save_integration():
    old = settings.integration()
    f = request.form
    host = (f.get("mqtt_host") or "").strip()
    user = (f.get("mqtt_user") or "").strip()
    password = f.get("mqtt_password") or ""
    if not password and user and not f.get("clear_password"):
        password = old["mqtt_password"]        # empty field = keep the saved password
    webhook = (f.get("ha_webhook_url") or "").strip()
    try:
        port = int(f.get("mqtt_port") or 1883)
        if not 0 < port < 65536:
            raise ValueError
    except ValueError:
        return settings_error("MQTT port must be a number between 1 and 65535")
    if host and not re.match(r"^[A-Za-z0-9.\-]{1,253}$|^\[?[0-9A-Fa-f:]+\]?$", host):
        return settings_error("MQTT broker: enter a host name or IP address, without http:// or a port")
    if webhook and not webhook.lower().startswith(("http://", "https://")):
        return settings_error("The webhook URL starts with http:// or https://")
    cfg = {"mqtt_host": host, "mqtt_port": port, "mqtt_user": user, "mqtt_password": password if user else "",
           "ha_webhook_url": webhook}
    settings.update(integration=cfg)
    mqtt = (mqtt_check(cfg) or "ok") if host else None
    return redirect(url_for("settings_page", saved="integration", mqtt=mqtt) + "#ha")


@app.post("/arm")
def quick_arm():
    settings.update(mode="disarmed" if settings.is_armed(settings.load()) else "armed")
    return redirect(request.referrer or url_for("index"))


@app.get("/zones")
def zones_page():
    camera = camera_arg()
    return render_template("zones.html", zones=settings.zones_for(settings.load(), camera), camera=camera,
                           cameras=cameras(), people=people())


@app.post("/zones")
def save_zones():
    """Replace the zones of one camera; the other cameras' zones are kept."""
    camera = camera_arg()
    zones = []
    for z in (request.get_json(silent=True) or {}).get("zones", []):
        name = str(z.get("name", "")).strip()[:40]
        pts = [[min(1.0, max(0.0, float(x))), min(1.0, max(0.0, float(y)))] for x, y in z.get("points", [])]
        if name and z.get("type") in ("ignore", "trigger", "house", "street", "parking", "package") and len(pts) >= 3:
            zones.append({"name": name, "type": z["type"], "camera": camera,
                          "points": [[round(x, 4), round(y, 4)] for x, y in pts]})
    conf = settings.load()
    others = [z for z in conf.get("zones", []) if z not in settings.zones_for(conf, camera)]
    settings.update(zones=others + zones)
    return {"saved": len(zones)}


@app.get("/plates")
def plates_page():
    sightings = []
    try:
        for line in (DATA_DIR / "plates.jsonl").read_text().splitlines()[-3000:]:
            sightings.append(json.loads(line))
    except (FileNotFoundError, ValueError):
        pass
    # Include plates found by the backfill tool (only stored in clip .json files)
    seen = {}
    for c in all_clips():
        for p in c["plates"]:
            e = seen.setdefault(p["plate"], {"plate": p["plate"], "name": p["name"], "count": 0, "last": None})
            e["count"] += 1
            when = f"{c['day']} {c['time']}"
            if not e["last"] or when > e["last"]["when"]:
                e["last"] = {"when": when, "day": c["day"], "stem": c["stem"], "crop": p.get("crop")}
    return render_template("plates.html", known=known_plates(), seen=sorted(seen.values(), key=lambda e: e["last"]["when"], reverse=True),
                           people=people())


@app.post("/plates")
def add_plate():
    plate = normalize(request.form.get("plate"))
    name = (request.form.get("name") or "").strip()[:40]
    if len(plate) < 2:
        abort(400, "Invalid plate")
    plates = [p for p in known_plates() if normalize(p["plate"]) != plate]
    plates.append({"plate": plate, "name": name or plate})
    settings.update(plates=sorted(plates, key=lambda p: p["name"].lower()))
    return redirect(request.form.get("next") or url_for("plates_page"))


@app.post("/plates/<plate>/delete")
def delete_plate(plate):
    settings.update(plates=[p for p in known_plates() if normalize(p["plate"]) != normalize(plate)])
    return redirect(url_for("plates_page"))


LOG_RANGES = {"1": "Today", "7": "7 days", "30": "30 days", "all": "All"}
LOG_KINDS = {"": "Everything", "person": "People", "vehicle": "Vehicles", "animal": "Animals"}


@app.get("/log")
def log_page():
    """Who came and when, from the presence service's database."""
    rng = request.args.get("range") if request.args.get("range") in LOG_RANGES else "7"
    kind = request.args.get("kind") if request.args.get("kind") in LOG_KINDS else ""
    who = (request.args.get("who") or "").strip()
    since = (dt.datetime.combine(dt.date.today(), dt.time()) - dt.timedelta(days=int(rng) - 1)
             if rng != "all" else dt.datetime(1970, 1, 1))
    try:
        from presence import connect
        db = connect()
    except Exception as e:
        return render_template("log.html", error=str(e), days=[], last_seen=[], rng=rng, kind=kind, who=who,
                               ranges=LOG_RANGES, kinds=LOG_KINDS, people=people())
    try:
        with db.cursor() as cur:
            cur.execute("""SELECT id, day, stem, started_at, duration_s, direction, labels, clip_deleted, faces_seen, loitering
                           FROM visits WHERE test = 0 AND started_at >= %s ORDER BY started_at DESC LIMIT 2000""", (since,))
            visits = cur.fetchall()
            by_visit = {}
            if visits:
                cur.execute(f"""SELECT visit_id, kind, name, source, detail, confidence, direction FROM visitors
                                WHERE visit_id IN ({','.join(['%s'] * len(visits))})""", [v["id"] for v in visits])
                for r in cur.fetchall():
                    by_visit.setdefault(r["visit_id"], []).append(r)
            cur.execute("""SELECT p.name, p.kind, MAX(v.started_at) AS last, COUNT(DISTINCT v.id) AS visits,
                                  MAX(CASE WHEN p.direction = 'arrived' THEN v.started_at END) AS last_arrived,
                                  MAX(CASE WHEN p.direction = 'left' THEN v.started_at END) AS last_left
                           FROM visitors p JOIN visits v ON v.id = p.visit_id
                           WHERE p.name IS NOT NULL AND v.test = 0 GROUP BY p.name, p.kind ORDER BY last DESC""")
            last_seen = cur.fetchall()
    finally:
        db.close()

    days_out = {}
    for v in visits:
        vis = by_visit.get(v["id"], [])
        if kind and not any(p["kind"] == kind for p in vis):
            continue
        if who == "unknown":
            if not any(p["kind"] == "person" and not p["name"] for p in vis):
                continue
        elif who and not any(p["name"] == who for p in vis):
            continue
        v["visitors"] = sorted(vis, key=lambda p: (p["name"] is None, p["kind"] != "person", p["name"] or ""))
        v["labels"] = json.loads(v["labels"] or "{}")
        days_out.setdefault(v["started_at"].date(), []).append(v)
    return render_template("log.html", error=None, days=list(days_out.items()), last_seen=last_seen, rng=rng,
                           kind=kind, who=who, ranges=LOG_RANGES, kinds=LOG_KINDS, people=people(),
                           names=sorted({r["name"] for r in last_seen}), today=dt.date.today())


@app.get("/report")
def report_page():
    """Weekly report: visits per day / hour, who came, cars, packages, door visits, heatmap."""
    try:
        day = dt.date.fromisoformat(request.args.get("week") or dt.date.today().isoformat())
    except ValueError:
        abort(400)
    monday = day - dt.timedelta(days=day.weekday())
    try:
        from presence import connect, weekly_report
        db = connect()
        try:
            r = weekly_report(db, monday)
        finally:
            db.close()
        error = None
    except Exception as e:
        r, error = None, str(e)
    label = request.args.get("label", "person")
    if label not in ("person", "car", "dog", "cat", "bicycle"):
        label = "person"
    return render_template("report.html", r=r, error=error, monday=monday, label=label, people=people(),
                           prev_week=monday - dt.timedelta(days=7), next_week=monday + dt.timedelta(days=7),
                           this_monday=dt.date.today() - dt.timedelta(days=dt.date.today().weekday()))


# ---------- recurring strangers (groups computed by facematch, app/strangers.py) ----------

def stranger_groups():
    return (load_json(DATA_DIR / "strangers.json", {}) or {}).get("groups", [])


@app.get("/strangers")
def strangers_page():
    data = load_json(DATA_DIR / "strangers.json", {}) or {}
    return render_template("strangers.html", groups=data.get("groups", []), updated=data.get("updated"),
                           days=data.get("days", 30), people=people(), named=request.args.get("named"))


@app.post("/strangers/name")
def name_stranger():
    group = next((g for g in stranger_groups() if g["id"] == request.form.get("id")), None)
    if group is None:
        abort(404)
    name = (request.form.get("new_name") or "").strip() or (request.form.get("name") or "").strip()
    for i, f in enumerate(group["faces"]):
        if not (DAY_RE.match(f["day"]) and STEM_RE.match(f["stem"])):
            continue
        # a few clear examples are enough for the library; every clip gets the tag
        tag_face(REC_DIR / f["day"], f["day"], f["stem"], name, f["crop"], add_to_library=i < 5)
    (DATA_DIR / "strangers.refresh").touch()   # facematch regroups on its next pass
    return redirect(url_for("strangers_page", named=name))


@app.post("/strangers/hide")
def hide_stranger():
    hidden = load_json(DATA_DIR / "strangers_hidden.json", []) or []
    gid = request.form.get("id", "")
    if gid and gid not in hidden:
        hidden.append(gid)
        (DATA_DIR / "strangers_hidden.json").write_text(json.dumps(hidden))
        data = load_json(DATA_DIR / "strangers.json", {}) or {}
        data["groups"] = [g for g in data.get("groups", []) if g["id"] != gid]
        (DATA_DIR / "strangers.json").write_text(json.dumps(data))
    return redirect(url_for("strangers_page"))


@app.get("/search")
def search_page():
    """Find recordings by description, e.g. "white van" or "person with a dog" (CLIP, see app/search.py)."""
    q = (request.args.get("q") or "").strip()[:100]
    results, error = [], None
    if q:
        try:
            import search
            for key, score in search.search(q, top=48):
                day, stem = key.split("/", 1)
                if (REC_DIR / day / f"{stem}.json").exists():
                    results.append({**clip(day, stem), "score": score})
        except Exception as e:  # model not installed, index missing, ...
            error = str(e)
    indexed = 0
    try:
        import numpy as _np
        with _np.load(DATA_DIR / "search_index.npz") as z:
            indexed = len(z["keys"])
    except Exception:
        pass
    return render_template("search.html", q=q, results=results, error=error, indexed=indexed, people=people(),
                           examples=["person with a dog", "white van", "red jacket", "delivery driver", "bicycle",
                                     "someone carrying a box", "child", "umbrella", "car at night"])


@app.post("/simulate-motion")
def simulate_motion():
    camera = camera_arg()
    (LIVE_DIR / camera).mkdir(parents=True, exist_ok=True)
    (LIVE_DIR / camera / "simulate_motion").touch()
    log.info("simulated motion requested for %s", camera)
    return redirect(url_for("live", sent=1, camera=camera))


# ---------- wall view: phone/tablet "Cameras" page (app/wallview.html) and its JSON ----------

SIDECAR_RE = re.compile(r"\.(faces|labels|track)\.json$")
WALLVIEW_HTML = Path(__file__).with_name("wallview.html")
_visits = {}  # meta path -> (signature, visit dict)


def _mtime(path):
    try:
        return path.stat().st_mtime
    except FileNotFoundError:
        return 0.0


def visit_json(meta_path, known):
    """One recording for the wall view, cached until one of its sidecars (or the known plates) changes."""
    folder, stem = meta_path.parent, meta_path.name[:-5]
    sig = tuple(_mtime(folder / f"{stem}{s}") for s in (".json", ".faces.json", ".labels.json", ".star")) + (settings.mtime(),)
    hit = _visits.get(meta_path)
    if hit and hit[0] == sig:
        return hit[1]
    meta = load_json(meta_path, {})
    faces = load_json(folder / f"{stem}.faces.json") or {}
    people, named = [], set()
    for k in faces.get("known", []) + load_json(folder / f"{stem}.labels.json", []):
        if k.get("name") and k["name"] not in named:
            named.add(k["name"])
            people.append({"name": k["name"], "crop": k.get("crop")})
    labels = meta.get("labels") or {}
    plates = [{"plate": p["plate"], "name": (match_known(p["plate"], known) or {}).get("name") or p.get("name")}
              for p in meta.get("plates") or [] if p.get("plate")]
    vehicles = [{**m, "name": (match_known(m["plate"], known) or {}).get("name") or m.get("name")} if m.get("plate") else m
                for m in meta.get("vehicles") or []]
    v = {"day": folder.name, "stem": stem, "start": meta.get("start"), "end": meta.get("end") or meta.get("start"),
         "labels": sorted(labels, key=lambda k: -labels[k]) if isinstance(labels, dict) else list(labels),
         "people": people, "unknown": len(faces.get("unknown", [])), "vehicles": vehicles, "plates": plates,
         "test": bool(meta.get("test")), "star": (folder / f"{stem}.star").exists(),
         "packages": [{"kind": p.get("kind"), "zone": p.get("zone"), "image": p.get("image")} for p in meta.get("packages") or []],
         "video": meta.get("video") or f"{stem}.mp4", "camera": meta.get("camera") or camera_of(stem),
         "unusual": meta.get("unusual")}
    _visits[meta_path] = (sig, v)
    return v


def day_visits(day):
    """Finished, non-test recordings of one day, newest first."""
    known = known_plates()
    out = []
    for meta_path in sorted((REC_DIR / day).glob("*.json"), reverse=True):
        if SIDECAR_RE.search(meta_path.name):
            continue
        v = visit_json(meta_path, known)
        if v["start"] and not v["test"]:
            group = day_groups(day).get(v["stem"], [])
            out.append({**v, "visit": [g["camera"] for g in group if g["stem"] != v["stem"]]})   # copy: v is cached
    return out


def as_json(data):
    return Response(json.dumps(data), mimetype="application/json", headers={"Cache-Control": "no-store"})


@app.get("/view")
def wall_view():
    html = WALLVIEW_HTML.read_text(encoding="utf-8")
    armed = settings.is_armed(settings.load())
    return Response(html.replace("__ARMED__", "true" if armed else "false"), mimetype="text/html")


@app.get("/api/cameras")
def api_cameras():
    return as_json(cameras())


@app.get("/api/days")
def api_days():
    cam = request.args.get("camera")
    return as_json([{"day": d, "count": n} for d in days()
                    if (n := len([v for v in day_visits(d) if not cam or v["camera"] == cam]))])


@app.get("/api/visits")
def api_visits():
    day = request.args.get("day", "")
    if not DAY_RE.match(day):
        abort(400)
    cam = request.args.get("camera")
    return as_json([v for v in day_visits(day) if not cam or v["camera"] == cam])


@app.get("/api/thumb/<day>/<stem>.jpg")
def api_thumb(day, stem):
    folder = check(day, stem)
    data = resized_jpeg(cv2.imread(str(folder / f"{stem}.jpg")), request.args.get("w", 480, type=int))
    if data is None:
        abort(404)
    return Response(data, mimetype="image/jpeg", headers={"Cache-Control": "max-age=300"})


@app.get("/api/clip/<day>/<stem>")
def api_clip(day, stem):
    """Faces, tags, plates and star of one clip, for tagging from the wall view."""
    check(day, stem)
    c = clip(day, stem)
    tagged = {t.get("crop"): t["name"] for t in c["labels"] if t.get("crop")}
    faces = [{"crop": k["crop"], "name": k["name"], "score": k.get("score"), "kind": "known", "tag": tagged.get(k["crop"])}
             for k in (c["faces"] or {}).get("known", []) if k.get("crop")]
    faces += [{"crop": u["crop"], "name": None, "guess": u.get("best_guess"), "kind": "unknown", "tag": tagged.get(u["crop"])}
              for u in (c["faces"] or {}).get("unknown", []) if u.get("crop")]
    return as_json({"faces": faces, "tags": [{"name": t["name"], "crop": t.get("crop")} for t in c["labels"]],
                    "plates": [{"plate": p["plate"], "name": p.get("name")} for p in c["plates"]],
                    "star": c["starred"], "analysed": c["faces"] is not None, "people": people()})


# ---------- heatmap: where people (or cars, dogs...) were, from the recorder's tracks ----------

HEAT_W, HEAT_H = 160, 90
_heat_cache = {}


def heatmap_jpeg(first_day, last_day, label="person", width=1280, camera=None):
    """The newest snapshot of the period, darkened, with the density of `label` foot points drawn over it.
    Returns (jpeg bytes, number of points)."""
    folders = [REC_DIR / d for d in days() if first_day <= d <= last_day]
    camera = camera or settings.default_camera()
    tracks = [p for f in folders for p in f.glob("*.track.json") if camera_of(p.name[: -len(".track.json")]) == camera]
    key = (first_day, last_day, label, width, camera, len(tracks), max((_mtime(p) for p in tracks), default=0))
    if key in _heat_cache:
        return _heat_cache[key]
    grid = np.zeros((HEAT_H, HEAT_W), np.float32)
    points = 0
    for path in tracks:
        for t, lab, x, y, *_ in (load_json(path, {}) or {}).get("points") or []:
            if lab == label and 0 <= x <= 1 and 0 <= y <= 1:
                grid[min(HEAT_H - 1, int(y * HEAT_H)), min(HEAT_W - 1, int(x * HEAT_W))] += 1
                points += 1
    background = None
    for folder in sorted(folders, reverse=True):
        snaps = sorted(p for p in folder.glob("*.jpg") if "." not in p.stem and camera_of(p.stem) == camera)
        if snaps:
            background = cv2.imread(str(snaps[-1]))
            break
    if background is None:
        background = np.full((720, 1280, 3), 30, np.uint8)
    h, w = background.shape[:2]
    background = cv2.resize(background, (width, round(h * width / w)), interpolation=cv2.INTER_AREA)
    h, w = background.shape[:2]
    out = (background * 0.55).astype(np.float32)
    if points:
        heat = cv2.GaussianBlur(grid, (0, 0), 2.0)
        heat = np.log1p(heat) / np.log1p(heat).max()
        heat = cv2.resize(heat, (w, h), interpolation=cv2.INTER_CUBIC).clip(0, 1)
        colors = cv2.applyColorMap((heat * 255).astype(np.uint8), cv2.COLORMAP_INFERNO).astype(np.float32)
        alpha = np.clip(heat * 1.4, 0, 0.85)[..., None]
        out = out * (1 - alpha) + colors * alpha
    ok, jpg = cv2.imencode(".jpg", out.clip(0, 255).astype(np.uint8), [cv2.IMWRITE_JPEG_QUALITY, 85])
    result = (jpg.tobytes(), points)
    _heat_cache.clear()
    _heat_cache[key] = result
    return result


@app.get("/api/heatmap.jpg")
def api_heatmap():
    """?days=N (default 7, ending today) or ?from=YYYY-MM-DD&to=YYYY-MM-DD; ?label=person|car|dog|..."""
    label = request.args.get("label", "person")
    if not re.match(r"^[a-z ]{2,20}$", label):
        abort(400)
    if request.args.get("from") and request.args.get("to"):
        first, last = request.args["from"], request.args["to"]
        if not (DAY_RE.match(first) and DAY_RE.match(last)):
            abort(400)
    else:
        n = max(1, min(90, request.args.get("days", 7, type=int)))
        last = dt.date.today().isoformat()
        first = (dt.date.today() - dt.timedelta(days=n - 1)).isoformat()
    data, points = heatmap_jpeg(first, last, label, max(320, min(1920, request.args.get("w", 1280, type=int))), camera_arg())
    return Response(data, mimetype="image/jpeg", headers={"Cache-Control": "max-age=300", "X-Points": str(points)})


DASHBOARD_HTML = Path(__file__).with_name("dashboard.html")


# ---------- installable app (home screen) ----------

@app.get("/manifest.webmanifest")
def manifest():
    data = {"name": "camwatch", "short_name": "camwatch", "start_url": "/m", "scope": "/", "display": "standalone",
            "background_color": "#101418", "theme_color": "#101418",
            "icons": [{"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png"},
                      {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png"},
                      {"src": "/static/icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"}],
            "shortcuts": [{"name": "Live", "url": "/live"}, {"name": "Cameras", "url": "/view"}, {"name": "Clips", "url": "/"}]}
    return Response(json.dumps(data), mimetype="application/manifest+json")


SERVICE_WORKER = """// camwatch: lets the app be installed. Nothing is cached - every page and clip comes live from camwatch.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));
self.addEventListener('fetch', e => {
  if (e.request.mode !== 'navigate') return;
  e.respondWith(fetch(e.request).catch(() => new Response(
    '<!doctype html><meta name=viewport content="width=device-width"><body style="background:#101418;color:#eef2f6;font:16px system-ui;padding:24px">'
    + '<h2>camwatch is not reachable</h2><p>Check the connection (home Wi-Fi or VPN) and try again.</p>',
    {headers: {'Content-Type': 'text/html'}})));
});
"""


@app.get("/sw.js")
def service_worker():
    return Response(SERVICE_WORKER, mimetype="text/javascript", headers={"Cache-Control": "no-cache"})


MOBILE_HTML = Path(__file__).with_name("mobile.html")


@app.get("/m")
def mobile():
    """Phone home screen: what needs attention, live cameras, today, recent visits (app/mobile.html)."""
    return Response(MOBILE_HTML.read_text(encoding="utf-8"), mimetype="text/html")


@app.get("/dashboard")
def dashboard():
    return Response(DASHBOARD_HTML.read_text(encoding="utf-8"), mimetype="text/html")


def packages_waiting():
    """Package zones whose latest event is a delivery from the last 48 h."""
    latest = {}
    try:
        for line in (DATA_DIR / "packages.jsonl").read_text().splitlines():
            p = json.loads(line)
            latest[p.get("zone")] = p
    except (FileNotFoundError, ValueError):
        return []
    cutoff = dt.datetime.now() - dt.timedelta(hours=48)
    return [p for p in latest.values() if p.get("kind") == "delivered" and dt.datetime.fromisoformat(p["at"]) >= cutoff]


@app.get("/api/version")
def api_version():
    """Which camwatch this is: {"version", "commit", "date", "text"}."""
    return as_json(app_version())


@app.get("/api/status")
def api_status():
    """Today at a glance for the dashboard."""
    conf = settings.load()
    today = dt.date.today()
    week_days = {(today - dt.timedelta(days=i)).isoformat() for i in range(7)}
    visits_today = day_visits(today.isoformat()) if (REC_DIR / today.isoformat()).is_dir() else []
    week = sum(len(day_visits(d)) for d in days() if d in week_days)
    seen = {}
    for v in reversed(visits_today):  # oldest first, so the last assignment is the latest sighting
        for p in v["people"]:
            seen[p["name"]] = v["start"]
    last = None
    for d in days()[:3]:
        vs = day_visits(d)
        if vs:
            v = vs[0]
            names = [p["name"] for p in v["people"]]
            what = ", ".join(names) or (", ".join(v["labels"]) or "motion")
            last = {"day": v["day"], "stem": v["stem"], "start": v["start"], "who": what[:1].upper() + what[1:]}
            break
    usage = shutil.disk_usage(REC_DIR)
    off = offsite.options(conf)
    unusual = [{"day": v["day"], "stem": v["stem"], "camera": v["camera"], "start": v["start"], "reason": v["unusual"]}
               for v in visits_today if v.get("unusual")]
    return as_json({"camera": CAMERA, "version": app_version(), "unusual_today": unusual, "strangers": len(stranger_groups()),
                    "offsite": {"enabled": bool(off["enabled"] and off["type"]), "error": offsite.status().get("error") if off["type"] else None}, "cameras": cameras(), "armed": settings.is_armed(conf), "mode": conf["mode"], "schedule": conf["schedule"],
                    "today": len(visits_today), "week": week,
                    "people_today": [{"name": n, "last": t} for n, t in sorted(seen.items(), key=lambda kv: kv[1], reverse=True)],
                    "last": last, "packages_waiting": packages_waiting(), "snoozed": snoozes(conf),
                    "disk": {"total": usage.total, "used": usage.used, "free": usage.free}})


@app.get("/media/<day>/<path:name>")
def media(day, name):
    check(day)
    return send_from_directory(REC_DIR / day, name, conditional=True, max_age=3600)


@app.post("/clip/<day>/<stem>/label")
def add_label(day, stem):
    folder = check(day, stem)
    name = (request.form.get("new_name") or "").strip() or (request.form.get("name") or "").strip()
    tag_face(folder, day, stem, name, request.form.get("crop") or None, bool(request.form.get("add_to_library")))
    return redirect(url_for("clip_page", day=day, stem=stem))


def tag_face(folder, day, stem, name, crop=None, add_to_library=False):
    """Tag a person on a clip (optionally a specific face crop, which can also go to their reference photos)."""
    if not NAME_RE.match(name or "") or name.startswith("."):
        abort(400, "Name may only contain letters, digits, spaces and . ' -")
    if crop:
        crop_path = (folder / crop).resolve()
        if not crop.startswith(f"{stem}_faces/") or folder.resolve() not in crop_path.parents or not crop_path.is_file():
            abort(400)

    labels = load_json(folder / f"{stem}.labels.json", [])
    if crop:
        # Re-tagging a face replaces its earlier tag, and takes the face out of the previous person's photos
        for old in [t for t in labels if t.get("crop") == crop]:
            labels.remove(old)
            if old["name"] != name and NAME_RE.match(old["name"]):
                (PHOTOS_DIR / old["name"] / f"{stem}_{Path(crop).name}").unlink(missing_ok=True)
    labels.append({"name": name, "crop": crop, "at": dt.datetime.now().isoformat(timespec="seconds")})
    (folder / f"{stem}.labels.json").write_text(json.dumps(labels, indent=2))

    if crop and add_to_library:
        dest_dir = PHOTOS_DIR / name
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(crop_path, dest_dir / f"{stem}_{Path(crop).name}")
        log.info("added %s to library for %s", crop, name)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with (DATA_DIR / "sightings.jsonl").open("a") as f:
        f.write(json.dumps({"video": f"{day}/{stem}", "name": name, "manual": True,
                            "at": dt.datetime.now().isoformat(timespec="seconds")}) + "\n")


@app.post("/clip/<day>/<stem>/label/<int:idx>/delete")
def remove_label(day, stem, idx):
    folder = check(day, stem)
    labels = load_json(folder / f"{stem}.labels.json", [])
    if 0 <= idx < len(labels):
        labels.pop(idx)
        (folder / f"{stem}.labels.json").write_text(json.dumps(labels, indent=2))
    return redirect(url_for("clip_page", day=day, stem=stem))


@app.post("/clip/<day>/<stem>/delete")
def delete_clip(day, stem):
    folder = check(day, stem)
    if folder.is_dir():
        delete_event(folder, stem, log)
        if not any(folder.iterdir()):
            folder.rmdir()
    target = request.form.get("next")
    if target and STEM_RE.match(target) and any(folder.glob(f"{target}.*")):
        return redirect(url_for("clip_page", day=day, stem=target))
    return redirect(url_for("index", day=day))


MAX_PICKED = 500


def picked_clips():
    """The clips ticked on the Clips page: [(folder, day, stem)] from the form's "clip" = "day/stem" values."""
    out = []
    for value in request.form.getlist("clip")[:MAX_PICKED]:
        day, _, stem = value.partition("/")
        out.append((check(day, stem), day, stem))
    return out


@app.post("/clips/delete")
def delete_clips():
    picked = picked_clips()
    for folder, day, stem in picked:
        if folder.is_dir():
            delete_event(folder, stem, log)
            if not any(folder.iterdir()):
                folder.rmdir()
    log.info("deleted %d clips at once", len(picked))
    back = request.form.get("back") or ""
    return redirect(back if back.startswith("/") and not back.startswith("//") else url_for("index"))


class _Pipe(io.RawIOBase):
    """Write-only buffer that zipfile streams into; the response takes the bytes out as they come."""
    def __init__(self):
        self.chunks = []

    def writable(self):
        return True

    def write(self, b):
        self.chunks.append(bytes(b))
        return len(b)

    def take(self):
        out = b"".join(self.chunks)
        self.chunks.clear()
        return out


@app.post("/clips/download")
def download_clips():
    """The ticked clips (video and snapshot) as one zip, streamed: no copy on the server's disk."""
    files = []
    for folder, day, stem in picked_clips():
        for path in sorted(folder.glob(f"{stem}.*")):
            if path.is_file() and (path.suffix.lower() in VIDEO_EXT or path.name == f"{stem}.jpg"):
                files.append((path, f"{day}_{path.name}"))
    if not files:
        abort(404)

    def stream():
        pipe = _Pipe()
        with zipfile.ZipFile(pipe, "w", zipfile.ZIP_STORED, allowZip64=True) as zf:   # video is compressed already
            for path, name in files:
                try:
                    info = zipfile.ZipInfo.from_file(path, name)
                    with path.open("rb") as src, zf.open(info, "w", force_zip64=True) as dst:
                        while chunk := src.read(1 << 20):
                            dst.write(chunk)
                            yield pipe.take()
                except FileNotFoundError:      # deleted (or pruned) while downloading
                    continue
        yield pipe.take()

    name = f"camwatch-clips-{dt.datetime.now():%Y%m%d-%H%M}.zip"
    log.info("download of %d files as %s", len(files), name)
    return Response(stream(), mimetype="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


# ---------- templates ----------

TEMPLATES = {
    "base.html": """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#101418">
<meta name="apple-mobile-web-app-capable" content="yes"><meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent"><meta name="apple-mobile-web-app-title" content="camwatch">
<link rel="manifest" href="/manifest.webmanifest" crossorigin="use-credentials">
<link rel="icon" type="image/svg+xml" href="/static/logo.svg"><link rel="icon" type="image/png" sizes="192x192" href="/static/icon-192.png"><link rel="apple-touch-icon" href="/static/apple-touch-icon.png">
<script>if ('serviceWorker' in navigator && window.isSecureContext) navigator.serviceWorker.register('/sw.js').catch(() => {});</script>
<title>{% block title %}Clips{% endblock %} · camwatch</title>
<style>
/* Same "Wall" look as /dashboard and /view: dark slate, solid rounded tiles, one cyan accent. */
:root{--bg:#101418;--card:#1a2027;--card-hi:#222a33;--fg:#eef2f6;--muted:#8b98a8;--faint:#5d6b7b;--line:#2a333d;
  --accent:#38bdf8;--accent-ink:#062033;--danger:#ef4444;--known:#22c55e;--unknown:#f59e0b;
  --font:-apple-system,BlinkMacSystemFont,"SF Pro Display","Segoe UI",Inter,Roboto,sans-serif}
*{box-sizing:border-box}[hidden]{display:none!important}
html{background:var(--bg);color-scheme:dark;-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.45 var(--font);-webkit-tap-highlight-color:transparent}
::selection{background:rgba(56,189,248,.35)}
a{color:var(--accent);text-decoration:none}
a:focus-visible,button:focus-visible,select:focus-visible,input:focus-visible{outline:3px solid var(--accent);outline-offset:2px}
header{position:sticky;top:0;z-index:20;display:flex;gap:10px;align-items:center;padding:10px 14px;background:rgba(16,20,24,.97);border-bottom:1px solid var(--line)}
header .brand{font-weight:750;font-size:20px;color:var(--fg);flex:none;display:inline-flex;align-items:center;gap:8px}
header nav{display:flex;gap:6px;overflow-x:auto;flex:1;min-width:0;scrollbar-width:none;padding:2px 0}
header nav::-webkit-scrollbar{display:none}
header nav a{flex:none;min-height:36px;padding:0 13px;border-radius:999px;border:1px solid var(--line);background:var(--card);color:var(--fg);
  font-weight:650;font-size:13.5px;display:inline-flex;align-items:center;white-space:nowrap}
header nav a:hover{border-color:var(--accent)}
header nav a.on{background:var(--accent);border-color:var(--accent);color:var(--accent-ink)}
header .tools{display:flex;gap:6px;align-items:center;flex:none}
header .tools button.armed{border-color:var(--accent);color:var(--accent);background:var(--card)}
@media (max-width:820px){header{flex-wrap:wrap;row-gap:8px}header nav{order:3;flex-basis:100%}header .tools{margin-left:auto}}
main{max-width:1100px;margin:0 auto;padding:12px 12px 24px}
footer.ver{max-width:1100px;margin:0 auto;padding:0 12px 28px;color:var(--faint);font-size:12px;text-align:center}
h1{font-size:26px;font-weight:750;margin:16px 0 12px;line-height:1.2}h1 .muted{font-size:15px;font-weight:600}
h2{font-size:13px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);font-weight:700;margin:24px 2px 10px}
h2 .muted{text-transform:none;letter-spacing:0}
.days{display:flex;gap:6px;overflow-x:auto;padding-bottom:4px;scrollbar-width:none}.days::-webkit-scrollbar{display:none}
.pill{flex:none;min-height:34px;padding:0 13px;border:1px solid var(--line);border-radius:999px;background:var(--card);color:var(--fg);
  font-size:13.5px;font-weight:650;display:inline-flex;align-items:center;white-space:nowrap}
.pill:hover{border-color:var(--accent)}
.pill.on{background:var(--accent);border-color:var(--accent);color:var(--accent-ink)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:10px}
@media (max-width:460px){.grid{grid-template-columns:1fr 1fr;gap:8px}}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;overflow:hidden;color:var(--fg);display:block;transition:border-color .15s}
.card:hover{border-color:var(--accent)}
.card img,.ph{width:100%;aspect-ratio:16/9;object-fit:cover;display:block;background:#0b0e12}
.card .meta{padding:8px 10px;display:flex;gap:6px;flex-wrap:wrap;align-items:center}
.time{font-weight:700;margin-right:auto;font-variant-numeric:tabular-nums}
.muted{color:var(--muted);font-size:13px}
.tag{font-size:12px;padding:1px 9px;border-radius:999px;border:1px solid currentColor;color:var(--muted);white-space:nowrap}
.tag.k{color:var(--known)}.tag.u{color:var(--unknown)}
video{width:100%;max-height:70vh;background:#000;border-radius:18px;display:block}
.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
button,select,input[type=text],input[type=password],input[type=number],input[type=time],input[type=file]{font:inherit;color:var(--fg);background:var(--card-hi);
  border:1px solid var(--line);border-radius:10px;padding:0 12px;min-height:38px}
input[type=file]{padding:6px 10px}
textarea{font:inherit;color:var(--fg);background:var(--card-hi);border:1px solid var(--line);border-radius:10px;padding:8px 12px;width:100%;resize:vertical}
.field{display:grid;gap:4px}
.field>span{font-size:11.5px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.field>span i{font-style:normal;font-weight:500;letter-spacing:0;text-transform:none;color:var(--faint)}
.field input{width:100%}
select{padding-right:8px}
button{cursor:pointer;font-weight:650;border-radius:999px;padding:0 15px}
button:hover{border-color:rgba(255,255,255,.25)}
button.primary{background:var(--accent);border-color:var(--accent);color:var(--accent-ink)}
button.danger{color:var(--danger);border-color:rgba(239,68,68,.6);background:transparent}
input[type=checkbox],input[type=radio]{accent-color:var(--accent);width:17px;height:17px;vertical-align:-3px}
label{cursor:pointer}
.faces{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:10px}
.face{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:10px}
.face img{width:100%;aspect-ratio:1;object-fit:cover;border-radius:12px;background:#0b0e12}
.face form{display:grid;gap:6px;margin-top:8px}
.box{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:14px}
.box.ok{border-color:rgba(34,197,94,.5)}.box.warn{border-color:rgba(245,158,11,.5)}.box.bad{border-color:rgba(239,68,68,.6)}
.inline{display:inline}
table{border-collapse:collapse}th{font-weight:600}td,th{padding:6px 8px 6px 0}
pre{background:#0b0e12;border:1px solid var(--line);border-radius:14px;padding:12px;overflow-x:auto;font-size:13px;margin:6px 0 0}
code{background:var(--card-hi);border:1px solid var(--line);border-radius:6px;padding:0 5px;font-size:13px}
.copy{float:right;font-size:12px;min-height:28px;padding:0 10px}
ol li,ul li{margin:4px 0}
.ok{color:var(--known)}.warn{color:var(--unknown)}.bad{color:#ef4444}
.star{background:none;border:0;font-size:22px;line-height:1;padding:0 4px;color:#f5b301;cursor:pointer;min-height:0}
.timeline{width:100%;height:56px;display:block;margin:4px 0 16px}
.timeline .bg{fill:var(--card);stroke:var(--line)}.timeline text{fill:var(--muted);font-size:11px}
.timeline .tick{stroke:var(--line)}.timeline a rect{cursor:pointer}
.k-known{fill:var(--known)}.k-person{fill:var(--accent)}.k-vehicle{fill:#f59e0b}.k-animal{fill:#a78bfa}
.k-test,.k-motion{fill:var(--faint)}
.tag.dir-arrived{color:var(--known)}.tag.dir-left{color:var(--accent)}.tag.dir-visited{color:var(--unknown)}
.legend{display:flex;gap:12px;flex-wrap:wrap;font-size:12px;color:var(--muted)}
.legend i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:4px;vertical-align:-1px}
</style></head><body>
<header><a class="brand" href="{{ url_for('dashboard') }}"><img src="/static/logo-mark.svg" alt="" width="36" height="29">camwatch</a>
<nav aria-label="Pages">{% for ep, label in [('dashboard', '🏠 Home'), ('wall_view', '📱 View'), ('index', '🎞 Clips'), ('search_page', '🔍 Search'),
  ('live', '📡 Live'), ('log_page', '📋 Log'), ('report_page', '📊 Report'), ('timelapse_page', '⏩ Timelapse'), ('people_page', '🧑 People'), ('strangers_page', '❔ Strangers'),
  ('plates_page', '🚗 Plates'), ('zones_page', '🗺 Zones'), ('settings_page', '⚙️ Settings'), ('ha_page', '🏠 Home Assistant')] %}
<a href="{{ url_for(ep) }}" class="{{ 'on' if request.endpoint == ep }}">{{ label }}</a>{% endfor %}</nav>
<div class="tools">{% if people %}<form method="get" action="{{ url_for('index') }}"><select name="person" onchange="this.form.submit()" aria-label="Filter by person">
<option value="">Person…</option>{% for p in people %}<option {{ 'selected' if p == person }}>{{ p }}</option>{% endfor %}</select></form>{% endif %}
<form method="post" action="{{ url_for('quick_arm') }}" title="Mode: {{ arm_mode }}"><button class="{{ 'armed' if armed }}">{{ '🛡 Armed' if armed else '🔕 Disarmed' }}</button></form></div>
</header>
<main>{% block body %}{% endblock %}</main>
<footer class="ver">camwatch {{ app_version.text }}{% if app_version.date %} · {{ app_version.date }}{% endif %} · <a href="{{ url_for('requests_page') }}">💡 Request a feature</a></footer></body></html>""",

    "requests.html": """{% extends "base.html" %}
{% block title %}Request a feature{% endblock %}
{% block body %}
<h1>Request a feature</h1>
{% if sent %}<p class="box {{ 'bad' if sent.error else 'ok' }}">{% if sent.error %}Your request is saved here, but GitHub did not get it: {{ sent.error }}.
<a href="{{ url_for('update_key_page') }}">How to make the access key</a>.{% else %}✓ Thank you! Your request is on GitHub as
<a href="{{ sent.url }}" target="_blank" rel="noopener">#{{ sent.number }}</a>.{% endif %}</p>{% endif %}
{% if error %}<p class="box bad">{{ error }}</p>{% endif %}
<div class="spair">
<form method="post" class="box" style="display:grid;gap:10px;align-self:start">
<p class="muted" style="margin:0">Tell us what CamWatch should do better. Each request goes to GitHub as an issue in
<code>{{ repo }}</code>, so the developer gets it.{% if not has_token %} <span class="warn">No access key yet: enter it in
<a href="{{ url_for('settings_page') }}#updates">Settings → Updates</a> first.</span>{% endif %}</p>
<label class="field"><span>What do you want? <i>one short line</i></span><input type="text" name="title" maxlength="120" required placeholder="e.g. Quiet hours for pushes"></label>
<label class="field"><span>Tell us more <i>why it helps you, and how it should work</i></span><textarea name="text" rows="6" maxlength="5000" required></textarea></label>
<label class="field"><span>Your name <i>optional · shows on GitHub</i></span><input type="text" name="name" maxlength="60" autocomplete="off"></label>
<div class="row"><button class="primary">Send request</button></div>
</form>
<div>
<h2 style="margin-top:0">Your requests</h2>
{% if not rows %}<p class="muted">No requests yet.</p>{% endif %}
<div style="display:grid;gap:8px">{% for r in rows %}
<div class="box" style="display:grid;gap:4px"><div class="row"><b>{{ r.title }}</b>
{% if r.number %}<a class="tag" href="{{ r.url }}" target="_blank" rel="noopener">#{{ r.number }}</a>
<span class="state {{ 'on' if r.state == 'open' else '' }}">{{ '● open' if r.state == 'open' else '✓ done' if r.state == 'closed' else '' }}</span>
{% else %}<span class="warn">not sent</span>
<form class="inline" method="post" action="{{ url_for('resend_request', request_id=r.id) }}"><button>Send again</button></form>{% endif %}</div>
<div class="muted" style="white-space:pre-wrap">{{ r.text|truncate(300) }}</div>
<div class="muted" style="font-size:12px">{{ r.created|replace('T', ' ') }}{% if r.error and not r.number %} · <span class="bad">{{ r.error }}</span>{% endif %}</div></div>
{% endfor %}</div></div></div>
<style>.spair{display:grid;gap:24px;align-items:start}@media (min-width:980px){.spair{grid-template-columns:repeat(2,minmax(0,1fr))}}</style>
{% endblock %}""",

    "index.html": """{% extends "base.html" %}
{% block body %}
{% if cameras|length > 1 %}<nav class="days" style="margin-bottom:8px"><a class="pill {{ 'on' if not camera }}" href="{{ url_for('index', day=day) }}">All cameras</a>
{% for c in cameras %}<a class="pill {{ 'on' if c.name == camera }}" href="{{ url_for('index', day=day, camera=c.name) }}">{{ c.name }}</a>{% endfor %}</nav>{% endif %}
<nav class="days"><a class="pill {{ 'on' if starred }}" href="{{ url_for('index', starred=1) }}">★ Starred</a>
{% for d in days %}<a class="pill {{ 'on' if d == day and not person and not starred }}" href="{{ url_for('index', day=d) }}">{{ d }}</a>{% endfor %}</nav>
<div class="row"><h1>{{ heading }} <span class="muted">· {{ clips|length }} clip{{ '' if clips|length == 1 else 's' }}</span></h1>
{% if clips %}<span style="margin-left:auto"></span><button type="button" id="pick-start" onclick="picking(true)">☑ Select</button>{% endif %}</div>
{% if timeline %}
<svg class="timeline" viewBox="0 0 1440 56" preserveAspectRatio="none" role="img" aria-label="Events over the day">
<rect class="bg" x="0" y="0" width="1440" height="38" rx="6"/>
{% for h in range(0, 25, 3) %}<line class="tick" x1="{{ h * 60 }}" x2="{{ h * 60 }}" y1="0" y2="38"/>
<text x="{{ [[h * 60, 6]|max, 1420]|min }}" y="52" text-anchor="{{ 'start' if h == 0 else ('end' if h == 24 else 'middle') }}">{{ '%02d'|format(h) }}:00</text>{% endfor %}
{% for c in timeline %}<a href="{{ url_for('clip_page', day=c.day, stem=c.stem) }}"><title>{{ c.time }} · {{ (c.names + c.detected)|join(', ') or 'motion' }}</title>
<rect class="k-{{ c.kind }}" x="{{ c.minute }}" y="5" width="{{ [((c.duration or 20) / 60), 4]|max }}" height="28" rx="1.5"/></a>{% endfor %}
</svg>
<div class="row" style="margin:-8px 0 12px">
<div class="legend"><span><i class="k-known" style="background:var(--known)"></i>identified</span><span><i style="background:var(--accent)"></i>person</span>
<span><i style="background:#d97706"></i>vehicle</span><span><i style="background:#a855f7"></i>animal</span><span><i style="background:var(--muted)"></i>other</span></div>
{% if labels %}<span style="margin-left:auto"></span><a class="pill {{ 'on' if not label }}" href="{{ url_for('index', day=day) }}">All</a>
{% for l in labels %}<a class="pill {{ 'on' if l == label }}" href="{{ url_for('index', day=day, label=l) }}">{{ l }}</a>{% endfor %}{% endif %}</div>
{% endif %}
{% if not clips %}<p class="muted">Nothing here yet. Clips appear when the camera sees motion.</p>{% endif %}
<div class="grid">
{% for c in clips %}<a class="card" href="{{ url_for('clip_page', day=c.day, stem=c.stem) }}" data-clip="{{ c.day }}/{{ c.stem }}"{% if c.starred %} data-starred="1"{% endif %}>
<span class="pick" aria-hidden="true"></span>
{% if c.snapshot %}<img loading="lazy" src="{{ url_for('media', day=c.day, name=c.snapshot) }}" alt="">{% else %}<div class="ph"></div>{% endif %}
<div class="meta"><span class="time">{% if c.starred %}<span style="color:#f5b301">★</span> {% endif %}{% if person or starred %}{{ c.day }} {% endif %}{{ c.time }}</span>
{% if c.duration is not none %}<span class="muted">{{ c.duration }}s</span>{% endif %}</div>
<div class="meta" style="padding-top:0">{% for d in c.detected %}<span class="tag">{{ d }}</span>{% endfor %}{% for z in c.zones %}<span class="tag">@{{ z }}</span>{% endfor %}{% for p in c.plates %}<span class="tag {{ 'k' if p.name }}">🚗 {{ p.name or p.plate }}</span>{% endfor %}{% if c.loitering %}<span class="tag u">loitering</span>{% endif %}{% if c.unusual %}<span class="tag u" title="{{ c.unusual }}">⚠ unusual</span>{% endif %}{% if c.visit %}<span class="tag" title="Same visit">🔗 {{ c.visit|map(attribute='camera')|unique|join(', ') }}</span>{% endif %}{% for n in c.names %}<span class="tag k">{{ n }}</span>{% endfor %}
{% if c.unknown %}<span class="tag u">{{ c.unknown }} unknown</span>{% endif %}
{% if c.faces is none %}<span class="muted">not analysed yet</span>{% endif %}</div></a>
{% endfor %}</div>
{% if clips %}
<!-- Select: tick clips, then download them as one zip or delete them -->
<style>
.card{position:relative}
.card .pick{display:none;position:absolute;top:8px;left:8px;z-index:2;width:28px;height:28px;border-radius:8px;
  border:2px solid #fff;background:rgba(0,0,0,.45);box-shadow:0 1px 4px rgba(0,0,0,.5)}
body.picking .card .pick{display:block}
body.picking .card.sel{outline:3px solid var(--accent);outline-offset:-3px}
body.picking .card.sel .pick{background:var(--accent);border-color:var(--accent)}
body.picking .card.sel .pick::after{content:"✓";display:block;text-align:center;line-height:24px;font-weight:800;color:#0b1220}
#pickbar{display:none;position:fixed;left:50%;bottom:16px;transform:translateX(-50%);z-index:20;gap:8px;align-items:center;flex-wrap:wrap;
  justify-content:center;max-width:calc(100vw - 24px);padding:10px 14px;border-radius:18px;background:var(--card);border:1px solid var(--line);
  box-shadow:0 8px 30px rgba(0,0,0,.5)}
body.picking #pickbar{display:flex}
body.picking main{padding-bottom:110px}
</style>
<form id="pickbar" method="post">
<b id="pick-count">0 selected</b>
<button type="button" onclick="pickAll()">Select all</button>
<button type="submit" class="primary" formaction="{{ url_for('download_clips') }}" id="pick-dl" disabled>⬇ Download</button>
<button type="submit" class="danger" formaction="{{ url_for('delete_clips') }}" id="pick-del" disabled>🗑 Delete</button>
<button type="button" onclick="picking(false)">Cancel</button>
<input type="hidden" name="back" value="{{ request.full_path }}">
<span id="pick-inputs"></span>
</form>
<script>
const cards = () => [...document.querySelectorAll('.grid .card[data-clip]')];
function picking(on) {
  document.body.classList.toggle('picking', on);
  if (!on) cards().forEach(c => c.classList.remove('sel'));
  pickCount();
}
function pickCount() {
  const sel = cards().filter(c => c.classList.contains('sel'));
  document.getElementById('pick-count').textContent = `${sel.length} selected`;
  document.getElementById('pick-dl').disabled = document.getElementById('pick-del').disabled = !sel.length;
  document.getElementById('pick-inputs').replaceChildren(...sel.map(c => Object.assign(document.createElement('input'),
    {type: 'hidden', name: 'clip', value: c.dataset.clip})));
}
function pickAll() {
  const all = cards(), every = all.every(c => c.classList.contains('sel'));
  all.forEach(c => c.classList.toggle('sel', !every));
  pickCount();
}
document.querySelector('.grid').addEventListener('click', e => {
  const card = e.target.closest('.card[data-clip]');
  if (!card || !document.body.classList.contains('picking')) return;
  e.preventDefault();
  card.classList.toggle('sel');
  pickCount();
});
document.getElementById('pickbar').addEventListener('submit', e => {
  const sel = cards().filter(c => c.classList.contains('sel'));
  if (e.submitter && e.submitter.id === 'pick-del') {
    const stars = sel.filter(c => c.dataset.starred).length;
    if (!confirm(`Delete ${sel.length} clip${sel.length === 1 ? '' : 's'} for good?` +
                 (stars ? ` ${stars} of them ${stars === 1 ? 'is' : 'are'} starred.` : ''))) e.preventDefault();
  } else {
    setTimeout(() => picking(false), 500);   // the zip downloads; the page stays
  }
});
document.addEventListener('keydown', e => { if (e.key === 'Escape') picking(false); });
</script>
{% endif %}
{% endblock %}""",

    "clip.html": """{% extends "base.html" %}
{% block title %}{{ c.day }} {{ c.time }}{% endblock %}
{% block body %}
{% if not c.video %}<meta http-equiv="refresh" content="5">{% endif %}
<div class="row"><a href="{{ url_for('index', day=c.day) }}">← {{ c.day }}</a>
<span style="margin-left:auto"></span>
{% if older %}<a class="pill" href="{{ url_for('clip_page', day=c.day, stem=older) }}">← Older</a>{% endif %}
{% if newer %}<a class="pill" href="{{ url_for('clip_page', day=c.day, stem=newer) }}">Newer →</a>{% endif %}</div>
<h1><form class="inline" method="post" action="{{ url_for('toggle_star', day=c.day, stem=c.stem) }}">
<button class="star" title="{{ 'Unstar' if c.starred else 'Star: never auto-delete' }}">{{ '★' if c.starred else '☆' }}</button></form>
{{ c.time }} <span class="muted">· {{ c.meta.camera or c.stem }}{% if c.duration is not none %} · {{ c.duration }}s{% endif %}</span>
{% for d in c.detected %}<span class="tag">{{ d }}{% if c.meta.labels and c.meta.labels[d] %} {{ '%.0f'|format(c.meta.labels[d] * 100) }}%{% endif %}</span>{% endfor %}</h1>

{% if c.unusual %}<p class="box warn">⚠ <b>Unusual:</b> {{ c.unusual }}</p>{% endif %}
{% if c.video %}
<video id="player" controls autoplay muted playsinline preload="metadata" {% if c.snapshot %}poster="{{ url_for('media', day=c.day, name=c.snapshot) }}"{% endif %}
 src="{{ url_for('media', day=c.day, name=c.video) }}"></video>
{% if c.visit %}{% set members = (c.visit + [{'stem': c.stem, 'camera': c.camera, 'time': c.time}])|sort(attribute='time') %}
<h2>Same visit <span class="muted">· {{ members|length }} clips on {{ members|map(attribute='camera')|unique|list|length }} cameras</span></h2>
<div class="row" style="margin-bottom:8px"><button class="primary" id="playall">▶ Play all in order</button><span class="muted" id="playing"></span></div>
<div class="grid">{% for m in members %}<a class="card" href="{{ url_for('clip_page', day=c.day, stem=m.stem) }}"{% if m.stem == c.stem %} style="border-color:var(--accent)"{% endif %}>
<img loading="lazy" src="{{ url_for('media', day=c.day, name=m.stem ~ '.jpg') }}" alt="">
<div class="meta"><span class="time">{{ m.time }}</span><span class="tag">{{ m.camera }}</span>{% if m.stem == c.stem %}<span class="muted">this clip</span>{% endif %}</div></a>{% endfor %}</div>
<script>
(() => {
  const clips = [{% for m in members %}{{ url_for('media', day=c.day, name=m.stem ~ '.mp4')|tojson }}{{ ', ' if not loop.last }}{% endfor %}];
  const cams = {{ members|map(attribute='camera')|list|tojson }};
  const player = document.getElementById('player'), label = document.getElementById('playing');
  let i = -1;
  function next() {
    i += 1;
    if (i >= clips.length) { label.textContent = ''; player.removeEventListener('ended', next); return; }
    label.textContent = `${i + 1}/${clips.length} · ${cams[i]}`;
    player.src = clips[i];
    player.play().catch(() => {});
  }
  document.getElementById('playall').onclick = () => { i = -1; player.addEventListener('ended', next); next(); player.scrollIntoView({behavior: 'smooth'}); };
})();
</script>{% endif %}
<p class="row muted"><a href="{{ url_for('media', day=c.day, name=c.video) }}" download>Download</a>
{% if c.video.endswith('.mkv') %}· MKV files may not play in the browser. Download to watch.{% endif %}</p>
{% else %}
{% if c.snapshot %}<img src="{{ url_for('media', day=c.day, name=c.snapshot) }}" style="width:100%;border-radius:10px" alt="">{% endif %}
<p class="box">Recording in progress. This page refreshes until the clip is saved.</p>
{% endif %}

{% if c.plates %}<h2>Number plates</h2>
<div class="faces">{% for p in c.plates %}<div class="face">
{% if p.crop %}<img loading="lazy" src="{{ url_for('media', day=c.day, name=p.crop) }}" alt="" style="aspect-ratio:auto">{% endif %}
<div style="margin-top:6px"><b style="font-family:ui-monospace,monospace;font-size:17px">{{ p.plate }}</b>
{% if p.name %}<span class="tag k">{{ p.name }}</span>{% else %}<span class="tag u">unknown</span>{% endif %}
<span class="muted">· {{ p.reads }} read{{ '' if p.reads == 1 else 's' }}</span></div>
<a href="{{ url_for('index', plate=p.plate) }}" class="muted">All clips with this plate</a>
{% if not p.name %}<form method="post" action="{{ url_for('add_plate') }}" class="row" style="margin-top:6px">
<input type="hidden" name="plate" value="{{ p.plate }}"><input type="hidden" name="next" value="{{ request.path }}">
<input type="text" name="name" placeholder="Name, e.g. Family car" required maxlength="40" style="flex:1"><button class="primary">Save as known</button></form>{% endif %}
</div>{% endfor %}</div>{% endif %}

<h2>People in this clip</h2>
<div class="row">
{% for k in (c.faces.known if c.faces else []) %}<span class="tag k">{{ k.name }} · auto {{ '%.2f'|format(k.score) }}</span>{% endfor %}
{% for l in c.labels %}<span class="tag k">{{ l.name }} · manual
<form class="inline" method="post" action="{{ url_for('remove_label', day=c.day, stem=c.stem, idx=loop.index0) }}"><button title="Remove tag" style="border:0;padding:0 2px;background:none;color:inherit">×</button></form></span>{% endfor %}
{% if not c.names %}<span class="muted">Nobody identified{% if c.faces is none %} yet: face matching hasn't run on this clip{% elif c.faces.error %}: analysis failed ({{ c.faces.error }}){% endif %}.</span>{% endif %}
</div>

{% set crops = (c.faces.known if c.faces else []) + (c.faces.unknown if c.faces else []) %}
{% if crops %}<h2>Faces found</h2>
<div class="faces">{% for f in crops %}<div class="face">
<img loading="lazy" src="{{ url_for('media', day=c.day, name=f.crop) }}" alt="">
<div class="muted" style="margin-top:6px">{% if f.name %}Matched <b>{{ f.name }}</b> ({{ '%.2f'|format(f.score) }}){% else %}Unknown{% if f.best_guess %} · closest {{ f.best_guess }} ({{ '%.2f'|format(f.best_guess_score) }}){% endif %}{% endif %} · seen {{ f.count }}×</div>
<form method="post" action="{{ url_for('add_label', day=c.day, stem=c.stem) }}">
<input type="hidden" name="crop" value="{{ f.crop }}">
<select name="name">{% for p in people %}<option {{ 'selected' if p == (f.name or f.best_guess) }}>{{ p }}</option>{% endfor %}</select>
<input type="text" name="new_name" placeholder="…or new person name">
<label class="muted"><input type="checkbox" name="add_to_library" value="1" checked> Add this face to their reference photos</label>
<button class="primary">This is them</button></form></div>{% endfor %}</div>{% endif %}

<h2>Tag someone manually</h2>
<form class="row" method="post" action="{{ url_for('add_label', day=c.day, stem=c.stem) }}">
{% if people %}<select name="name">{% for p in people %}<option>{{ p }}</option>{% endfor %}</select>{% endif %}
<input type="text" name="new_name" placeholder="{{ 'or new name' if people else 'Name' }}">
<button class="primary">Add tag</button></form>

<h2>Share a blurred copy</h2>
<div class="box">
<p class="muted" style="margin-top:0">Makes a copy you can send to someone (a neighbour, the police): faces and number plates pixelated,
sound removed, 1280 px wide. Takes about a minute; the copy is kept for 7 days.</p>
<form method="post" action="{{ url_for('share_clip', day=c.day, stem=c.stem) }}" id="shareform" class="row">
<select name="faces"><option value="strangers">Blur strangers (keep known people)</option><option value="all">Blur every face</option>
<option value="none">Don't blur faces</option></select>
<label><input type="checkbox" name="plates" value="1" checked> Blur number plates</label>
<button class="primary">Make the copy</button></form>
<div id="sharestatus" class="muted" style="margin-top:8px">{% if share %}{{ share.state }}{% endif %}</div>
</div>
{% if share %}<script>
(async function poll() {
  const r = await fetch('/api/share/{{ share.id }}', { cache: 'no-store' }); const s = await r.json(), el = document.getElementById('sharestatus');
  if (s.state === 'done') { el.innerHTML = '<a class="pill on" href="' + s.url + '">⬇ Download the blurred copy</a>'; return; }
  if (s.state === 'error') { el.textContent = 'Could not make the copy: ' + s.error; return; }
  el.textContent = (s.state === 'queued' ? 'Waiting for another copy to finish…' : 'Blurring… ' + Math.round(s.progress * 100) + '%');
  setTimeout(poll, 1500);
})();
</script>{% endif %}

<h2>Delete</h2>
<form method="post" action="{{ url_for('delete_clip', day=c.day, stem=c.stem) }}" onsubmit="return confirm('Delete this clip permanently?')">
<input type="hidden" name="next" value="{{ older or newer or '' }}">
<button class="danger">Delete clip</button></form>
{% endblock %}""",

    "live.html": """{% extends "base.html" %}
{% block title %}Live{% endblock %}
{% block body %}
<h1>Live <span class="muted">· {{ camera }}</span></h1>
{% if cameras|length > 1 %}<nav class="days" style="margin:8px 0">{% for c in cameras %}
<a class="pill {{ 'on' if c.name == camera }}" href="?camera={{ c.name }}">{{ '🟢' if c.online else '⚪' }} {{ c.name }}</a>{% endfor %}</nav>{% endif %}
<img id="live" src="{{ url_for('live_stream', camera=camera) }}" alt="Live view" style="width:100%;border-radius:10px;background:#000;min-height:200px">
<p id="nolive" class="box" hidden>No picture: the recorder isn't receiving the camera stream right now.
<button onclick="location.reload()">Retry</button></p>
<p class="muted">About 5 frames per second, no sound. It shows exactly what motion detection sees.</p>

<h2>Test the pipeline</h2>
{% if sent %}<p class="box">Simulated motion sent. You should get a <b>TEST motion</b> ntfy notification within a few seconds,
and the clip appears under <a href="{{ url_for('index') }}">Clips</a> about 20 seconds later.</p>{% endif %}
<form method="post" action="{{ url_for('simulate_motion') }}" class="row">
<input type="hidden" name="camera" value="{{ camera }}"><button class="primary">Simulate motion</button>
<span class="muted">Records a real clip from the camera and sends a real notification to your devices.</span></form>
<script>document.getElementById('live').addEventListener('error',function(){this.hidden=true;document.getElementById('nolive').hidden=false})</script>
{% endblock %}""",

    "people.html": """{% extends "base.html" %}
{% block title %}People{% endblock %}
{% block body %}
<h1>People <span class="muted">· reference photos for face matching</span></h1>
<p class="muted">Add 3–10 clear photos of each person's face from different angles. Changes are used for new clips within a minute.</p>
<div class="grid">{% for r in rows %}<a class="card" href="{{ url_for('person_page', name=r.name) }}">
{% if r.cover %}<img loading="lazy" src="{{ url_for('person_photo', name=r.name, file=r.cover) }}" alt="" style="aspect-ratio:1">{% else %}<div class="ph" style="aspect-ratio:1"></div>{% endif %}
<div class="meta"><span class="time">{{ r.name }}</span><span class="muted">{{ r.count }} photo{{ '' if r.count == 1 else 's' }}</span></div></a>
{% endfor %}</div>
<h2>Add a person</h2>
<form class="box" method="post" action="{{ url_for('create_person') }}" enctype="multipart/form-data" style="display:grid;gap:8px;max-width:420px">
<input type="text" name="name" placeholder="Name" required maxlength="40">
<input type="file" name="photos" accept="image/*" multiple>
<button class="primary">Add person</button></form>
{% endblock %}""",

    "person.html": """{% extends "base.html" %}
{% block title %}{{ name }}{% endblock %}
{% block body %}
<a href="{{ url_for('people_page') }}">← People</a>
<h1>{{ name }} <span class="muted">· {{ photos|length }} photo{{ '' if photos|length == 1 else 's' }}</span>
<a class="pill" href="{{ url_for('index', person=name) }}">Clips with {{ name }}</a></h1>
<div class="faces">{% for p in photos %}<div class="face">
<img loading="lazy" src="{{ url_for('person_photo', name=name, file=p.file) }}" alt="">
<div class="row" style="margin-top:6px">
{% if p.face is none %}<span class="muted">not checked yet</span>{% elif p.face %}<span class="ok">face found</span>{% else %}<span class="warn">no face found, not used</span>{% endif %}
<form class="inline" method="post" action="{{ url_for('delete_photo', name=name, file=p.file) }}" style="margin-left:auto" onsubmit="return confirm('Delete this photo?')"><button class="danger">Delete</button></form></div>
</div>{% endfor %}</div>
<h2>Add photos</h2>
<form class="row" method="post" action="{{ url_for('upload_photos', name=name) }}" enctype="multipart/form-data">
<input type="file" name="photos" accept="image/*" multiple required><button class="primary">Upload</button></form>
{% if sightings %}<h2>Recent sightings</h2><ul>{% for s in sightings %}
<li>{{ s.at }} · <a href="{{ url_for('clip_page', day=s.video.split('/')[0], stem=s.video.split('/')[-1].rsplit('.', 1)[0]) }}">{{ s.video }}</a>
<span class="muted">{{ 'manual' if s.manual else 'auto %.2f'|format(s.score) }}</span></li>{% endfor %}</ul>{% endif %}
<h2>Manage</h2>
<form class="row" method="post" action="{{ url_for('rename_person', name=name) }}">
<input type="text" name="new_name" placeholder="New name" required maxlength="40"><button>Rename</button></form>
<form method="post" action="{{ url_for('delete_person', name=name) }}" onsubmit="return confirm('Delete {{ name }} and all their reference photos?')" style="margin-top:8px">
<button class="danger">Delete person</button></form>
<p class="muted">Renaming or deleting doesn't change tags on clips that were already analysed.</p>
{% endblock %}""",

    "ha.html": """{% extends "base.html" %}
{% block title %}Home Assistant{% endblock %}
{% block body %}
<h1>Home Assistant</h1>
<p>Status:
{% if mqtt %}<span class="ok">MQTT enabled ({{ mqtt }})</span>{% else %}<span class="warn">MQTT not configured</span>{% endif %} ·
{% if webhook %}<span class="ok">webhook enabled</span>{% else %}<span class="muted">webhook not configured</span>{% endif %}</p>

<h2>1. Connect with MQTT (recommended)</h2>
<ol>
<li>In Home Assistant: <b>Settings → Add-ons → Mosquitto broker</b> → install and start. Then <b>Settings → Devices & services</b> → configure the discovered <b>MQTT</b> integration.</li>
<li>Create a Home Assistant user for camwatch (<b>Settings → People → Users</b>), e.g. <code>camwatch</code>.</li>
<li>In camwatch: <a href="{{ url_for('settings_page') }}#ha"><b>Settings → Home Assistant</b></a>: enter the Home Assistant IP as MQTT broker,
that user and its password, and save. camwatch tests the login right away and connects within a few seconds; no restart needed.</li>
<li>A device <b>camwatch {{ camera }}</b> appears under <b>Settings → Devices & services → MQTT</b> with:
<ul>
{% for l in labels %}<li><code>binary_sensor.{{ slug }}_{{ l|replace(' ', '_') }}</code>: on while a {{ l }} is in view</li>{% endfor %}
<li><code>binary_sensor.{{ slug }}_motion</code>: any pixel motion</li>
<li><code>event.{{ slug }}_detection</code>: fires on {{ labels|join(', ') }}{{ ', ' if labels }}identified, unknown_face, camera_offline/online, test. Use it as an automation trigger.</li>
<li><code>camera.{{ slug }}_last_event</code>: snapshot of the latest detection</li>
<li><code>sensor.{{ slug }}_last_identified</code>, <code>sensor.{{ slug }}_last_plate</code> and <code>sensor.{{ slug }}_last_event_time</code></li>
<li><code>switch.{{ slug }}_armed</code>: arm/disarm push alerts</li>
<li><code>binary_sensor.{{ slug }}_camera_online</code></li>
</ul></li></ol>
<p class="muted">Every event carries <code>clip_url</code> and <code>snapshot_url</code> attributes (links into this web UI). Identified events also carry <code>name</code>, <code>score</code> and <code>face_url</code>;
<code>plate</code> events carry <code>plate</code>, <code>name</code> and <code>known</code>.</p>

<h2>2. Live view on a dashboard</h2>
<p><b>Settings → Devices & services → Add integration → MJPEG IP Camera</b>:</p>
<pre>Name:            camwatch {{ camera }} live
MJPEG URL:       {{ base }}/live.mjpg
Still image URL: {{ base }}/live.jpg{% if auth %}
Username/password: your web UI login{% endif %}</pre>
<p>Example dashboard card (edit dashboard → add card → Manual):</p>
<pre><button class="copy" onclick="copyPre(this)">Copy</button>{{ dashboard }}</pre>

<h2>3. Automation examples</h2>
<p class="muted">Settings → Automations → Create → ⋮ → Edit in YAML. Replace the <code>YOUR_…</code> parts.</p>
{% for title, yaml in examples.items() %}<h3 style="font-size:15px;margin:16px 0 0">{{ title }}</h3>
<pre><button class="copy" onclick="copyPre(this)">Copy</button>{{ yaml }}</pre>{% endfor %}

<h2>Alternative: webhook (no MQTT broker)</h2>
<p>Triggers only, no entities. Create this automation, then enter <code>http://&lt;Home Assistant IP&gt;:8123/api/webhook/&lt;webhook_id&gt;</code> as webhook URL in <a href="{{ url_for('settings_page') }}#ha">Settings → Home Assistant</a>.</p>
<pre><button class="copy" onclick="copyPre(this)">Copy</button>{{ webhook_example }}</pre>

<h2>Test</h2>
<p>Go to <a href="{{ url_for('live') }}">Live</a> and press <b>Simulate motion</b>. A <code>test</code> event fires in Home Assistant (Developer tools → Events or the event entity's history).</p>
<script>function copyPre(b){const t=b.parentElement.innerText.replace(/^Copy\\n?/,'');navigator.clipboard.writeText(t).then(()=>{b.textContent='Copied';setTimeout(()=>b.textContent='Copy',1500)})}</script>
{% endblock %}""",
    "plates.html": """{% extends "base.html" %}
{% block title %}Plates{% endblock %}
{% block body %}
<h1>Number plates</h1>
<p class="muted">Plates of moving vehicles are read live. Known plates get a quiet notification with their name; unknown ones a normal alert.
Reads are matched allowing one wrong character.</p>
<h2>Known plates</h2>
{% if known %}<div class="box">{% for k in known %}<div class="row" style="margin:4px 0">
<b style="font-family:ui-monospace,monospace;min-width:110px">{{ k.plate }}</b><span>{{ k.name }}</span>
<a class="muted" href="{{ url_for('index', plate=k.plate) }}">clips</a>
<form class="inline" method="post" action="{{ url_for('delete_plate', plate=k.plate) }}" style="margin-left:auto" onsubmit="return confirm('Remove {{ k.plate }}?')"><button class="danger">Remove</button></form>
</div>{% endfor %}</div>{% else %}<p class="muted">None yet.</p>{% endif %}
<form method="post" action="{{ url_for('add_plate') }}" class="row" style="margin-top:10px">
<input type="text" name="plate" placeholder="Plate, e.g. AB12345" required maxlength="12" style="text-transform:uppercase">
<input type="text" name="name" placeholder="Name, e.g. Family car" maxlength="40"><button class="primary">Add known plate</button></form>
<h2>Seen</h2>
{% if not seen %}<p class="muted">No plates read yet.</p>{% endif %}
<div class="faces">{% for e in seen %}<div class="face">
{% if e.last.crop %}<a href="{{ url_for('clip_page', day=e.last.day, stem=e.last.stem) }}"><img loading="lazy" src="{{ url_for('media', day=e.last.day, name=e.last.crop) }}" alt="" style="aspect-ratio:auto"></a>{% endif %}
<div style="margin-top:6px"><b style="font-family:ui-monospace,monospace;font-size:17px">{{ e.plate }}</b>
{% if e.name %}<span class="tag k">{{ e.name }}</span>{% else %}<span class="tag u">unknown</span>{% endif %}</div>
<div class="muted">{{ e.count }} clip{{ '' if e.count == 1 else 's' }} · last {{ e.last.when }} · <a href="{{ url_for('index', plate=e.plate) }}">clips</a></div>
{% if not e.name %}<form method="post" action="{{ url_for('add_plate') }}" class="row" style="margin-top:6px">
<input type="hidden" name="plate" value="{{ e.plate }}"><input type="text" name="name" placeholder="Name" required maxlength="40" style="flex:1">
<button>Save as known</button></form>{% endif %}
</div>{% endfor %}</div>
{% endblock %}""",

    "report.html": """{% extends "base.html" %}
{% block title %}Week {{ monday.strftime('%V') }}{% endblock %}
{% block body %}
<div class="row"><a class="pill" href="{{ url_for('report_page', week=prev_week, label=label) }}">‹ Previous</a>
<h1 style="margin:0 8px">Week {{ monday.strftime('%V') }} <span class="muted">· {{ monday.strftime('%d %b') }} – {{ (monday + timedelta(days=6)).strftime('%d %b %Y') }}</span></h1>
{% if monday < this_monday %}<a class="pill" href="{{ url_for('report_page', week=next_week, label=label) }}">Next ›</a>{% endif %}</div>
{% if error %}<p class="box warn">The presence log isn't available: {{ error }}</p>{% else %}
<div class="grid" style="grid-template-columns:repeat(auto-fill,minmax(150px,1fr));margin-top:14px">
{% set delivered = r.packages|selectattr('kind', 'equalto', 'delivered')|list|length %}
{% set arrived = r.cars|selectattr('direction', 'equalto', 'arrived')|list|length %}
{% for value, text, extra in [(r.total, 'events', ('%+d%% vs last week'|format(r.change) if r.change is not none else '')),
   (r.people|length, 'people identified', ''), (r.unknown, 'unidentified visits', ''), (r.door_visits, 'came to the door & left', ''),
   (delivered, 'packages', ''), (arrived, 'car arrivals', '')] %}
<div class="box"><div style="font-size:28px;font-weight:700">{{ value }}</div><div class="muted">{{ text }}{% if extra %}<br>{{ extra }}{% endif %}</div></div>
{% endfor %}</div>

{% set dmax = [r.per_day|map(attribute=1)|max, 1]|max %}
<h2>Per day</h2>
<div class="box" style="display:grid;grid-template-columns:repeat(7,1fr);gap:8px;align-items:end;height:170px">
{% for d, n in r.per_day %}<a href="{{ url_for('index', day=d.isoformat()) }}" style="display:flex;flex-direction:column;align-items:center;justify-content:end;height:100%;color:var(--fg)">
<span class="muted">{{ n }}</span><span style="width:70%;background:var(--accent);border-radius:6px 6px 0 0;height:{{ (n / dmax * 110)|round|int + 2 }}px"></span>
<span>{{ d.strftime('%a') }}</span></a>{% endfor %}</div>

{% set hmax = [r.per_hour|max, 1]|max %}
<h2>Per hour {% if r.busiest_hour is not none %}<span class="muted">· busiest {{ '%02d'|format(r.busiest_hour) }}–{{ '%02d'|format((r.busiest_hour + 1) % 24) }}</span>{% endif %}</h2>
<div class="box" style="display:grid;grid-template-columns:repeat(24,1fr);gap:3px;align-items:end;height:120px">
{% for n in r.per_hour %}<div title="{{ '%02d'|format(loop.index0) }}:00 · {{ n }}" style="background:var(--accent);opacity:{{ 0.35 + 0.65 * n / hmax }};border-radius:3px 3px 0 0;height:{{ (n / hmax * 90)|round|int + 1 }}px"></div>{% endfor %}
</div><div style="display:grid;grid-template-columns:repeat(8,1fr)" class="muted">{% for h in range(0, 24, 3) %}<span>{{ '%02d'|format(h) }}</span>{% endfor %}</div>

<h2>Who came</h2>
{% if r.people %}<div class="box"><table style="width:100%;border-collapse:collapse">
<tr class="muted" style="text-align:left"><th>Person</th><th>Visits</th><th>First – last</th><th>Arrived / left</th></tr>
{% for p in r.people %}<tr style="border-top:1px solid var(--line)"><td><a href="{{ url_for('index', person=p.name) }}">{{ p.name }}</a></td><td>{{ p.n }}</td>
<td>{{ p.first.strftime('%a %H:%M') }} – {{ p.last.strftime('%a %H:%M') }}</td><td>{{ p.arrived|int }} / {{ p.lft|int }}</td></tr>{% endfor %}
</table></div>{% else %}<p class="muted">Nobody identified this week.</p>{% endif %}

{% if r.cars %}<h2>Cars</h2><div class="box">{% for c in r.cars %}
<div><a href="{{ url_for('clip_page', day=c.day, stem=c.stem) }}">{{ c.at.strftime('%a %H:%M') }}</a> · {{ c.who or 'car' }} {{ c.direction }}</div>{% endfor %}</div>{% endif %}

{% if r.packages %}<h2>Packages</h2><div class="box">{% for p in r.packages %}
<div><a href="{{ url_for('clip_page', day=p.clip.split('/')[0], stem=p.clip.split('/')[1]) }}">{{ p.at[:16].replace('T', ' ') }}</a> · {{ 'delivered' if p.kind == 'delivered' else 'picked up' }} at {{ p.zone }}</div>{% endfor %}</div>{% endif %}

{% if r.animals %}<h2>Animals</h2><p>{% for a in r.animals %}<span class="tag">{{ a.kind }} {{ a.n }}×</span> {% endfor %}</p>{% endif %}

<h2 id="heat">Where they walked</h2>
<div class="row" style="margin-bottom:8px">{% for l in ['person', 'car', 'dog', 'cat', 'bicycle'] %}
<a class="pill {{ 'on' if l == label }}" href="{{ url_for('report_page', week=monday, label=l) }}">{{ l }}</a>{% endfor %}</div>
<img src="/api/heatmap.jpg?from={{ monday }}&to={{ monday + timedelta(days=6) }}&label={{ label }}&w=1600" alt="Heatmap"
 style="width:100%;border-radius:10px;background:#000">
<p class="muted">Brighter = more time spent there, from every detection this week (foot position).</p>
{% endif %}
{% endblock %}""",

    "strangers.html": """{% extends "base.html" %}
{% block title %}Strangers{% endblock %}
{% block body %}
<h1>Recurring strangers <span class="muted">· unknown faces seen in 2+ clips, last {{ days }} days</span></h1>
<p class="muted">The same unknown face across several clips is grouped here. Name a group once: every clip gets tagged and
a few faces become reference photos, so future visits are recognised. Groups are refreshed every 10 minutes{% if updated %} (last {{ updated[11:16] }}){% endif %}.
Grouping can mix up people who look alike in poor light; check the faces before naming.</p>
{% if named %}<p class="box ok">Tagged as {{ named }}. Face matching re-checks the clips within a few minutes.</p>{% endif %}
{% if not groups %}<p class="box muted">No recurring unknown faces right now.</p>{% endif %}
{% for g in groups %}<div class="box" style="margin-bottom:12px">
<div class="row"><b>Seen in {{ g.clips }} clips on {{ g.days }} day{{ '' if g.days == 1 else 's' }}</b>
<span class="muted">{{ g.first[:16].replace('T', ' ') }} – {{ g.last[:16].replace('T', ' ') }}</span>
{% if g.probably %}<span class="tag u">probably {{ g.probably.name }}? ({{ '%.0f'|format(g.probably.score * 100) }}%)</span>{% endif %}</div>
<div class="row" style="margin:8px 0;gap:6px">{% for f in g.faces[:10] %}
<a href="{{ url_for('clip_page', day=f.day, stem=f.stem) }}" title="{{ f.start[:16].replace('T', ' ') }}">
<img loading="lazy" src="{{ url_for('media', day=f.day, name=f.crop) }}" alt="" style="width:72px;height:72px;object-fit:cover;border-radius:8px"></a>{% endfor %}
{% if g.faces|length > 10 %}<span class="muted">+{{ g.faces|length - 10 }} more</span>{% endif %}</div>
<form method="post" action="{{ url_for('name_stranger') }}" class="row">
<input type="hidden" name="id" value="{{ g.id }}">
{% if people %}<select name="name">{% for p in people %}<option {{ 'selected' if g.probably and g.probably.name == p }}>{{ p }}</option>{% endfor %}</select>{% endif %}
<input type="text" name="new_name" placeholder="{{ 'or new name' if people else 'Name' }}" maxlength="40">
<button class="primary">Name this person</button></form>
<form method="post" action="{{ url_for('hide_stranger') }}" style="margin-top:6px"><input type="hidden" name="id" value="{{ g.id }}">
<button>Hide (not one person / not interesting)</button></form>
</div>{% endfor %}
{% endblock %}""",

    "search.html": """{% extends "base.html" %}
{% block title %}Search{% endblock %}
{% block body %}
<h1>Search recordings</h1>
<form method="get" class="row" style="margin-bottom:8px">
<input type="text" name="q" value="{{ q }}" placeholder="Describe what you're looking for, e.g. white van" autofocus style="flex:1;min-width:220px">
<button class="primary">Search</button></form>
<div class="row" style="gap:6px;margin-bottom:12px">{% for e in examples %}<a class="pill" href="{{ url_for('search_page', q=e) }}">{{ e }}</a>{% endfor %}</div>
<p class="muted">Matches the picture, not names or labels, using a local image model (CLIP). {{ indexed }} recordings indexed;
new ones are added within a few minutes. Results are ordered best first; the top ones are usually the useful ones.</p>
{% if error %}<p class="box warn">Search isn't available: {{ error }}</p>{% endif %}
{% if q and not error and not results %}<p class="muted">Nothing indexed yet.</p>{% endif %}
<div class="grid">
{% for c in results %}<a class="card" href="{{ url_for('clip_page', day=c.day, stem=c.stem) }}">
{% if c.snapshot %}<img loading="lazy" src="/api/thumb/{{ c.day }}/{{ c.stem }}.jpg?w=480" alt="">{% else %}<div class="ph"></div>{% endif %}
<div class="meta"><span class="time">{{ c.day }} {{ c.time }}</span><span class="muted">#{{ loop.index }}</span></div>
<div class="meta" style="padding-top:0">{% for d in c.detected %}<span class="tag">{{ d }}</span>{% endfor %}{% for n in c.names %}<span class="tag k">{{ n }}</span>{% endfor %}</div></a>
{% endfor %}</div>
{% endblock %}""",

    "timelapse.html": """{% extends "base.html" %}
{% block title %}Timelapse{% endblock %}
{% block body %}
<h1>Timelapse <span class="muted">· the day in a minute, and every event in a few seconds</span></h1>
{% if job.running %}<meta http-equiv="refresh" content="10">{% endif %}
<div class="box row">
<span class="muted" style="flex:1">A picture is saved every {{ interval }} s ({% for c in cameras %}{{ c.name }}: {{ frames_today[c.name] }}{{ ', ' if not loop.last }}{% endfor %} so far today). Each night at {{ build_at }}
yesterday becomes a timelapse and a highlights reel (4 s of every recording with time and who). Kept for 14 days.</span>
<form method="post" action="{{ url_for('timelapse_build') }}"><button class="primary" {{ 'disabled' if job.running }}>
{{ 'Building today…' if job.running else 'Build today so far' }}</button></form></div>
{% if job.error %}<p class="box warn">The last build failed: {{ job.error }}</p>{% endif %}
{% if not items %}<p class="muted" style="margin-top:14px">Nothing built yet. The first videos appear after tonight's build, or press the button.</p>{% endif %}
{% for it in items %}<h2>{{ it.day }}{% if cameras|length > 1 %} · {{ it.camera }}{% endif %}</h2>
<div class="grid" style="grid-template-columns:repeat(auto-fill,minmax(320px,1fr))">
{% for kind, label in [('timelapse', 'The whole day'), ('highlights', 'Highlights')] %}{% if it[kind] %}
<div class="box" style="padding:10px"><div class="row" style="margin-bottom:6px"><b>{{ label }}</b>
<a class="pill" style="margin-left:auto" href="{{ url_for('timelapse_file', name=it[kind]) }}" download>⬇</a></div>
<video controls playsinline preload="metadata" src="{{ url_for('timelapse_file', name=it[kind]) }}"></video></div>
{% endif %}{% endfor %}</div>{% endfor %}
{% endblock %}""",

    "log.html": """{% extends "base.html" %}
{% block title %}Log{% endblock %}
{% block body %}
<h1>Who came and when</h1>
{% if error %}<div class="box warn">The presence database is not reachable: {{ error }}</div>{% else %}
{% if last_seen %}<h2>Last seen</h2>
<div class="box">{% for s in last_seen %}<div class="row" style="margin:4px 0">
<a href="{{ url_for('log_page', who=s.name, range='all') }}"><span class="tag k">{{ s.name }}</span></a>
<span>{{ s.last.strftime('%Y-%m-%d %H:%M') }}</span>
<span class="muted">{{ s.visits }} visit{{ '' if s.visits == 1 else 's' }}{{ ' · vehicle' if s.kind == 'vehicle' else '' }}
{% if s.last_arrived %} · arrived {{ s.last_arrived.strftime('%Y-%m-%d %H:%M') }}{% endif %}
{% if s.last_left %} · left {{ s.last_left.strftime('%Y-%m-%d %H:%M') }}{% endif %}</span>
</div>{% endfor %}</div>{% endif %}
<h2>Visits</h2>
<form method="get" class="row" style="margin-bottom:12px">
<div class="days">{% for k, label in ranges.items() %}<a class="pill {{ 'on' if k == rng }}" href="{{ url_for('log_page', range=k, kind=kind, who=who) }}">{{ label }}</a>{% endfor %}</div>
<div class="days">{% for k, label in kinds.items() %}<a class="pill {{ 'on' if k == kind }}" href="{{ url_for('log_page', range=rng, kind=k, who=who) }}">{{ label }}</a>{% endfor %}</div>
<input type="hidden" name="range" value="{{ rng }}"><input type="hidden" name="kind" value="{{ kind }}">
<select name="who" onchange="this.form.submit()"><option value="">Anyone</option>
<option value="unknown" {{ 'selected' if who == 'unknown' }}>Unknown people</option>
{% for n in names %}<option {{ 'selected' if n == who }}>{{ n }}</option>{% endfor %}</select>
</form>
{% if not days %}<p class="muted">No visits in this period.</p>{% endif %}
{% for day, visits in days %}
<h2>{{ 'Today' if day == today else day.strftime('%A %Y-%m-%d') }} <span class="muted">· {{ visits|length }} visit{{ '' if visits|length == 1 else 's' }}</span></h2>
<div class="box">{% for v in visits %}<div class="row" style="margin:6px 0;border-bottom:1px solid var(--line);padding-bottom:6px">
<b style="min-width:70px">{{ v.started_at.strftime('%H:%M:%S') }}</b>
<span class="muted" style="min-width:48px">{{ v.duration_s ~ ' s' if v.duration_s is not none else '' }}</span>
<span style="min-width:120px">{% for d in (v.direction or '').split(',') if d %}<span class="tag dir-{{ d }}">{{ {'arrived': '→ arrived', 'left': '← left', 'visited': '↺ visited'}[d] }}</span> {% endfor %}</span>
<span class="row" style="flex:1;gap:6px">{% for p in v.visitors %}
{% if p.name %}<span class="tag k" title="{{ p.source }}{{ ' ' ~ p.detail if p.detail else '' }}">{{ p.name }}{{ ' (' ~ p.detail ~ ')' if p.source == 'plate' else '' }}</span>
{% elif p.kind == 'person' %}<span class="tag u">unknown person</span>
{% else %}<span class="tag" style="color:var(--muted)">{{ p.detail or p.kind }}</span>{% endif %}
{% if p.kind == 'vehicle' and p.direction %}<span class="tag dir-{{ p.direction }}">🚗 {{ {'arrived': '→ arrived', 'left': '← left'}[p.direction] }}</span>{% endif %}
{% else %}<span class="muted">motion</span>{% endfor %}
{% if v.loitering %}<span class="tag u">loitering</span>{% endif %}
{% if v.faces_seen is none %}<span class="muted" title="Face check not done yet">face check pending</span>{% endif %}</span>
{% if v.clip_deleted %}<span class="muted">clip deleted</span>{% else %}<a href="{{ url_for('clip_page', day=v.day, stem=v.stem) }}">clip</a>{% endif %}
</div>{% endfor %}</div>
{% endfor %}
{% endif %}
{% endblock %}""",

    "settings.html": """{% extends "base.html" %}
{% block title %}Settings{% endblock %}
{% block body %}
<h1>Settings</h1>
{% if error %}<p class="box bad">{{ error }}</p>
{% elif saved == 'cameras' %}<p class="box ok">Cameras saved. Changed cameras restart within about 10 seconds (after a recording in progress is saved).</p>
{% elif saved == 'ntfy' %}<p class="box {{ 'bad' if ntfy_result and ntfy_result != 'ok' else 'ok' }}">Notification settings saved.{% if ntfy_result == 'ok' %} Test push sent - check your phone.{% elif ntfy_result %} <span class="bad">Test push failed: {{ ntfy_result }}</span>{% endif %}</p>
{% elif saved == 'offsite' %}<p class="box ok">Off-site storage settings saved.</p>
{% elif saved == 'offsite-run' %}<p class="box ok">Upload started - it runs in the background; the status below updates when it's done.</p>
{% elif saved == 'offsite-off' %}<p class="box ok">Off-site storage disconnected. Files already uploaded stay where they are.</p>
{% elif saved == 'integration' %}<p class="box ok">Saved.{% if mqtt == 'ok' %} MQTT login works - camwatch connects within 10 seconds.{% elif mqtt %} <span class="bad">MQTT test failed: {{ mqtt }}</span>{% endif %}</p>
{% elif saved %}<p class="box ok">Saved. The recorder picks it up within a few seconds.</p>{% endif %}
<style>
/* the sections in pairs, side by side on a wide screen; one below the other on a phone */
main{max-width:1320px}
.spair{display:grid;gap:0 24px;align-items:start}
@media (min-width:980px){.spair{grid-template-columns:repeat(2,minmax(0,1fr))}}
.spair > section{min-width:0}
.spair .box{max-width:none !important}
</style>
<div class="spair"><section>
<h2 id="alerts">Alerts and login</h2>
<form method="post" class="box" style="display:grid;gap:14px;max-width:560px">
<div><b>Alerts</b><p class="muted" style="margin:4px 0">Recording continues in every mode; disarmed only silences push notifications.
Home Assistant still receives every event (with <code>armed: false</code>) and has an <b>Armed</b> switch.</p>
<label><input type="radio" name="mode" value="armed" {{ 'checked' if conf.mode == 'armed' }}> Armed: always notify</label><br>
<label><input type="radio" name="mode" value="disarmed" {{ 'checked' if conf.mode == 'disarmed' }}> Disarmed: no notifications</label><br>
<label><input type="radio" name="mode" value="schedule" {{ 'checked' if conf.mode == 'schedule' }}> Schedule: armed only between
<input type="time" name="from" value="{{ start }}"> and <input type="time" name="to" value="{{ end }}"></label></div>
<div><b>Unusual activity</b><p class="muted" style="margin:4px 0">Each camera learns from the last 4 weeks of clips when people,
cars and animals normally show up (weekdays and weekends apart). A visit at a time with no such visit before - a person in the garden at 03:00 -
gets an urgent "unusual" push. Starts after 2 weeks of history.</p>
<label><input type="radio" name="unusual_alerts" value="armed" {{ 'checked' if conf.get('unusual_alerts', 'armed') == 'armed' }}> When armed</label><br>
<label><input type="radio" name="unusual_alerts" value="always" {{ 'checked' if conf.get('unusual_alerts') == 'always' }}> Always, also when disarmed</label><br>
<label><input type="radio" name="unusual_alerts" value="off" {{ 'checked' if conf.get('unusual_alerts') == 'off' }}> Off</label></div>
<div><b>Loitering</b><p class="muted" style="margin:4px 0">Extra urgent alert when a person (or other detected object) stays in view this long. 0 = off.</p>
<input type="number" name="loiter_seconds" min="0" max="3600" step="5" value="{{ conf.loiter_seconds }}"> seconds</div>
<div id="login"><b>Login</b>{% if has_password %}
<p class="muted" style="margin:4px 0">Skip the password for devices on trusted networks: your home network, and e.g. your VPN's subnet
(WireGuard, OpenVPN, Tailscale). Anyone on such a network, including guests on the same Wi-Fi, can then open camwatch.
Requests that arrive through a proxy (e.g. from the internet) always need the password.</p>
<label><input type="checkbox" name="lan_no_auth" value="1" {{ 'checked' if conf.lan_no_auth }}> No password required on trusted networks</label>
<style>
.nets{display:grid;gap:8px;margin:10px 0 6px}
.net{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.3fr) auto;gap:8px;align-items:center}
.net input{width:100%}.net input[name=net]{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:13.5px}
.net .x{min-height:38px;width:38px;padding:0;color:var(--muted)}.net .x:hover{color:#ef4444;border-color:rgba(239,68,68,.6)}
.net .note{grid-column:1/-1;font-size:12px;margin:-2px 0 2px}
@media (max-width:520px){.net{grid-template-columns:minmax(0,1fr) auto}.net input[name=net]{grid-column:1}.net input[name=net_label]{grid-column:1/-1}}
</style>
<div class="nets" id="nets">
{% for n in networks %}<div class="net"><input type="text" name="net_label" value="{{ n.label }}" placeholder="Name, e.g. Home" maxlength="40">
<input type="text" name="net" value="{{ n.net }}" placeholder="192.168.1.0/24" spellcheck="false">
<button type="button" class="x" onclick="this.parentNode.remove()" title="Remove" aria-label="Remove network">✕</button>
{% if n.here %}<span class="note ok">✓ this device is on this network</span>{% endif %}
{% if n.docker %}<span class="note warn">Overlaps Docker's internal networks (172.16.0.0/12): programs on the camwatch server itself also skip the password.</span>{% endif %}</div>
{% endfor %}</div>
<template id="net-row"><div class="net"><input type="text" name="net_label" placeholder="Name, e.g. VPN" maxlength="40">
<input type="text" name="net" placeholder="10.8.0.0/24" spellcheck="false">
<button type="button" class="x" onclick="this.parentNode.remove()" title="Remove" aria-label="Remove network">✕</button></div></template>
<div class="row"><button type="button" onclick="addNet()">+ Add network</button>
{% if suggest %}<button type="button" onclick="addNet('{{ suggest }}', 'This device')">+ Add this device's network ({{ suggest }})</button>{% endif %}</div>
<script>
function addNet(net, label) {
  const row = document.getElementById('net-row').content.firstElementChild.cloneNode(true);
  if (net) { row.querySelector('[name=net]').value = net; row.querySelector('[name=net_label]').value = label || ''; }
  document.getElementById('nets').append(row);
  row.querySelector(net ? '[name=net_label]' : '[name=net]').focus();
}
</script>
<p class="muted" style="margin:8px 0 0">This device: {{ client }} {% if on_lan %}<span class="ok">is trusted</span>{% else %}<span class="warn">is not on a trusted network</span>{% endif %}.
A VPN only works here if its traffic reaches camwatch with the VPN address (routed, not NAT/masquerade to the router's address).</p>
{% else %}<p class="muted" style="margin:4px 0">No password is set (<code>WEB_PASSWORD</code> in <code>.env</code> is empty), so no login is asked anywhere.</p>{% endif %}</div>
<div><button class="primary">Save</button></div></form>
</section><section>
<h2 id="snooze">Snooze</h2>
<p class="muted">No pushes from one camera for a while (recording and Home Assistant carry on). Pushes also have a <b>Snooze 1h</b> button.</p>
<div class="box" style="display:grid;gap:8px;max-width:560px">{% for c in cams %}
<div class="row"><b style="min-width:110px">{{ c.name }}</b>
{% if snoozed[c.name] %}<span class="warn">snoozed until {{ snoozed[c.name] }}</span>
<form class="inline" method="post" action="{{ url_for('snooze') }}"><input type="hidden" name="camera" value="{{ c.name }}"><input type="hidden" name="minutes" value="0"><button>Resume pushes</button></form>
{% else %}<span class="muted">pushes on</span>{% endif %}
<span style="margin-left:auto"></span>{% for m, t in [(60, '1 h'), (240, '4 h'), (720, '12 h')] %}
<form class="inline" method="post" action="{{ url_for('snooze') }}"><input type="hidden" name="camera" value="{{ c.name }}"><input type="hidden" name="minutes" value="{{ m }}"><button>{{ t }}</button></form>{% endfor %}</div>
{% endfor %}</div>

<h2>Retention</h2>
<p class="muted">Starred clips are never deleted automatically. Clips where someone was identified or tagged are kept longer
(<code>RETENTION_KEEP_DAYS</code>) than other clips (<code>RETENTION_DAYS</code>). When the disk runs low, untagged clips go first.
Retention periods are set in <code>/opt/camwatch/.env</code>.</p>
</section></div>

<h2 id="cameras">Cameras <span class="muted">· up to {{ slots|length }}</span></h2>
<style>
.cams{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}
@media (max-width:760px){.cams{grid-template-columns:1fr}}
.camcard{background:var(--card);border:1px solid var(--line);border-radius:18px;overflow:hidden;display:flex;flex-direction:column;transition:border-color .15s}
.camcard.live{border-color:rgba(34,197,94,.45)}
.camcard .view{position:relative;aspect-ratio:16/9;background:#0b0e12;display:grid;place-items:center;overflow:hidden}
.camcard .view img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}
.camcard .view .ph{background:none;color:var(--faint);font-size:13px;display:grid;place-items:center;gap:4px;aspect-ratio:auto;text-align:center}
.camcard .view .ph b{font-size:34px;line-height:1;color:var(--line)}
.camcard .head{display:flex;align-items:center;gap:10px;padding:12px 14px 4px}
.camcard .num{flex:none;width:28px;height:28px;border-radius:50%;display:grid;place-items:center;font-weight:750;font-size:14px;background:var(--card-hi);border:1px solid var(--line)}
.camcard .title{font-weight:700;font-size:17px;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.state{flex:none;font-size:12px;font-weight:700;padding:3px 10px;border-radius:999px;border:1px solid currentColor}
.state.on{color:var(--known);background:rgba(34,197,94,.1)}.state.wait{color:var(--unknown);background:rgba(245,158,11,.1)}
.state.off{color:var(--muted)}
.camcard .fields{display:grid;gap:10px;padding:8px 14px 4px}
.field input{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:13.5px}
.field input[name^=name_]{font-family:inherit;font-size:15px}
.camcard .foot{display:flex;align-items:center;gap:10px;padding:10px 14px 14px;margin-top:auto;flex-wrap:wrap}
.camcard .msg{font-size:12.5px;color:var(--muted);flex-basis:100%}.camcard .msg.ok{color:var(--known)}.camcard .msg.bad{color:#ef4444}
.switch{display:inline-flex;align-items:center;gap:8px;font-weight:650;font-size:14px;margin-right:auto}
.switch input{appearance:none;-webkit-appearance:none;width:42px;height:24px;border-radius:999px;background:var(--line);position:relative;cursor:pointer;transition:background .15s;margin:0}
.switch input::after{content:"";position:absolute;top:3px;left:3px;width:18px;height:18px;border-radius:50%;background:#fff;transition:transform .15s}
.switch input:checked{background:var(--known)}.switch input:checked::after{transform:translateX(18px)}
.camcard.empty{border-style:dashed;background:transparent}
.camcard.empty .view,.camcard.empty .fields,.camcard.empty .foot{display:none}
.camcard .add{display:none}
.camcard.empty .add{display:grid;place-content:center;justify-items:center;gap:6px;min-height:200px;height:100%;width:100%;border:0;background:none;border-radius:0;color:var(--muted);font-size:15px}
.camcard.empty .add b{font-size:30px;line-height:1;color:var(--accent)}
.camcard.empty .add:hover{color:var(--fg)}
.camcard.empty .head{display:none}
.savebar{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-top:12px}
</style>
<form method="post" action="{{ url_for('save_cameras') }}">
<div class="cams">
{% for c in slots %}<div class="camcard{{ ' live' if c.online }}{{ ' empty' if not c.saved and c.slot != 1 }}" data-slot="{{ c.slot }}">
<button type="button" class="add" onclick="openSlot(this, true)"><b>+</b>Add camera {{ c.slot }}<span class="muted" style="font-size:12.5px">finds the cameras on your network</span></button>
<div class="view">{% if c.online %}<img src="{{ url_for('live_still', camera=c.name, w=640) }}" alt="{{ c.name }} live">{% endif %}
<div class="ph"{% if c.online %} hidden{% endif %}><b>{{ c.slot }}</b>{% if c.enabled %}no picture yet{% elif c.saved %}switched off{% else %}new camera{% endif %}</div>
<img data-test hidden alt="Test picture"></div>
<div class="head"><span class="num">{{ c.slot }}</span>
<span class="title">{{ c.name or 'New camera' }}</span>
{% if c.online %}<span class="state on">● Online</span>{% elif c.enabled %}<span class="state wait">No picture</span>{% elif c.saved %}<span class="state off">Off</span>{% endif %}</div>
<div class="fields">
{% if c.slot == 1 %}<p class="muted" style="margin:0">The name <code>{{ c.name }}</code> comes from .env. Switch it off to remove it.
Its recordings stay. Switch it on again to bring it back.</p>
{% else %}<label class="field"><span>Name <i>lowercase, e.g. garden</i></span>
<input type="text" name="name_{{ c.slot }}" value="{{ c.name }}" placeholder="garden" maxlength="24" pattern="[a-z0-9][a-z0-9_]*" autocomplete="off"></label>{% endif %}
<label class="field"><span>Stream</span>
<input type="text" name="rtsp_{{ c.slot }}" value="{{ c.rtsp_url }}" placeholder="rtsp://user:password@192.168.1.51:554/stream1" autocomplete="off" spellcheck="false"></label>
<label class="field"><span>Detection stream <i>optional</i></span>
<input type="text" name="detect_{{ c.slot }}" value="{{ c.detect_url }}" placeholder="low-res substream, saves CPU - rtsp://…/stream2" autocomplete="off" spellcheck="false"></label></div>
<div class="foot">
<label class="switch"><input type="checkbox" name="enabled_{{ c.slot }}" value="1" {{ 'checked' if c.enabled or not c.saved }}> On</label>
<button type="button" onclick="openFinder({{ c.slot }})">🔍 Find</button>
<button type="button" onclick="testCam(this, {{ c.slot }})">📷 Test picture</button>
{% if c.enabled or (c.saved and c.slot != 1) %}<button type="button" class="danger" onclick='removeCam(this, {{ c.slot }}, {{ c.name|tojson }})'>🗑 Remove</button>{% endif %}
<span class="msg" data-msg hidden></span></div>
</div>{% endfor %}
</div>
<div class="savebar"><button class="primary">Save cameras</button>
<span class="muted">Saved passwords show as ••••••. Leave the dots as they are to keep a password.
<b>🗑 Remove</b> stops a camera. Its recordings stay. A renamed camera saves new clips under the new name.</span></div></form>
<dialog id="finder" class="finder">
<div class="fhead"><b>Find cameras</b> <span class="muted" id="f-slot"></span><button type="button" aria-label="Close" onclick="this.closest('dialog').close()">✕</button></div>
<div class="row"><input type="text" id="f-subnet" value="{{ scan_subnet }}" spellcheck="false" style="flex:1;font-family:ui-monospace,Consolas,monospace">
<button type="button" class="primary" id="f-scan" onclick="scanNet()">Scan network</button></div>
<p class="muted" id="f-status" style="margin:8px 0">Looks for cameras (ONVIF) and devices with a video (RTSP) port on this network.</p>
<div id="f-list" class="flist"></div>
<div id="f-login" hidden style="display:grid;gap:8px;margin-top:10px">
<div><b id="f-ip"></b> <span class="muted">· the camera's own login (as in its app)</span></div>
<div class="row"><input type="text" id="f-user" placeholder="User, often admin" autocomplete="off" style="flex:1"><input type="password" id="f-pass" placeholder="Password" autocomplete="new-password" style="flex:1">
<button type="button" class="primary" id="f-get" onclick="getStreams()">Get streams</button></div></div>
<div id="f-streams" hidden style="margin-top:10px"></div>
<p style="margin:12px 0 0"><a href="#" onclick="$f('finder').close(); return false" class="muted">Not listed? Enter the address yourself</a></p>
</dialog>
<style>
.finder{background:var(--card);color:var(--fg);border:1px solid var(--line);border-radius:18px;padding:16px;width:min(640px,calc(100vw - 32px));max-height:85vh;overflow:auto}
.finder::backdrop{background:rgba(0,0,0,.6)}
.fhead{display:flex;align-items:center;gap:8px;margin:0 0 10px}.fhead button{margin-left:auto;min-height:32px;width:32px;padding:0}
.flist{display:grid;gap:6px}
.flist button{display:flex;gap:10px;align-items:center;justify-content:flex-start;border-radius:12px;text-align:left;width:100%;font-weight:500;min-height:44px}
.flist button.on{border-color:var(--accent)}.flist b{font-family:ui-monospace,Consolas,monospace;font-weight:650}
.stream{display:grid;grid-template-columns:auto 1fr auto auto;gap:8px;align-items:center;padding:8px 0;border-top:1px solid var(--line);font-size:14px}
.stream code{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
</style>
<script>
let fSlot = 0, fCam = null;
const $f = id => document.getElementById(id);
function openFinder(slot) {
  fSlot = slot; $f('f-slot').textContent = `for camera ${slot}`;
  $f('f-login').hidden = $f('f-streams').hidden = true;
  $f('finder').showModal();
}
async function post(url, data) {
  const body = new FormData(); Object.entries(data).forEach(([k, v]) => body.append(k, v));
  const r = await fetch(url, {method: 'POST', body});
  const j = await r.json().catch(() => ({error: 'no answer'}));
  if (!r.ok) throw new Error(j.error || r.status);
  return j;
}
async function scanNet() {
  $f('f-scan').disabled = true; $f('f-list').innerHTML = ''; $f('f-login').hidden = $f('f-streams').hidden = true;
  $f('f-status').textContent = 'Scanning… (a few seconds)';
  try {
    const {found} = await post('{{ url_for("scan_cameras") }}', {subnet: $f('f-subnet').value});
    $f('f-status').textContent = found.length ? `${found.length} camera${found.length > 1 ? 's' : ''} found. Pick one:` : 'No cameras found in this network - check the network above, or enter the address yourself.';
    found.forEach(f => {
      const b = document.createElement('button'); b.type = 'button';
      const what = [f.maker, f.model].filter(Boolean).join(' ');
      b.innerHTML = `<span style="display:grid;gap:2px"><span>${what ? `<b style="font-family:inherit">${esc(what)}</b> · ` : ''}<b>${f.ip}</b></span>
        <span class="muted">${f.onvif_port ? 'ONVIF ✓ - only the login is needed' : 'video port only - enter the stream path yourself'}</span></span>${f.used_by ? `<span class="tag" style="margin-left:auto">already ${esc(f.used_by)}</span>` : ''}`;
      b.onclick = () => pickCam(f, b);
      $f('f-list').append(b);
    });
  } catch (e) { $f('f-status').textContent = 'Scan failed: ' + e.message; }
  $f('f-scan').disabled = false;
}
function pickCam(f, btn) {
  fCam = f;
  document.querySelectorAll('.flist button').forEach(b => b.classList.toggle('on', b === btn));
  $f('f-streams').hidden = true;
  if (!f.onvif_port) {   // no ONVIF: fill in the address, the user completes path and login
    fill(`rtsp://user:password@${f.ip}:${f.rtsp_port || 554}/`, '');
    $f('f-status').textContent = `${f.ip} doesn't answer ONVIF: its address is filled in - add the login and the stream path from the camera's manual.`;
    return;
  }
  $f('f-ip').textContent = f.ip; $f('f-login').hidden = false; $f('f-user').focus();
}
async function getStreams() {
  $f('f-get').disabled = true; $f('f-streams').hidden = false; $f('f-streams').textContent = 'Asking the camera…';
  try {
    const r = await post('{{ url_for("onvif_streams") }}', {ip: fCam.ip, port: fCam.onvif_port, user: $f('f-user').value, password: $f('f-pass').value});
    const s = r.streams;
    $f('f-streams').innerHTML = `<div class="row" style="margin-bottom:6px"><b>${r.device || fCam.ip}</b><span class="muted">· pick the main stream (recorded) and optionally a small one for detection</span></div>` +
      s.map((x, i) => `<div class="stream"><span>${x.width ? x.width + '×' + x.height : '?'}</span><code title="${x.name}">${x.name}${x.encoding ? ' · ' + x.encoding : ''}</code>
        <label><input type="radio" name="f-main" value="${i}" ${i === 0 ? 'checked' : ''}> main</label>
        <label><input type="radio" name="f-det" value="${i}" ${s.length > 1 && i === s.length - 1 ? 'checked' : ''}> detection</label></div>`).join('') +
      `<div class="row" style="margin-top:10px"><button type="button" class="primary" id="f-use">Use these streams</button><span class="muted">Then press Save cameras.</span></div>`;
    $f('f-use').onclick = () => {
      const main = s[+document.querySelector('[name=f-main]:checked').value];
      const det = document.querySelector('[name=f-det]:checked');
      fill(main.url, det && det.value !== document.querySelector('[name=f-main]:checked').value ? s[+det.value].url : '', fCam);
      $f('finder').close();
    };
  } catch (e) { $f('f-streams').textContent = e.message; }
  $f('f-get').disabled = false;
}
function fill(main, det, cam) {
  const card = document.querySelector(`.camcard[data-slot="${fSlot}"]`);
  card.classList.remove('empty');
  card.querySelector(`[name=rtsp_${fSlot}]`).value = main;
  card.querySelector(`[name=detect_${fSlot}]`).value = det;
  const name = card.querySelector(`[name=name_${fSlot}]`);
  if (name && !name.value && cam) {   // a name to start from: maker + last part of the address, e.g. dahua_85
    name.value = `${(cam.maker || 'camera').toLowerCase().replace(/[^a-z0-9]+/g, '')}_${cam.ip.split('.').pop()}`.slice(0, 24);
    name.dispatchEvent(new Event('input'));
  }
  if (cam && cam.onvif_port) testCam(card.querySelector('.foot button[onclick^=testCam]'), fSlot);
  if (name) { name.focus(); name.select(); }
}
</script>

<div class="spair"><section>
<h2 id="ntfy">Notifications</h2>
<form method="post" action="{{ url_for('save_ntfy') }}" class="box" style="display:grid;gap:10px;max-width:560px">
<p class="muted" style="margin:0">Push notifications go through <a href="https://ntfy.sh" target="_blank" rel="noopener">ntfy</a>: install the ntfy app and subscribe to the topic.
On the public ntfy.sh server anyone who knows the topic can read it, so use a long random name.{% if not nt.topic %} <span class="warn">No topic yet: no pushes are sent.</span>{% endif %}</p>
<label class="field"><span>Server</span><input type="text" name="url" value="{{ nt.url }}" placeholder="https://ntfy.sh" spellcheck="false"></label>
<label class="field"><span>Topic <i>detections</i></span><input type="text" name="topic" value="{{ nt.topic }}" placeholder="camwatch-8f3k2q9x" maxlength="64" spellcheck="false" autocomplete="off"></label>
<label class="field"><span>Status topic <i>optional · camera offline, recording stalled, backups. Empty = the topic above</i></span><input type="text" name="status_topic" value="{{ nt.status_topic }}" maxlength="64" spellcheck="false" autocomplete="off"></label>
<label class="field"><span>Link in pushes <i>the address your phone opens camwatch with. Empty: pushes have no links</i></span>
<div class="row" style="flex-wrap:nowrap"><input type="text" name="link_url" id="link-url" value="{{ link_url }}" placeholder="http://192.168.1.20:8080" spellcheck="false" style="flex:1">
<button type="button" onclick="document.getElementById('link-url').value = location.origin">Use this address</button></div></label>
<label class="field"><span>Priority of detection pushes</span><select name="priority">{% for p in priorities %}<option {{ 'selected' if p == nt.priority }}>{{ p }}</option>{% endfor %}</select></label>
<details {{ 'open' if nt.token or nt.user }}><summary class="muted" style="cursor:pointer">Login <i>(only for a protected topic or your own ntfy server)</i></summary>
<div style="display:grid;gap:10px;margin-top:8px">
<label class="field"><span>Access token</span><input type="password" name="token" value="" autocomplete="new-password" placeholder="{{ 'saved - leave empty to keep' if nt.token else 'tk_…' }}"></label>
{% if nt.token %}<label><input type="checkbox" name="clear_token" value="1"> Remove the saved token</label>{% endif %}
<div class="muted">or user name and password:</div>
<label class="field"><span>User</span><input type="text" name="user" value="{{ nt.user }}" autocomplete="off"></label>
<label class="field"><span>Password</span><input type="password" name="password" value="" autocomplete="new-password" placeholder="{{ 'saved - leave empty to keep' if nt.password else '' }}"></label>
{% if nt.password %}<label><input type="checkbox" name="clear_password" value="1"> Remove the saved password</label>{% endif %}</div></details>
<div class="row"><button class="primary">Save</button><button name="test" value="1">Save &amp; send a test push</button></div></form>

</section><section>
<h2 id="offsite">Off-site storage</h2>
<div class="box" style="display:grid;gap:12px;max-width:640px">
<p class="muted" style="margin:0">Copies of clips in the cloud or on a NAS, so the footage survives when this server is stolen or breaks.
Alarms (strangers, unusual activity) go up right away, the rest every night.</p>
{% if off_connected and off.type %}
<div class="row"><span class="state on">● Connected</span><b>{{ off_types[off.type].label }}</b><code>{{ off.path }}</code>
{% if off.encrypt %}<span class="tag k">🔒 encrypted</span>{% endif %}</div>
<div class="muted">{% if off_status.running %}Uploading now (since {{ off_status.run_started[11:16] }})…
{% elif off_status.last_ok %}Last upload {{ off_status.last_ok|replace('T', ' ') }}{% if off_status.last_counts %}: {{ off_status.last_counts.clips }} clip files, {{ off_status.last_counts.starred }} starred, {{ off_status.last_counts.timelapse }} timelapses, {{ off_status['last_counts']['db-backup'] }} backups checked{% endif %}.
{% else %}No upload yet{% if not off.enabled %} (switched off){% endif %}.{% endif %}
{% if off_queue %} · {{ off_queue }} alarm{{ 's' if off_queue > 1 }} waiting{% endif %}</div>
{% if off_status.error %}<div class="bad" style="font-size:14px">⚠ {{ off_status.error }} <span class="muted">({{ off_status.error_at|replace('T', ' ') }})</span></div>{% endif %}
<div class="row"><form class="inline" method="post" action="{{ url_for('offsite_run') }}"><button>⬆ Upload now</button></form>
<button type="button" onclick="offTest(this)">Test connection</button><span class="muted" id="off-test"></span>
<span style="margin-left:auto"></span>
<button type="button" onclick="offReconnect()">🔑 Sign in again</button>
<form class="inline" method="post" action="{{ url_for('offsite_disconnect') }}" onsubmit="return confirm('Disconnect and forget this destination{{ ' and its encryption keys - files already uploaded can then only be read with the downloaded keys' if off.encrypt }}?')"><button class="danger">Disconnect</button></form></div>
{% if off.encrypt %}<p class="muted" style="margin:0">🔑 <a href="{{ url_for('offsite_recovery') }}">Download the encryption keys</a> and keep them safe
(password manager, printed copy): without them nobody - you included - can read the uploads if this server is lost.</p>{% endif %}
<form method="post" action="{{ url_for('offsite_save') }}" style="display:grid;gap:10px;border-top:1px solid var(--line);padding-top:12px">
<label><input type="checkbox" name="enabled" value="1" {{ 'checked' if off.enabled }}> Upload</label>
<div><b>What to copy</b>
<div style="display:grid;gap:4px;margin-top:4px">
<label><input type="checkbox" name="what_starred" value="1" {{ 'checked' if off.what.starred }}> Starred clips <span class="muted">(kept forever)</span></label>
<label><input type="checkbox" name="what_people" value="1" {{ 'checked' if off.what.people }}> Clips with faces (known people and strangers)</label>
<label><input type="checkbox" name="what_all" value="1" {{ 'checked' if off.what.all }}> All clips <span class="muted">(much more data)</span></label>
<label><input type="checkbox" name="what_timelapse" value="1" {{ 'checked' if off.what.timelapse }}> Daily timelapse and highlights</label>
<label><input type="checkbox" name="what_db_backup" value="1" {{ 'checked' if off.what.db_backup }}> Presence log database backups</label></div></div>
<label><input type="checkbox" name="instant" value="1" {{ 'checked' if off.instant }}> Alarms right away: snapshot at once, the clip as soon as it's saved</label>
<label><input type="checkbox" name="encrypt" value="1" {{ 'checked' if off.encrypt }}> Encrypt before upload <span class="muted">(switching changes the folder: encrypted files go to {{ off.path }}/encrypted)</span></label>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
<label class="field"><span>Keep in the cloud <i>days, starred forever</i></span><input type="number" name="keep_days" min="1" max="3650" value="{{ off.keep_days }}"></label>
<label class="field"><span>Upload speed limit <i>MB/s, 0 = none</i></span><input type="number" name="bwlimit_mbps" min="0" max="1000" step="0.5" value="{{ off.bwlimit_mbps }}"></label></div>
<div><button class="primary">Save</button></div></form>
{% endif %}
<div id="off-connect" style="display:grid;gap:10px"{% if off_connected and off.type %} hidden{% endif %}>
<label class="field"><span>Where to</span><select id="off-type" onchange="offFields()"><option value="">Choose…</option>
{% for k, t in off_types.items() %}<option value="{{ k }}">{{ t.label }}</option>{% endfor %}</select></label>
{% for k, t in off_types.items() %}<div class="off-fields" data-type="{{ k }}" hidden style="display:grid;gap:10px">
{% for name, label, secret in t.fields %}<label class="field"><span>{{ label }}</span><input type="{{ 'password' if secret else 'text' }}" data-name="{{ name }}" autocomplete="off" spellcheck="false"></label>{% endfor %}
<label class="field"><span>{{ t.path }}</span><input type="text" data-name="path" value="camwatch" spellcheck="false"></label>
{% if k == 'iclouddrive' %}<p class="muted" style="margin:0">iCloud has no official access for servers; this uses rclone's iCloud support. You'll be asked for the
two-factor code next. Advanced Data Protection must be off for the Apple ID, and the sign-in has to be renewed about once a month
(camwatch pushes a reminder when uploads start failing).</p>{% endif %}
{% if t.oauth %}<p class="muted" style="margin:0">You'll sign in with {{ t.label }} in a new tab. Afterwards that tab tries to open an address
starting with <code>http://127.0.0.1:53682/</code> or <code>http://localhost:53682/</code> and shows an error - that's expected:
copy that whole address and paste it here.</p>{% endif %}
</div>{% endfor %}
<div class="row"><button type="button" class="primary" id="off-go" onclick="offConnect()" disabled>Connect</button><span class="muted" id="off-msg"></span></div>
<div id="off-step" hidden style="display:grid;gap:8px;border-top:1px solid var(--line);padding-top:10px"></div>
<p class="muted" style="margin:0">Uploads are encrypted by default; after connecting you can change what is copied and how long it's kept.</p></div>
</div>
<script>
const $o = id => document.getElementById(id);
function offFields() {
  const t = $o('off-type').value;
  document.querySelectorAll('.off-fields').forEach(d => d.hidden = d.dataset.type !== t);
  $o('off-go').disabled = !t; $o('off-step').hidden = true; $o('off-msg').textContent = '';
}
async function offPost(url, data) {
  const body = new FormData(); Object.entries(data).forEach(([k, v]) => body.append(k, v));
  const r = await fetch(url, {method: 'POST', body});
  return r.json().catch(() => ({step: 'error', error: 'no answer from camwatch'}));
}
function esc(s) { return String(s ?? '').replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'})[c]); }
function offShow(step) {
  const box = $o('off-step'); box.hidden = false; $o('off-msg').textContent = '';
  if (step.step === 'error') { box.innerHTML = `<div class="bad">${esc(step.error)}</div>`; return; }
  if (step.step === 'done') {
    box.innerHTML = step.test === 'ok' ? '<div class="ok">✓ Connected and tested. Reloading…</div>'
      : `<div class="warn">Connected, but the test upload failed: ${esc(step.test)}</div>`;
    setTimeout(() => location.reload(), step.test === 'ok' ? 1200 : 4000); return;
  }
  if (step.step === 'oauth') {
    box.innerHTML = `<div><b>1.</b> <a href="${esc(step.url)}" target="_blank" rel="noopener">Sign in here</a> (new tab) and allow access.</div>
      <div><b>2.</b> Paste the address the tab ends on (http://127.0.0.1:53682/?… or http://localhost:53682/?…):</div>
      <div class="row"><input type="text" id="off-paste" style="flex:1" spellcheck="false"><button type="button" class="primary" id="off-paste-go">Continue</button></div>`;
    $o('off-paste-go').onclick = async () => { $o('off-msg').textContent = 'Finishing sign-in…'; offShow(await offPost('{{ url_for("offsite_oauth") }}', {pasted: $o('off-paste').value})); };
    return;
  }
  const ex = step.examples.length ? `<select id="off-ans">${step.examples.map(e => `<option value="${esc(e.value)}" ${e.value === step.default ? 'selected' : ''}>${esc(e.help || e.value)}</option>`).join('')}</select>`
    : `<input type="${step.password ? 'password' : 'text'}" id="off-ans" value="${esc(step.default)}" autocomplete="off" style="width:100%">`;
  box.innerHTML = `${step.error ? `<div class="bad">${esc(step.error)}</div>` : ''}<div style="white-space:pre-line">${esc(step.help || step.name)}</div>
    <div class="row">${ex}<button type="button" class="primary" id="off-ans-go">Continue</button></div>`;
  $o('off-ans').focus();
  $o('off-ans-go').onclick = async () => { $o('off-msg').textContent = 'Working…'; offShow(await offPost('{{ url_for("offsite_answer") }}', {state: step.state, result: $o('off-ans').value})); };
}
async function offConnect() {
  const t = $o('off-type').value, data = {type: t};
  document.querySelectorAll(`.off-fields[data-type="${t}"] [data-name]`).forEach(i => {
    data[i.dataset.name === 'path' ? 'path' : 'f_' + i.dataset.name] = i.value; });
  $o('off-go').disabled = true; $o('off-msg').textContent = 'Connecting…';
  offShow(await offPost('{{ url_for("offsite_connect") }}', data));
  $o('off-go').disabled = false;
}
function offReconnect() {   // same destination and folder: encryption keys and options are kept
  $o('off-connect').hidden = false;
  $o('off-type').value = {{ off.type|tojson }}; offFields();
  const box = document.querySelector(`.off-fields[data-type="{{ off.type }}"]`);
  if (box) { box.querySelector('[data-name=path]').value = {{ off.path|tojson }}; (box.querySelector('input') || box).focus(); }
  $o('off-connect').scrollIntoView({behavior: 'smooth', block: 'center'});
}
async function offTest(btn) {
  btn.disabled = true; $o('off-test').textContent = 'testing…';
  const r = await (await fetch('{{ url_for("offsite_test") }}', {method: 'POST'})).json().catch(() => ({result: 'no answer'}));
  $o('off-test').textContent = r.result === 'ok' ? '✓ works' : (r.result || r.error);
  btn.disabled = false;
}
</script>

</section></div>

<div class="spair"><section>
<h2 id="ha">Home Assistant</h2>
<form method="post" action="{{ url_for('save_integration') }}" class="box" style="display:grid;gap:10px;max-width:560px">
<p class="muted" style="margin:0"><b style="color:var(--fg)">MQTT broker</b>: the Mosquitto add-on in Home Assistant; empty = off. Setup steps: <a href="{{ url_for('ha_page') }}">Home Assistant</a>.</p>
<div style="display:grid;grid-template-columns:minmax(0,1fr) 110px;gap:10px">
<label class="field"><span>Host / IP</span><input type="text" name="mqtt_host" value="{{ integ.mqtt_host }}" placeholder="192.168.1.10" spellcheck="false"></label>
<label class="field"><span>Port</span><input type="number" name="mqtt_port" value="{{ integ.mqtt_port }}" min="1" max="65535"></label></div>
<label class="field"><span>User</span><input type="text" name="mqtt_user" value="{{ integ.mqtt_user }}" autocomplete="off"></label>
<label class="field"><span>Password</span><input type="password" name="mqtt_password" value="" autocomplete="new-password" placeholder="{{ 'saved - leave empty to keep' if integ.mqtt_password else '' }}"></label>
{% if integ.mqtt_password %}<label><input type="checkbox" name="clear_password" value="1"> Remove the saved password</label>{% endif %}
<label class="field"><span>Webhook URL <i>optional, instead of or next to MQTT</i></span><input type="text" name="ha_webhook_url" value="{{ integ.ha_webhook_url }}" placeholder="http://192.168.1.10:8123/api/webhook/camwatch" spellcheck="false"></label>
<div class="row"><button class="primary">Save</button> <span class="muted">Saving tests the MQTT login.</span></div></form>
</section><section>
<h2 id="updates">Updates</h2>
<div class="box" style="display:grid;gap:10px;max-width:560px">
<div class="row"><span>This server runs <b>{{ app_version.text }}</b></span>{% if app_version.date %}<span class="muted">from {{ app_version.date }}</span>{% endif %}</div>
<div id="upd-check" class="muted">Checking GitHub for a new version…</div>
<div class="muted">Missing something? <a href="{{ url_for('requests_page') }}">💡 Request a feature</a></div>
<div id="upd-new" hidden>
<div style="margin-bottom:8px"><span class="state on">● New version</span> <b id="upd-version"></b> <span class="muted" id="upd-detail"></span></div>
<form method="post" action="{{ url_for('run_update') }}" onsubmit="return confirm('Install the new version now? camwatch stops for a few minutes. When the new version fails, the old version comes back by itself.')">
<input type="hidden" name="sha" id="upd-sha">
<button class="primary" id="upd-button" {{ 'disabled' if not upd_status.helper }}>⬆ Update now</button></form></div>
{% if not upd_status.helper %}<div class="warn" style="font-size:14px">The update helper is not installed on the server yet. Run <code>sudo ./deploy.sh</code> once.</div>{% endif %}
<div id="upd-status" class="muted" {{ 'hidden' if upd_status.state == 'idle' }}>
{% if upd_status.state == 'waiting' %}Waiting for the server to start the update…
{% elif upd_status.state == 'running' %}Updating: {{ upd_status.message }}
{% elif upd_status.state == 'done' %}<span class="ok">✓ Last update: {{ upd_status.message }} ({{ (upd_status.finished or '')|replace('T', ' ') }})</span>
{% elif upd_status.state == 'failed' %}<span class="bad">⚠ Last update failed: {{ upd_status.message }} ({{ (upd_status.finished or '')|replace('T', ' ') }})</span>
{% if upd_status.log %}<details><summary style="cursor:pointer">Log</summary><pre style="white-space:pre-wrap;font-size:12px;max-height:300px;overflow:auto">{{ upd_status.log }}</pre></details>{% endif %}{% endif %}</div>
<form method="post" action="{{ url_for('save_update') }}" style="display:grid;gap:10px">
<details {{ 'open' if not upd.token }}><summary class="muted" style="cursor:pointer">Where updates come from</summary>
<div style="display:grid;gap:10px;margin-top:8px">
<p class="muted" style="margin:0">A private repository needs an access key: a fine-grained GitHub token for this one repository.
It needs <i>Contents: Read-only</i>, and <i>Issues: Read and write</i> for <a href="{{ url_for('requests_page') }}">feature requests</a>.
<a href="{{ url_for('update_key_page') }}">How to make the key, step by step</a>.</p>
<div style="display:grid;grid-template-columns:minmax(0,1fr) 130px;gap:10px">
<label class="field"><span>GitHub repository</span><input type="text" name="repo" value="{{ upd.repo }}" placeholder="owner/name" spellcheck="false"></label>
<label class="field"><span>Folder</span><input type="text" name="folder" value="{{ upd.folder }}" spellcheck="false"></label></div>
<label class="field"><span>Branch</span><input type="text" name="branch" value="{{ upd.branch }}" spellcheck="false"></label>
<label class="field"><span>Access key</span><input type="password" name="token" value="" autocomplete="new-password" placeholder="{{ 'saved - leave empty to keep' if upd.token else 'github_pat_…' }}"></label>
{% if upd.token %}<label><input type="checkbox" name="clear_token" value="1"> Remove the saved access key</label>{% endif %}
<div class="row"><button class="primary">Save and check</button></div></div></details></form>
</div>
<script>
(async function updates() {
  const $ = id => document.getElementById(id), running = {{ 'true' if upd_status.state in ('waiting', 'running') else 'false' }};
  if (running) { $('upd-check').hidden = true; return followUpdate(); }
  try {
    const r = await (await fetch('{{ url_for("api_update") }}')).json();
    if (r.error) {
      $('upd-check').className = 'bad'; $('upd-check').textContent = '⚠ ' + r.error + '. ';
      const help = document.createElement('a');
      help.href = '{{ url_for("update_key_page") }}'; help.textContent = 'How to make the access key';
      $('upd-check').append(help);
      return;
    }
    if (!r.newer) { $('upd-check').textContent = `✓ Up to date. The newest version on GitHub is ${r.latest.version} (${r.latest.short}).`; return; }
    $('upd-check').hidden = true; $('upd-new').hidden = false;
    $('upd-version').textContent = `${r.latest.version} (${r.latest.short})`;
    $('upd-detail').textContent = `from ${r.latest.date}: ${r.latest.message}`;
    $('upd-sha').value = r.latest.sha;
  } catch (e) { $('upd-check').textContent = 'The check for a new version failed: ' + e; }
})();
// camwatch restarts during the update: keep asking until the server answers again, then show the result
async function followUpdate() {
  const box = document.getElementById('upd-status');
  box.hidden = false;
  for (;;) {
    await new Promise(ok => setTimeout(ok, 4000));
    try {
      const s = await (await fetch('{{ url_for("api_update_status") }}', {cache: 'no-store'})).json();
      if (s.state === 'done' || s.state === 'failed') { location.hash = 'updates'; location.reload(); return; }
      box.textContent = s.state === 'waiting' ? 'Waiting for the server to start the update…' : 'Updating: ' + s.message;
    } catch (e) { box.textContent = 'camwatch restarts with the new version…'; }
  }
}
</script>
</section></div>
<script>
document.querySelectorAll('.camcard input[name^=name_]').forEach(inp => inp.addEventListener('input', () => {
  inp.closest('.camcard').querySelector('.title').textContent = inp.value.trim() || 'New camera';
}));
function removeCam(btn, slot, name) {
  const msg = slot === 1
    ? `Remove camera 1 (${name})? It stops recording. Its recordings stay. Switch it on again to bring it back.`
    : `Remove camera ${slot} (${name})? It stops recording. Its recordings stay.`;
  if (!confirm(msg)) return;
  const card = btn.closest('.camcard');
  if (slot === 1) {
    card.querySelector('[name=enabled_1]').checked = false;   // camera 1 comes from .env: switched off, not erased
  } else {
    card.querySelectorAll(`[name=name_${slot}], [name=rtsp_${slot}], [name=detect_${slot}]`).forEach(i => { i.value = ''; });
  }
  btn.disabled = true;
  btn.closest('form').submit();
}
function openSlot(btn, find) {
  const card = btn.closest('.camcard');
  card.classList.remove('empty');
  if (find) { openFinder(+card.dataset.slot); scanNet(); } else card.querySelector('input[name^=name_]').focus();
}
async function testCam(btn, slot) {
  const card = btn.closest('.camcard'), msg = card.querySelector('[data-msg]'), img = card.querySelector('[data-test]');
  const body = new FormData(); body.append('slot', slot); body.append('url', card.querySelector(`[name=rtsp_${slot}]`).value);
  msg.hidden = false; msg.className = 'msg'; msg.textContent = 'Connecting to the camera…'; btn.disabled = true;
  try {
    const r = await fetch('{{ url_for("test_camera") }}', {method: 'POST', body});
    if (r.ok) {
      img.src = URL.createObjectURL(await r.blob()); img.hidden = false;
      card.querySelector('.ph').hidden = true;
      msg.className = 'msg ok'; msg.textContent = '✓ Picture received - the camera works. Press Save cameras below.';
    } else { msg.className = 'msg bad'; msg.textContent = await r.text(); }
  } catch (e) { msg.className = 'msg bad'; msg.textContent = 'Failed: ' + e; }
  btn.disabled = false;
}
</script>
{% endblock %}""",

    "update_key.html": """{% extends "base.html" %}
{% block title %}Make the update key{% endblock %}
{% block body %}
<div style="max-width:680px;line-height:1.6">
<h1>How to make the secret key for updates</h1>
<p>CamWatch wants to look at your code on GitHub. Your code is private, like a locked diary.
You make a special key. The key lets CamWatch read the code. It can never change the code.
The key also lets CamWatch send your <a href="{{ url_for('requests_page') }}">feature requests</a> to GitHub.</p>
<p class="muted">Do you have a key already? Then open it on <a href="https://github.com/settings/personal-access-tokens" target="_blank" rel="noopener">GitHub</a>,
click <b>Edit</b>, and do steps 5 and 6. The key stays the same, so CamWatch needs nothing new.</p>

<h2>Part 1: Make the key on GitHub</h2>
<ol>
<li>Open this page: <a href="https://github.com/settings/personal-access-tokens/new" target="_blank" rel="noopener">github.com/settings/personal-access-tokens/new</a>. If GitHub asks you to log in, log in.</li>
<li>Find the box <b>Token name</b>. Type <code>CamWatch updates</code>.</li>
<li>Find <b>Expiration</b>. Pick <b>Custom</b> and choose a date one year from today. The key stops working on that date. Then you make a new key.</li>
<li>Find <b>Repository access</b>. Click <b>Only select repositories</b>. Click <b>{{ upd.repo.split('/')[-1] }}</b> in the list.</li>
<li>Find <b>Permissions</b> and click <b>Add permissions</b>. Type <code>contents</code> in the search box. Tick <b>Contents</b>.
Then type <code>issues</code> and tick <b>Issues</b>. Click outside the list to close it.</li>
<li><b>Contents</b> and <b>Issues</b> now show, each with a small menu next to it.
Set <b>Contents</b> to <b>Read-only</b>: CamWatch only reads the code.
Set <b>Issues</b> to <b>Read and write</b>: CamWatch sends your feature requests there.
GitHub can add <b>Metadata</b> by itself. Leave it there.</li>
<li>Scroll to the bottom. Click the green <b>Generate token</b> button. If GitHub asks again, click <b>Generate token</b> again.</li>
<li>GitHub shows your key. It is a long line that starts with <code>github_pat_</code>. Click the small copy button next to it.
<br><span class="warn">⚠ GitHub shows the key only once. Keep this page open until you finish Part 2.</span></li>
</ol>
<p class="muted">Can't find <b>Contents</b>? Check step 4. GitHub shows the full list only after you pick a repository.</p>

<h2>Part 2: Give the key to CamWatch</h2>
<ol start="9">
<li>Open <a href="{{ url_for('settings_page') }}#updates">Settings → Updates</a>.</li>
<li>Click <b>Where updates come from</b>. A small box opens.</li>
<li>Click in the box <b>Access key</b>. Paste the key: press <b>Ctrl</b> and <b>V</b> together.</li>
<li>Click <b>Save and check</b>.</li>
</ol>

<h2>Part 3: Check that it works</h2>
<p>Look at <b>Updates</b> again. You see one of two messages:</p>
<ul>
<li><span class="ok">✓ Up to date</span>: it works. CamWatch has the newest version.</li>
<li><span class="state on">● New version</span> with an <b>Update now</b> button: it works too. Press the button when you want the new version.</li>
</ul>
<p>You see <span class="bad">GitHub refused</span>? Then something went wrong with the key. Make a new key and check steps 4, 5 and 6 carefully.</p>

<h2>Two rules for secret keys</h2>
<ol>
<li>Never show the key to anyone. Do not send it in a message or put it in a photo.</li>
<li>You can close the GitHub page now. CamWatch keeps the key safe and never shows it again.</li>
</ol>
</div>
{% endblock %}""",

    "zones.html": """{% extends "base.html" %}
{% block title %}Zones{% endblock %}
{% block body %}
<h1>Zones{% if cameras|length > 1 %} <span class="muted">· {{ camera }}</span>{% endif %}</h1>
{% if cameras|length > 1 %}<nav class="days" style="margin:8px 0">{% for c in cameras %}
<a class="pill {{ 'on' if c.name == camera }}" href="?camera={{ c.name }}">{{ '🟢' if c.online else '⚪' }} {{ c.name }}</a>{% endfor %}</nav>{% endif %}
<p class="muted"><b style="color:#dc2626">Ignore zones</b> are excluded from motion and detection (trees, the street, the timestamp).
<b style="color:#2563eb">Trigger zones</b>: if you draw any, only people/objects whose feet are inside one count, and alerts say which zone
("person at door"). Each trigger zone also becomes a sensor in Home Assistant.<br>
<b style="color:#15803d">House</b> and <b style="color:#d97706">street</b> zones only feed the <a href="{{ url_for('log_page') }}">Log</a>:
a person walking from a street zone to a house zone <i>arrived</i>, the other way round <i>left</i>.
Draw them where people's feet are when they come into view from the street, and when they reach the door.<br>
<b style="color:#7c3aed">Parking</b> zones: where the car stands when it's home (draw around its wheels). A car appearing there is
logged as <i>arrived</i>, disappearing as <i>left</i>, even inside an ignore zone.</p>
<div style="max-width:1100px">
<div class="row" style="margin-bottom:8px"><button id="heat" type="button">🔥 Show where people walk (14 days)</button>
<span class="muted">Helps to draw house/street/trigger zones where people actually go.</span></div>
<!-- the drawing layer covers the picture only: zone points are fractions of the picture -->
<div style="position:relative">
<img id="bg" src="{{ url_for('live_still', camera=camera) }}" alt="Camera view" style="width:100%;display:block;border-radius:10px;background:#000;min-height:200px">
<canvas id="cv" style="position:absolute;inset:0;width:100%;height:100%;cursor:crosshair"></canvas></div></div>
<div class="row" style="margin-top:10px">
<input type="text" id="zname" placeholder="Zone name, e.g. door" maxlength="40">
<select id="ztype"><option value="trigger">Trigger zone</option><option value="ignore">Ignore zone</option>
<option value="house">House zone (arrive/leave)</option><option value="street">Street zone (arrive/leave)</option>
<option value="parking">Parking zone (car arrive/leave)</option>
<option value="package">Package zone (doorstep: parcel left / picked up)</option></select>
<button id="start" class="primary">Draw new zone</button>
<span id="drawing" hidden class="row"><span class="muted">Click points on the picture.</span>
<button id="undo">Undo point</button><button id="finish" class="primary">Finish zone</button><button id="cancel">Cancel</button></span></div>
<h2>Zones</h2><div id="list"></div>
<div class="row" style="margin-top:12px"><button id="save" class="primary">Save zones</button><span id="status" class="muted"></span></div>
<script>
let zones = {{ zones|tojson }}, draft = null, dirty = false;
const cv = document.getElementById('cv'), bg = document.getElementById('bg'), ctx = cv.getContext('2d');
const $ = id => document.getElementById(id);
function color(t, a) { return {ignore: `rgba(220,38,38,${a})`, house: `rgba(21,128,61,${a})`, street: `rgba(217,119,6,${a})`, parking: `rgba(124,58,237,${a})`}[t] || `rgba(37,99,235,${a})`; }
function draw() {
  cv.width = cv.clientWidth; cv.height = cv.clientHeight; ctx.clearRect(0, 0, cv.width, cv.height);
  const W = cv.width, H = cv.height;
  for (const z of zones.concat(draft ? [draft] : [])) {
    if (!z.points.length) continue;
    ctx.beginPath(); z.points.forEach(([x, y], i) => i ? ctx.lineTo(x * W, y * H) : ctx.moveTo(x * W, y * H));
    if (z !== draft) ctx.closePath();
    ctx.fillStyle = color(z.type, z === draft ? .15 : .25); ctx.strokeStyle = color(z.type, .9); ctx.lineWidth = 2;
    ctx.fill(); ctx.stroke();
    z.points.forEach(([x, y]) => { ctx.beginPath(); ctx.arc(x * W, y * H, 3, 0, 7); ctx.fillStyle = color(z.type, 1); ctx.fill(); });
    const [lx, ly] = z.points[0]; ctx.font = '600 13px system-ui'; ctx.fillStyle = '#fff';
    ctx.strokeStyle = 'rgba(0,0,0,.6)'; ctx.lineWidth = 3; ctx.strokeText(z.name, lx * W + 6, ly * H + 16); ctx.fillText(z.name, lx * W + 6, ly * H + 16);
  }
}
function list() {
  $('list').innerHTML = zones.length ? '' : '<p class="muted">No zones. Detection covers the whole picture.</p>';
  zones.forEach((z, i) => {
    const row = document.createElement('div'); row.className = 'row'; row.style.margin = '4px 0';
    row.innerHTML = `<span class="tag" style="color:${color(z.type, 1)}">${z.type}</span> <b></b> <span class="muted">${z.points.length} points</span>`;
    row.querySelector('b').textContent = z.name;
    const del = document.createElement('button'); del.className = 'danger'; del.textContent = 'Delete';
    del.onclick = () => { zones.splice(i, 1); dirty = true; refresh(); }; row.appendChild(del); $('list').appendChild(row);
  });
  $('status').textContent = dirty ? 'Unsaved changes' : '';
}
function refresh() { draw(); list(); }
$('start').onclick = () => {
  const name = $('zname').value.trim(); if (!name) { $('zname').focus(); return; }
  draft = { name, type: $('ztype').value, points: [] }; $('drawing').hidden = false; $('start').hidden = true;
};
cv.onclick = e => { if (!draft) return; const r = cv.getBoundingClientRect();
  draft.points.push([(e.clientX - r.left) / r.width, (e.clientY - r.top) / r.height]); draw(); };
$('undo').onclick = () => { if (draft) { draft.points.pop(); draw(); } };
$('cancel').onclick = () => { draft = null; $('drawing').hidden = true; $('start').hidden = false; draw(); };
$('finish').onclick = () => {
  if (!draft || draft.points.length < 3) { alert('A zone needs at least 3 points'); return; }
  zones.push(draft); draft = null; dirty = true; $('drawing').hidden = true; $('start').hidden = false; $('zname').value = ''; refresh();
};
$('save').onclick = async () => {
  const r = await fetch('{{ url_for('save_zones', camera=camera) }}', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ zones }) });
  if (r.ok) { dirty = false; list(); $('status').textContent = 'Saved. Active within a few seconds.'; } else { $('status').textContent = 'Save failed'; }
};
window.addEventListener('beforeunload', e => { if (dirty) { e.preventDefault(); e.returnValue = ''; } });
$('heat').onclick = () => {
  const on = !bg.src.includes('heatmap');
  bg.src = on ? '/api/heatmap.jpg?days=14&w=1600&camera={{ camera }}' : '{{ url_for('live_still', camera=camera) }}';
  $('heat').textContent = on ? '📷 Show the camera picture' : '🔥 Show where people walk (14 days)';
};
bg.onload = refresh; window.onresize = draw; refresh();
</script>
{% endblock %}""",
}
app.jinja_loader = DictLoader(TEMPLATES)
app.jinja_env.globals["timedelta"] = dt.timedelta


if __name__ == "__main__":
    log.info("web UI on :8080%s", " (password protected)" if WEB_PASSWORD else "")
    serve(app, host="0.0.0.0", port=8080, threads=8)
