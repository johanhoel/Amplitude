#!/usr/bin/env python3
"""Home Deck editor: edit the panel files and server.py in the browser, with live preview and version history.

  http://192.168.1.52:8088/        (only from ALLOW addresses, password set on first visit)

Files it may touch (nothing else): /opt/panel-wrapper/www/<name>.html|.js|.css, server.py, homedeck/*.py and homedeck.toml.
Saving a backend file (server.py, homedeck/*.py, homedeck.toml) runs `python3 -m homedeck.check` first; a problem puts the
old file back and nothing is restarted.
Every save keeps the previous version in /var/lib/deck-editor/history/<file>/<time>.txt (last KEEP versions).
Saving server.py: syntax check -> write -> restart panel-wrapper -> the panels must answer within HEALTH_S,
otherwise the previous version is put back and the service restarted again (automatic rollback).
Drafts for the live preview go to /opt/panel-wrapper/www/.drafts/ (served by the Home Deck itself, so the
preview can call the same /api/... as the real page).
"""
import base64, datetime, difflib, glob, hashlib, hmac, http.server, json, os, re, secrets, subprocess, threading, time
import urllib.parse, urllib.request

ROOT = os.environ.get("EDITOR_ROOT", "/opt/panel-wrapper")
WWW = f"{ROOT}/www"
DRAFTS = f"{WWW}/.drafts"
STATE = os.environ.get("STATE_DIRECTORY", "/var/lib/deck-editor")
AUTH = f"{STATE}/auth.json"
HIST = f"{STATE}/history"
UI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "editor.html")
ALLOW = set(os.environ.get("EDITOR_ALLOW", "127.0.0.1,192.168.1.200").split(","))
# Devices may also be allowed by hardware (MAC) address, so a new DHCP address does not lock them out.
# The address is read from this container's ARP table (same LAN); file: one MAC per line, # comments allowed.
ALLOW_MACS_FILE = os.environ.get("EDITOR_ALLOW_MACS", "/etc/deck-editor/allowed-macs")
PORT = int(os.environ.get("EDITOR_PORT", "8088"))
KEEP = 60
HEALTH_URL = os.environ.get("EDITOR_HEALTH_URL", "http://127.0.0.1/api/status")
RESTART = os.environ.get("EDITOR_RESTART", "systemctl restart panel-wrapper").split()
HEALTH_S = 25
SESSION_S = 12 * 3600
FILE_RE = re.compile(r"^(www/[a-z0-9][a-z0-9_-]{0,40}\.(html|js|css)|server\.py|homedeck/[a-z_]{1,40}\.py|homedeck\.toml)$")
PREVIEW_DIR = f"{ROOT}/.preview"                     # backend preview: a copy of homedeck/ + settings with the unsaved edit
PREVIEW_PORT = int(os.environ.get("EDITOR_PREVIEW_PORT", "8089"))
PREVIEW_IDLE_S = 600
_pv = {"proc": None, "used": 0}
_pv_lock = threading.Lock()
HD_CHECK = [f"{ROOT}/venv/bin/python3", "-m", "homedeck.check"]   # Home Deck self-test (code + homedeck.toml) before any restart
TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{title} | Home Deck</title>
<style>
:root {{ --accent: #7c5cff; --glass: rgba(18,20,30,.55); --line: rgba(255,255,255,.1); --text: #f4f5fb; --mute: rgba(244,245,251,.58);
  --font: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", Inter, Roboto, sans-serif; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; min-height: 100vh; color: var(--text); font-family: var(--font);
  background: radial-gradient(60% 50% at 15% 10%, rgba(91,60,255,.45), transparent 70%), #06070c; padding: 24px; }}
.card {{ background: var(--glass); border: 1px solid var(--line); border-radius: var(--r-lg); padding: 18px 20px; max-width: 520px; }}
h1 {{ font-weight: 300; font-size: 44px; margin: 0 0 8px; }}
.sub {{ color: var(--mute); }}
</style>
</head>
<body>
<div class="card"><h1>{title}</h1><div class="sub" id="time">–</div></div>
<script>
// Example: the time, refreshed every second. Data from the Home Deck server: fetch('/api/status').then(r => r.json())
setInterval(() => document.getElementById('time').textContent = new Date().toLocaleTimeString(), 1000);
</script>
</body>
</html>
"""

lock = threading.Lock()
sessions = {}                 # token -> expiry
fails = {"n": 0, "until": 0}
log = lambda *a: print(time.strftime("%F %T"), *a, flush=True)


# ---------------------------------------------------------------- auth
def auth_load():
    try:
        with open(AUTH) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def pw_hash(pw, salt=None):
    salt = salt or secrets.token_bytes(16)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 300_000)
    return base64.b64encode(salt).decode(), base64.b64encode(h).decode()


def pw_check(pw):
    a = auth_load()
    if not a:
        return False
    _, h = pw_hash(pw, base64.b64decode(a["salt"]))
    return hmac.compare_digest(h, a["hash"])


# ---------------------------------------------------------------- files + history
def abspath(rel):
    if not FILE_RE.match(rel or ""):
        raise PermissionError("not an editable file")
    p = os.path.realpath(os.path.join(ROOT, rel))
    if not p.startswith(ROOT + "/") or os.path.islink(os.path.join(ROOT, rel)):
        raise PermissionError("outside the panel folder")
    return p


def sha(b):
    return hashlib.sha256(b).hexdigest()[:16]


def list_files():
    out = []
    for p in sorted(glob.glob(f"{WWW}/*")) + [f"{ROOT}/homedeck.toml"] + sorted(glob.glob(f"{ROOT}/homedeck/*.py")) + [f"{ROOT}/server.py"]:
        rel = os.path.relpath(p, ROOT)
        if FILE_RE.match(rel) and os.path.isfile(p):
            st = os.stat(p)
            out.append({"path": rel, "size": st.st_size, "mtime": st.st_mtime,
                        "kind": "server" if not rel.startswith("www/") else rel.rsplit(".", 1)[1],
                        "url": None if not rel.startswith("www/") else "/" + rel[4:]})
    return out


def hist_dir(rel):
    return os.path.join(HIST, rel.replace("/", "__"))


def remember(rel, content, note):
    d = hist_dir(rel)
    os.makedirs(d, exist_ok=True)
    vid = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3]
    with open(f"{d}/{vid}.txt", "wb") as f:
        f.write(content)
    with open(f"{d}/{vid}.json", "w") as f:
        json.dump({"note": note, "size": len(content)}, f)
    vers = sorted(glob.glob(f"{d}/*.txt"))
    for old in vers[:-KEEP]:
        os.remove(old)
        if os.path.exists(old[:-4] + ".json"):
            os.remove(old[:-4] + ".json")
    return vid


def history(rel):
    out = []
    for p in sorted(glob.glob(f"{hist_dir(rel)}/*.txt"), reverse=True):
        vid = os.path.basename(p)[:-4]
        meta = {}
        try:
            meta = json.load(open(p[:-4] + ".json"))
        except Exception:
            pass
        t = datetime.datetime.strptime(vid[:15], "%Y%m%d-%H%M%S")
        out.append({"id": vid, "when": t.strftime("%Y-%m-%d %H:%M:%S"), "note": meta.get("note", ""), "size": os.path.getsize(p), "source": "editor"})
    # older hand-made backups next to the file (name.bak-YYYYMMDD-what)
    for p in sorted(glob.glob(abspath(rel) + ".bak*"), key=os.path.getmtime, reverse=True):
        out.append({"id": "bak:" + os.path.basename(p), "when": time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(p))),
                    "note": os.path.basename(p).split(".bak", 1)[1].lstrip("-") or "backup", "size": os.path.getsize(p), "source": "backup"})
    return out


def version(rel, vid):
    if vid.startswith("bak:"):
        name = vid[4:]
        if "/" in name or not name.startswith(os.path.basename(abspath(rel)) + ".bak"):
            raise PermissionError("bad backup name")
        return open(os.path.join(os.path.dirname(abspath(rel)), name), "rb").read()
    if not re.fullmatch(r"\d{8}-\d{6}-\d{3}", vid):
        raise PermissionError("bad version id")
    return open(f"{hist_dir(rel)}/{vid}.txt", "rb").read()


def write_atomic(path, content):
    tmp = path + ".editor-tmp"
    with open(tmp, "wb") as f:
        f.write(content)
    st = os.stat(path) if os.path.exists(path) else None
    if st:
        os.chmod(tmp, st.st_mode & 0o777)
    os.replace(tmp, path)


def panels_ok():
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=6) as r:
            return r.status == 200
    except Exception:
        return False


def restart_panels():
    subprocess.run(RESTART, timeout=40, check=False)
    t0 = time.time()
    while time.time() - t0 < HEALTH_S:
        time.sleep(1.5)
        if panels_ok():
            return True, round(time.time() - t0, 1)
    return False, HEALTH_S


def journal_tail(n=25):
    r = subprocess.run(["journalctl", "-u", "panel-wrapper", "-n", str(n), "--no-pager", "-o", "cat"], capture_output=True, text=True, timeout=10)
    return r.stdout[-4000:]


def save(rel, content, base, note, force=False):
    path = abspath(rel)
    with lock:
        old = open(path, "rb").read() if os.path.exists(path) else b""
        if base and base != sha(old) and not force:
            return 409, {"error": "conflict", "message": "The file was changed elsewhere since you opened it.", "current_sha": sha(old)}
        backend = not rel.startswith("www/")              # server.py, homedeck/*.py, homedeck.toml: checked + restarted
        if rel.endswith(".py"):
            try:
                compile(content, rel, "exec")
            except SyntaxError as e:
                return 400, {"error": "syntax", "message": f"Line {e.lineno}: {e.msg}", "line": e.lineno, "col": e.offset}
        vid = remember(rel, old, f"before: {note}" if note else "before save") if old else None
        write_atomic(path, content)
        log(f"saved {rel} ({len(content)} bytes){' note: ' + note if note else ''}")
        res = {"ok": True, "sha": sha(content), "previous": vid}
        if backend:                                       # full Home Deck self-test first: a problem -> file put back, no restart
            chk = subprocess.run(HD_CHECK, cwd=ROOT, capture_output=True, text=True, timeout=90,
                                 env={**os.environ, "STATE_DIRECTORY": "/var/lib/panel-wrapper"})
            if chk.returncode != 0:
                write_atomic(path, old)
                out = (chk.stdout + chk.stderr).strip()
                m = re.search(r"line (\d+)", out)
                log(f"{rel} save refused by homedeck.check")
                return 400, {"error": "check", "message": out[-1500:] + "\n\nNothing was saved or restarted.",
                             "line": int(m.group(1)) if m and rel.split("/")[-1] in out else None}
        if backend:
            ok, secs = restart_panels()
            if ok:
                res.update(restarted=True, seconds=secs)
            else:
                tail = journal_tail()
                write_atomic(path, old)
                ok2, _ = restart_panels()
                log(f"{rel} save rolled back (panels did not answer); restore ok={ok2}")
                return 500, {"error": "rollback", "message": f"The panels did not answer within {HEALTH_S} s, so the previous "
                             f"version was put back{' and is running again' if ok2 else ' (still not answering: check the log)'}.",
                             "log": tail}
        return 200, res


def _pv_stop():
    import shutil
    if _pv["proc"] and _pv["proc"].poll() is None:
        _pv["proc"].terminate()
        try:
            _pv["proc"].wait(5)
        except subprocess.TimeoutExpired:
            _pv["proc"].kill()
    _pv["proc"] = None
    shutil.rmtree(PREVIEW_DIR, ignore_errors=True)


def backend_preview(rel, content):
    """Unsaved server.py / homedeck/*.py / homedeck.toml -> a copy of the Home Deck on PREVIEW_PORT (status refresh only:
    no presence, no notices; the live panels are not touched). -> (ok, problems or log text)."""
    import shutil
    with _pv_lock:
        _pv_stop()
        os.makedirs(PREVIEW_DIR)
        shutil.copytree(f"{ROOT}/homedeck", f"{PREVIEW_DIR}/homedeck", ignore=shutil.ignore_patterns("__pycache__"))
        for f in ("homedeck.toml", "server.py"):
            shutil.copy2(f"{ROOT}/{f}", f"{PREVIEW_DIR}/{f}")
        with open(os.path.join(PREVIEW_DIR, rel), "wb") as f:
            f.write(content)
        env = {**os.environ, "HOMEDECK_ROOT": PREVIEW_DIR, "HOMEDECK_CONFIG": f"{PREVIEW_DIR}/homedeck.toml",
               "STATE_DIRECTORY": "/var/lib/panel-wrapper", "HOMEDECK_READONLY": "1"}
        chk = subprocess.run([f"{ROOT}/venv/bin/python3", "-m", "homedeck.check"], cwd=PREVIEW_DIR, env=env,
                             capture_output=True, text=True, timeout=90)
        if chk.returncode != 0:
            return False, (chk.stdout + chk.stderr).strip()[-1500:]
        _pv["proc"] = subprocess.Popen([f"{ROOT}/venv/bin/python3", f"{PREVIEW_DIR}/server.py"], cwd=PREVIEW_DIR,
                                       env={**env, "HOMEDECK_PORT": str(PREVIEW_PORT), "HOMEDECK_PREVIEW": "1"},
                                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        _pv["used"] = time.time()
        t0 = time.time()
        while time.time() - t0 < 10:
            time.sleep(.4)
            if _pv["proc"].poll() is not None:
                return False, "The preview copy stopped while starting:\n" + (_pv["proc"].stdout.read() or "")[-1500:]
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{PREVIEW_PORT}/api/health", timeout=2).read()
                return True, ""
            except Exception:
                pass
        return False, "The preview copy did not answer within 10 s."


def preview_reaper():
    """Stop the backend preview copy after PREVIEW_IDLE_S without a new preview."""
    while True:
        time.sleep(30)
        with _pv_lock:
            if _pv["proc"] and time.time() - _pv["used"] > PREVIEW_IDLE_S:
                _pv_stop()
                log("backend preview stopped (idle)")


threading.Thread(target=preview_reaper, daemon=True).start()


def diff_text(a, b, name):
    return "".join(difflib.unified_diff(a.decode(errors="replace").splitlines(True), b.decode(errors="replace").splitlines(True),
                                        f"{name} (version)", f"{name} (current)", n=3))


def allowed_macs():
    try:
        with open(ALLOW_MACS_FILE) as f:
            return {l.split("#")[0].strip().lower() for l in f if l.split("#")[0].strip()}
    except FileNotFoundError:
        return set()


def mac_of(ip):
    try:
        out = subprocess.run(["ip", "-j", "neigh", "show", ip], capture_output=True, text=True, timeout=3).stdout
        for n in json.loads(out or "[]"):
            if n.get("lladdr"):
                return n["lladdr"].lower()
    except Exception:
        pass
    return ""


# ---------------------------------------------------------------- http
class H(http.server.BaseHTTPRequestHandler):
    server_version = "deck-editor"

    def send(self, code, body, ctype="application/json", headers=()):
        if not isinstance(body, (bytes, bytearray)):
            body = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def client_ok(self):
        ip = self.client_address[0]
        if ip in ALLOW:
            return True
        mac = mac_of(ip)
        if mac and mac in allowed_macs():
            return True
        log(f"refused {self.command} {self.path[:60]} from {ip} ({mac or 'MAC unknown'})")
        return False

    def token(self):
        for part in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == "deck_editor":
                return v
        return ""

    def authed(self):
        t = self.token()
        with lock:
            exp = sessions.get(t)
            if exp and exp > time.time():
                sessions[t] = time.time() + SESSION_S
                return True
        return False

    def body(self, limit=4 * 1024 * 1024):
        n = int(self.headers.get("Content-Length") or 0)
        if n > limit:
            raise ValueError("too large")
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        if not self.client_ok():
            return self.send(403, b"The editor only opens from the owner's PC.\n", "text/plain; charset=utf-8")
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        try:
            if u.path == "/":
                return self.send(200, open(UI, "rb").read(), "text/html; charset=utf-8")
            if u.path == "/api/me":
                return self.send(200, {"setup": not auth_load(), "in": self.authed()})
            if not self.authed():
                return self.send(401, {"error": "login"})
            if u.path == "/api/files":
                return self.send(200, list_files())
            rel = q.get("path", [""])[0]
            if u.path == "/api/file":
                c = open(abspath(rel), "rb").read()
                return self.send(200, {"path": rel, "content": c.decode("utf-8", errors="replace"), "sha": sha(c)})
            if u.path == "/api/history":
                return self.send(200, history(rel))
            if u.path == "/api/version":
                v = version(rel, q.get("id", [""])[0])
                cur = open(abspath(rel), "rb").read()
                return self.send(200, {"content": v.decode("utf-8", errors="replace"), "diff": diff_text(v, cur, rel)})
        except PermissionError as e:
            return self.send(403, {"error": str(e)})
        except FileNotFoundError:
            return self.send(404, {"error": "not found"})
        except Exception as e:
            log("GET error", e)
            return self.send(500, {"error": str(e)[:200]})
        self.send(404, {"error": "not found"})

    def do_POST(self):
        if not self.client_ok():
            return self.send(403, {"error": "forbidden"})
        if self.headers.get("X-Deck-Editor") != "1":          # blocks cross-site form posts
            return self.send(400, {"error": "missing header"})
        p = urllib.parse.urlparse(self.path).path
        try:
            req = self.body()
            if p == "/api/setup":
                with lock:
                    if auth_load():
                        return self.send(409, {"error": "a password is already set"})
                    pw = req.get("password") or ""
                    if len(pw) < 8:
                        return self.send(400, {"error": "Use at least 8 characters."})
                    os.makedirs(STATE, exist_ok=True)
                    salt, h = pw_hash(pw)
                    with open(AUTH, "w") as f:
                        json.dump({"salt": salt, "hash": h, "set": time.time()}, f)
                    os.chmod(AUTH, 0o600)
                log("password set")
                return self.login_ok()
            if p == "/api/login":
                if time.time() < fails["until"]:
                    return self.send(429, {"error": f"Too many attempts; try again in {int(fails['until'] - time.time())} s."})
                if pw_check(req.get("password") or ""):
                    fails["n"] = 0
                    return self.login_ok()
                fails["n"] += 1
                if fails["n"] >= 5:
                    fails.update(n=0, until=time.time() + 300)
                log(f"failed login from {self.client_address[0]}")
                time.sleep(1)
                return self.send(401, {"error": "Wrong password."})
            if p == "/api/logout":
                with lock:
                    sessions.pop(self.token(), None)
                return self.send(200, {"ok": True}, headers=[("Set-Cookie", "deck_editor=; Max-Age=0; Path=/; HttpOnly; SameSite=Strict")])
            if not self.authed():
                return self.send(401, {"error": "login"})
            if p == "/api/password":
                if not pw_check(req.get("old") or ""):
                    return self.send(401, {"error": "The current password is wrong."})
                if len(req.get("new") or "") < 8:
                    return self.send(400, {"error": "Use at least 8 characters."})
                salt, h = pw_hash(req["new"])
                with open(AUTH, "w") as f:
                    json.dump({"salt": salt, "hash": h, "set": time.time()}, f)
                return self.send(200, {"ok": True})
            if p == "/api/preview-backend":
                rel = req.get("path", "")
                abspath(rel)
                if rel.startswith("www/"):
                    return self.send(400, {"error": "only for server.py, homedeck/*.py and homedeck.toml"})
                ok, info = backend_preview(rel, (req.get("content") or "").encode())
                if not ok:
                    return self.send(400, {"error": "preview", "message": info})
                return self.send(200, {"port": PREVIEW_PORT})
            if p == "/api/draft":
                rel = req.get("path", "")
                abspath(rel)
                if rel == "server.py":
                    return self.send(400, {"error": "no preview for server.py"})
                os.makedirs(DRAFTS, exist_ok=True)
                write_atomic(os.path.join(DRAFTS, os.path.basename(rel)), (req.get("content") or "").encode())
                return self.send(200, {"url": "/.drafts/" + os.path.basename(rel)})
            if p == "/api/save":
                code, res = save(req.get("path", ""), (req.get("content") or "").encode(), req.get("sha"), (req.get("note") or "")[:120],
                                 bool(req.get("force")))
                return self.send(code, res)
            if p == "/api/new":
                name = (req.get("name") or "").strip().lower()
                rel = f"www/{name}.html"
                path = abspath(rel)
                if os.path.exists(path):
                    return self.send(409, {"error": "a page with that name exists"})
                write_atomic(path, TEMPLATE.format(title=name.capitalize()).encode())
                os.chmod(path, 0o644)
                log(f"new page {rel}")
                return self.send(200, {"path": rel})
        except PermissionError as e:
            return self.send(403, {"error": str(e)})
        except Exception as e:
            log("POST error", e)
            return self.send(500, {"error": str(e)[:200]})
        self.send(404, {"error": "not found"})

    def login_ok(self):
        t = secrets.token_urlsafe(32)
        with lock:
            now = time.time()
            for k in [k for k, v in sessions.items() if v < now]:
                sessions.pop(k, None)
            sessions[t] = now + SESSION_S
        return self.send(200, {"ok": True}, headers=[("Set-Cookie", f"deck_editor={t}; Max-Age={SESSION_S}; Path=/; HttpOnly; SameSite=Strict")])

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    os.makedirs(HIST, exist_ok=True)
    log(f"deck-editor on :{PORT}, allowed from {sorted(ALLOW)}")
    http.server.ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
