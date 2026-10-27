#!/usr/bin/env python3
"""camwatch-feed: read-only JSON of recent camera visits for the Home Deck panels (CT 106).

Reads the recording sidecars directly (no database, no camwatch login):
  /srv/camwatch/recordings/<day>/<stem>.json        start/end/labels/vehicles/plates
  /srv/camwatch/recordings/<day>/<stem>.faces.json  recognised people + face crops
  /srv/camwatch/recordings/<day>/<stem>.jpg         snapshot (served resized)
Only ALLOW addresses get answers.

  GET /visits?days=2&limit=60          newest first
  GET /thumb/<day>/<stem>.jpg?w=480    resized snapshot
  GET /crop/<day>/<stem>_faces/<file>  face crop
  GET /days                            every day with recordings, newest first: [{day, count}]
  GET /visits?day=YYYY-MM-DD           every visit of one day (the Cameras panel loads day by day)
  GET /video/<day>/<stem>.mp4          the recording itself, with Range support (phones seek and Safari needs it)
  GET /latest                          newest event as soon as it starts (its snapshot is written at the start;
                                       the .json only when the clip ends): {day, stem, started, ended}
"""
import ast, glob, http.server, io, json, os, re, time, urllib.parse
from PIL import Image

REC = "/srv/camwatch/recordings"
ALLOW = {"127.0.0.1", "192.168.1.52", "192.168.1.50"}
PORT = 8091
_cache = {}


def lit(v, default):
    if isinstance(v, (list, dict)): return v
    try: return ast.literal_eval(v) if isinstance(v, str) else default
    except Exception: return default


def visit(path):
    st = os.stat(path).st_mtime
    c = _cache.get(path)
    if c and c[0] == st:
        return c[1]
    m = json.load(open(path))
    day, stem = path.split("/")[-2], os.path.basename(path)[:-5]
    faces = {}
    try: faces = json.load(open(path[:-5] + ".faces.json"))
    except Exception: pass
    labels = lit(m.get("labels"), {})
    v = {"day": day, "stem": stem, "start": m.get("start"), "end": m.get("end"),
         "labels": sorted(labels, key=lambda k: -labels[k]) if isinstance(labels, dict) else labels,
         "people": [{"name": k["name"], "score": k.get("score"), "crop": k.get("crop")} for k in faces.get("known", [])],
         "unknown": len(faces.get("unknown", [])), "faces_checked": bool(faces),
         "vehicles": lit(m.get("vehicles"), []), "plates": lit(m.get("plates"), []),
         "test": str(m.get("test")) == "True", "star": os.path.exists(path[:-5] + ".star"),
         "has_jpg": os.path.exists(path[:-5] + ".jpg")}
    _cache[path] = (st, v)
    return v


def visits(days=2, limit=60):
    out = []
    for d in sorted(glob.glob(f"{REC}/20*"), reverse=True)[:days]:
        for f in sorted(glob.glob(f"{d}/*.json"), reverse=True):
            if re.search(r"\.(faces|labels|track)\.json$", f): continue
            try:
                v = visit(f)
            except Exception:
                continue
            if not v["test"]:
                out.append(v)
            if len(out) >= limit: return out
    return out


def day_visits(day):
    out = []
    for f in sorted(glob.glob(f"{REC}/{day}/*.json"), reverse=True):
        if re.search(r"\.(faces|labels|track)\.json$", f): continue
        try:
            v = visit(f)
        except Exception:
            continue
        if not v["test"]:
            out.append({**v, "has_mp4": os.path.exists(f[:-5] + ".mp4")})
    return out


def list_days():
    out = []
    for d in sorted(glob.glob(f"{REC}/20*"), reverse=True):
        n = sum(1 for f in glob.glob(f"{d}/*.json") if not re.search(r"\.(faces|labels|track)\.json$", f))
        if n:
            out.append({"day": os.path.basename(d), "count": n})
    return out


def latest():
    for d in sorted(glob.glob(f"{REC}/20*"), reverse=True)[:2]:
        jpgs = sorted(f for f in glob.glob(f"{d}/camera*.jpg") if "_faces" not in f)
        if jpgs:
            f = jpgs[-1]
            return {"day": os.path.basename(d), "stem": os.path.basename(f)[:-4], "started": os.stat(f).st_mtime,
                    "ended": os.path.exists(f[:-4] + ".json")}
    return {}


class H(http.server.BaseHTTPRequestHandler):
    def reply(self, code, body, ctype="application/json"):
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body))); self.send_header("Cache-Control", "max-age=60" if ctype == "image/jpeg" else "no-store")
        self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        if self.client_address[0] not in ALLOW:
            return self.reply(403, b'{"error":"forbidden"}')
        u = urllib.parse.urlparse(self.path); q = urllib.parse.parse_qs(u.query)
        try:
            if u.path == "/visits" and "day" not in q:
                days = min(14, int(q.get("days", ["2"])[0])); limit = min(300, int(q.get("limit", ["60"])[0]))
                return self.reply(200, json.dumps(visits(days, limit)).encode())
            if u.path == "/days":
                return self.reply(200, json.dumps(list_days()).encode())
            if u.path == "/visits" and re.fullmatch(r"\d{4}-\d\d-\d\d", q.get("day", [""])[0]):
                return self.reply(200, json.dumps(day_visits(q["day"][0])).encode())
            m = re.fullmatch(r"/video/(\d{4}-\d\d-\d\d)/(camera\w+)\.mp4", u.path)
            if m:
                return self.video(f"{REC}/{m.group(1)}/{m.group(2)}.mp4")
            if u.path == "/latest":
                return self.reply(200, json.dumps(latest()).encode())
            m = re.fullmatch(r"/thumb/(\d{4}-\d\d-\d\d)/(camera\w+)\.jpg", u.path)
            if m:
                w = max(120, min(1280, int(q.get("w", ["480"])[0])))
                im = Image.open(f"{REC}/{m.group(1)}/{m.group(2)}.jpg"); im.thumbnail((w, w))
                b = io.BytesIO(); im.convert("RGB").save(b, "JPEG", quality=78)
                return self.reply(200, b.getvalue(), "image/jpeg")
            m = re.fullmatch(r"/crop/(\d{4}-\d\d-\d\d)/(camera\w+_faces)/(\w+\.jpg)", u.path)
            if m:
                return self.reply(200, open(f"{REC}/{m.group(1)}/{m.group(2)}/{m.group(3)}", "rb").read(), "image/jpeg")
        except FileNotFoundError:
            return self.reply(404, b'{"error":"not found"}')
        except Exception as e:
            return self.reply(500, json.dumps({"error": str(e)[:100]}).encode())
        self.reply(404, b'{"error":"not found"}')

    def video(self, path):
        size = os.path.getsize(path)
        rng = re.fullmatch(r"bytes=(\d*)-(\d*)", self.headers.get("Range", "") or "")
        start, end = 0, size - 1
        if rng and (rng.group(1) or rng.group(2)):
            if rng.group(1):
                start = int(rng.group(1)); end = min(size - 1, int(rng.group(2))) if rng.group(2) else size - 1
            else:
                start = max(0, size - int(rng.group(2)))
            if start > end or start >= size:
                self.send_response(416); self.send_header("Content-Range", f"bytes */{size}"); self.send_header("Content-Length", "0"); self.end_headers(); return
        self.send_response(206 if rng else 200)
        self.send_header("Content-Type", "video/mp4"); self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1)); self.send_header("Cache-Control", "max-age=3600")
        if rng: self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        with open(path, "rb") as f:
            f.seek(start); left = end - start + 1
            while left > 0:
                chunk = f.read(min(256 * 1024, left))
                if not chunk: break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    return
                left -= len(chunk)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    http.server.ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
