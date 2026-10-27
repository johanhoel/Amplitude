"""Off-site storage: copies of clips, timelapses and database backups in the cloud or on a NAS, through rclone.

Settings -> Off-site storage connects one destination (remote "camwatch" in DATA_DIR/rclone.conf, mode 600 - it holds
the credentials) and chooses what is copied. With encryption on, everything goes through a crypt remote
("camwatch-crypt" over <destination>/encrypted) whose keys camwatch generates; the recovery file on the Settings page
is the only other copy of them.

Run as its own container (python offsite.py):
  * alarms: the recorder queues loud / unusual events in DATA_DIR/offsite/queue; the snapshot goes up at once,
    the clip as soon as it is saved
  * nightly (OFFSITE_BATCH_AT) and on "Upload now": everything selected, then retention (keep_days; starred forever)
Layout at the destination: clips/<day>/, starred/<day>/, timelapse/, db-backup/.
"""
import datetime as dt
import http.client
import json
import os
import re
import secrets
import subprocess
import tempfile
import threading
import time
import urllib.parse
from pathlib import Path

from common import Ntfy, env, setup_logging
import settings

DATA_DIR = Path(env("DATA_DIR", "/data"))
REC_DIR = Path(env("RECORDINGS_DIR", "/recordings"))
CONF = DATA_DIR / "rclone.conf"
STATE = DATA_DIR / "offsite"
QUEUE = STATE / "queue"
STATUS = STATE / "status.json"
RUN_NOW = STATE / "run_now"
REMOTE, CRYPT = "camwatch", "camwatch-crypt"
BATCH_AT = env("OFFSITE_BATCH_AT", "03:30")
FAIL_PUSH_HOURS = env("OFFSITE_FAIL_PUSH_HOURS", 6, float)
INSTANT_GIVE_UP = 1800          # seconds to wait for an alarm clip to be saved
VIDEO_EXT = (".mp4", ".mkv")

# Destinations offered on the Settings page: rclone type, fields (name, label, secret?), OAuth sign-in?
TYPES = {
    "b2": {"label": "Backblaze B2", "rclone": "b2", "fields": [("account", "Key ID", False), ("key", "Application key", True)],
           "path": "Bucket (and folder), e.g. my-camwatch/home"},
    "s3": {"label": "S3 (AWS, Wasabi, Cloudflare R2, MinIO ...)", "rclone": "s3",
           "fields": [("provider", "Provider (AWS, Wasabi, Cloudflare, Minio, Other)", False), ("endpoint", "Endpoint (empty for AWS)", False),
                      ("region", "Region", False), ("access_key_id", "Access key", False), ("secret_access_key", "Secret key", True)],
           "path": "Bucket (and folder)"},
    "drive": {"label": "Google Drive", "rclone": "drive", "oauth": True, "fields": [], "path": "Folder, e.g. camwatch"},
    "onedrive": {"label": "Microsoft OneDrive", "rclone": "onedrive", "oauth": True, "fields": [], "path": "Folder, e.g. camwatch"},
    "dropbox": {"label": "Dropbox", "rclone": "dropbox", "oauth": True, "fields": [], "path": "Folder, e.g. camwatch"},
    "iclouddrive": {"label": "iCloud Drive", "rclone": "iclouddrive",
                    "fields": [("apple_id", "Apple ID (e-mail)", False), ("password", "Apple ID password", True)],
                    "path": "Folder, e.g. camwatch"},
    "sftp": {"label": "NAS / server over SFTP", "rclone": "sftp",
             "fields": [("host", "Host / IP", False), ("port", "Port (22)", False), ("user", "User", False), ("pass", "Password", True)],
             "path": "Folder, e.g. /volume1/camwatch"},
    "smb": {"label": "NAS over SMB (Windows share)", "rclone": "smb",
            "fields": [("host", "Host / IP", False), ("user", "User", False), ("pass", "Password", True)],
            "path": "Share and folder, e.g. backup/camwatch"},
}
DEFAULTS = {"enabled": False, "type": "", "path": "", "encrypt": True, "instant": True, "keep_days": 30, "bwlimit_mbps": 0,
            "what": {"starred": True, "people": True, "all": False, "timelapse": True, "db_backup": True}}
OAUTH_PORT = 53682


def options(conf=None):
    saved = (conf or settings.load()).get("offsite") or {}
    out = {**DEFAULTS, **saved}
    out["what"] = {**DEFAULTS["what"], **(saved.get("what") or {})}
    return out


# ---------- rclone ----------

class RcloneError(Exception):
    pass


def rclone(*args, timeout=120, check=True, bwlimit=0):
    CONF.parent.mkdir(parents=True, exist_ok=True)
    if not CONF.exists():
        CONF.touch(mode=0o600)
    cmd = ["rclone", "--config", str(CONF), *args]
    if bwlimit:
        cmd[3:3] = ["--bwlimit", f"{bwlimit}M"]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RcloneError(f"rclone {args[0]} took longer than {timeout}s") from None
    except FileNotFoundError:
        raise RcloneError("rclone is not installed in this image") from None
    if check and out.returncode:
        raise RcloneError(_clean_error(out.stderr or out.stdout))
    return out.stdout


APPLE_CODES = {"-20101": "Apple didn't accept the Apple ID or password (use your normal Apple ID password)",
               "-20209": "this Apple ID is locked - unlock it at iforgot.apple.com",
               "-20283": "Apple asks to verify this Apple ID first - sign in at icloud.com once"}


def _clean_error(text):
    """rclone's error output -> one readable line (it can end in a usage text or a multi-line JSON block)."""
    text = text or ""
    lines = [re.sub(r"^\d{4}/\d\d/\d\d \d\d:\d\d:\d\d (ERROR|NOTICE|CRITICAL) ?:? ?", "", l).strip() for l in text.splitlines()]
    lines = [l for l in lines if l and not re.match(r"^(Usage:|Flags:|Use \"|Use '|Run '|rclone config|-|--|\{|\}|\[|\]|\")", l)]
    msg = next((re.sub(r"^(Fatal error|Error):\s*", "", l) for l in lines if re.match(r"^(Fatal error|Error):", l)),
               lines[-1] if lines else "rclone failed")
    msg = re.sub(r"\s*:\s*\{$", "", msg)
    code = re.search(r'"code"\s*:\s*"(-?\d+)"', text)
    detail = re.search(r'"message"\s*:\s*"([^"]+)"', text)
    if code and code.group(1) in APPLE_CODES:
        msg = APPLE_CODES[code.group(1)]
    elif detail and detail.group(1) not in msg:
        msg = f"{msg}: {detail.group(1)}"
    msg = msg[:300]
    if re.search(r"2fa|trust token|session.*expired|missing.*cookie", msg, re.I) and options().get("type") == "iclouddrive":
        msg += " - the iCloud sign-in has probably expired: reconnect it in Settings -> Off-site storage"
    return msg


def connected():
    return f"[{REMOTE}]" in (CONF.read_text() if CONF.exists() else "")


def target(opts=None):
    opts = opts or options()
    return f"{CRYPT}:" if opts["encrypt"] else f"{REMOTE}:{opts['path'].strip('/')}"


def dest(opts, sub):
    """<target>/<sub> - without a double slash when the target is a remote's root ("camwatch-crypt:")."""
    base = target(opts)
    return f"{base}{sub}" if base.endswith(":") else f"{base.rstrip('/')}/{sub}"


# ---------- connecting a destination (Settings page) ----------

def _config_step(output):
    """rclone config --non-interactive output -> {"step": "question", ...} or {"step": "done"}."""
    try:
        data = json.loads(output or "{}")
    except ValueError:
        return {"step": "done"}
    opt = data.get("Option")
    if not data.get("State") or not opt:
        if data.get("Error"):
            return {"step": "error", "error": data["Error"]}
        return {"step": "done"}
    return {"step": "question", "state": data["State"], "error": data.get("Error") or "",
            "name": opt.get("Name"), "help": (opt.get("Help") or "").strip(), "default": opt.get("DefaultStr") or str(opt.get("Default") or ""),
            "password": bool(opt.get("IsPassword")), "examples": [{"value": e.get("Value"), "help": e.get("Help")} for e in opt.get("Examples") or []]}


def create_remote(kind, fields, token=None):
    """Start connecting: (re)create the "camwatch" remote. Returns the first follow-up question or done."""
    t = TYPES[kind]
    params = [f"{k}={v}" for k, v in fields.items() if v not in ("", None)]
    if kind == "drive":
        params.append("scope=drive")
    if token:
        params += [f"token={token}", "config_is_local=false"]
    rclone("config", "delete", REMOTE, check=False)
    # --obscure: without it rclone stores a long base64-looking password unobscured, thinking it already is
    return _config_step(rclone("config", "create", REMOTE, t["rclone"], *params, "--obscure", "--non-interactive", timeout=120))


def answer(state, result):
    return _config_step(rclone("config", "update", REMOTE, "--continue", "--state", state, "--result", result,
                               "--non-interactive", timeout=120))


def disconnect():
    rclone("config", "delete", CRYPT, check=False)
    rclone("config", "delete", REMOTE, check=False)


def _reveal(remote, key):
    """A crypt password from rclone.conf in clear text (rclone stores it obscured, not encrypted)."""
    section = re.search(rf"^\[{re.escape(remote)}\]\n(.*?)(?=^\[|\Z)", CONF.read_text(), re.S | re.M)
    value = re.search(rf"^{key} = (.+)$", section.group(1), re.M) if section else None
    return rclone("reveal", value.group(1).strip()).strip() if value else None


def ensure_crypt(path):
    """The crypt remote over <destination>/<path>/encrypted, keeping existing keys (so old uploads stay readable)."""
    pw = _reveal(CRYPT, "password") if f"[{CRYPT}]" in CONF.read_text() else None
    salt = _reveal(CRYPT, "password2") if pw else None
    pw, salt = pw or secrets.token_urlsafe(32), salt or secrets.token_urlsafe(32)
    rclone("config", "delete", CRYPT, check=False)
    rclone("config", "create", CRYPT, "crypt", f"remote={REMOTE}:{path.strip('/')}/encrypted",
           f"password={pw}", f"password2={salt}", "--obscure", "--non-interactive")


def recovery_text(opts):
    """Everything needed to read the encrypted uploads without camwatch."""
    pw, salt = _reveal(CRYPT, "password"), _reveal(CRYPT, "password2")
    if not pw:
        return None
    return f"""camwatch off-site encryption keys - keep this file safe (password manager, printed copy).
Without these keys the encrypted uploads cannot be read by anyone, including you.

Destination: {TYPES.get(opts['type'], {}).get('label', opts['type'])}, folder {opts['path'].strip('/')}/encrypted
Created by rclone crypt (standard file name encryption).

  password  (Password):        {pw}
  password2 (Salt / Password2): {salt}

To read the files on any computer: install rclone (https://rclone.org), run `rclone config`, add the destination
as a remote (e.g. "cloud"), then add a remote of type "crypt" with remote = cloud:{opts['path'].strip('/')}/encrypted,
filename encryption "standard", directory name encryption "true", and the two passwords above.
Then e.g.: rclone copy <crypt-remote>:clips/2026-10-26 ./restored
"""


def test(opts=None):
    """Write, read and delete a small file at the destination. None when it works, else the error."""
    opts = opts or options()
    path = dest(opts, ".camwatch-test")
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write(f"camwatch connection test {dt.datetime.now().isoformat()}\n")
        rclone("copyto", f.name, path, timeout=120)
        rclone("deletefile", path, timeout=60)
        return None
    except RcloneError as exc:
        return str(exc)
    finally:
        os.unlink(f.name)


# ---------- OAuth sign-in (Google Drive, OneDrive, Dropbox) ----------

class Authorizer:
    """`rclone authorize` waits on 127.0.0.1:53682 inside this container. The browser is somewhere else, so:
    start() returns the provider's sign-in URL (read from rclone's local redirect); after signing in the browser
    lands on http://127.0.0.1:53682/?code=... which doesn't load there - the user pastes that address and
    finish() hands it to the waiting rclone, which prints the token."""

    def __init__(self):
        self.proc, self.lines, self.started = None, [], 0.0

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.kill()
        self.proc = None

    def start(self, kind):
        self.stop()
        self.lines = []
        self.proc = subprocess.Popen(["rclone", "--config", str(CONF), "authorize", TYPES[kind]["rclone"], "--auth-no-open-browser"],
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        self.started = time.time()
        threading.Thread(target=lambda p=self.proc: [self.lines.append(l.rstrip()) for l in p.stdout], daemon=True).start()
        local = None
        for _ in range(100):
            local = next((m.group(0) for l in self.lines for m in [re.search(rf"http://127\.0\.0\.1:{OAUTH_PORT}/auth\?state=\S+", l)] if m), None)
            if local:
                break
            time.sleep(0.1)
        if not local:
            self.stop()
            raise RcloneError("rclone did not start the sign-in: " + " ".join(self.lines[-3:]))
        conn = http.client.HTTPConnection("127.0.0.1", OAUTH_PORT, timeout=10)
        conn.request("GET", local[len(f"http://127.0.0.1:{OAUTH_PORT}"):])
        resp = conn.getresponse()
        url = resp.getheader("Location")
        conn.close()
        if not url:
            self.stop()
            raise RcloneError("rclone gave no sign-in address")
        return url

    def finish(self, pasted):
        if not self.proc or self.proc.poll() is not None or time.time() - self.started > 900:
            raise RcloneError("the sign-in has expired - press Connect again")
        parts = urllib.parse.urlsplit(pasted.strip())
        query = urllib.parse.parse_qs(parts.query)
        if parts.port != OAUTH_PORT or "code" not in query:
            raise RcloneError(f"paste the whole address from the browser's address bar after signing in "
                              f"(it starts with http://127.0.0.1:{OAUTH_PORT}/? or http://localhost:{OAUTH_PORT}/?)")
        conn = http.client.HTTPConnection("127.0.0.1", OAUTH_PORT, timeout=30)
        conn.request("GET", f"/?{parts.query}")
        conn.getresponse().read()
        conn.close()
        for _ in range(300):
            text = "\n".join(self.lines)
            m = re.search(r"--->\s*(\{.*?\})\s*<---", text, re.S)
            if m:
                self.stop()
                return m.group(1)
            if self.proc.poll() is not None and not m:
                break
            time.sleep(0.1)
        self.stop()
        raise RcloneError("no token from the sign-in: " + " ".join(self.lines[-3:]))


authorizer = Authorizer()


# ---------- what to copy ----------

def _clip_files(folder, stem):
    names = [f"{stem}{ext}" for ext in VIDEO_EXT if (folder / f"{stem}{ext}").exists()]
    return names + [n for n in (f"{stem}.jpg", f"{stem}.json") if (folder / n).exists()]


def _has_people(folder, stem):
    try:
        faces = json.loads((folder / f"{stem}.faces.json").read_text())
        if faces.get("known") or faces.get("unknown"):
            return True
    except (OSError, ValueError):
        pass
    return (folder / f"{stem}.labels.json").exists()


def selection(opts, today=None):
    """{"clips": [day/file...], "starred": [...], "timelapse": [...], "db-backup": [...]} - relative paths to copy."""
    what, today = opts["what"], today or dt.date.today()
    oldest = (today - dt.timedelta(days=int(opts["keep_days"]))).isoformat()
    out = {"clips": [], "starred": [], "timelapse": [], "db-backup": []}
    for folder in sorted(p for p in REC_DIR.glob("????-??-??") if p.is_dir()):
        stems = sorted({p.name[:-len(p.suffix)] for p in folder.iterdir() if p.suffix.lower() in VIDEO_EXT})
        for stem in stems:
            files = [f"{folder.name}/{n}" for n in _clip_files(folder, stem)]
            if what["starred"] and (folder / f"{stem}.star").exists():
                out["starred"] += files
            if folder.name >= oldest and (what["all"] or (what["people"] and _has_people(folder, stem))):
                out["clips"] += files
    if what["timelapse"]:
        out["timelapse"] = sorted(p.name for p in (DATA_DIR / "timelapse").glob("*.mp4"))
    if what["db_backup"]:
        out["db-backup"] = sorted(p.name for p in (DATA_DIR / "db-backup").glob("*.sql.gz"))
    return out


SOURCES = {"clips": REC_DIR, "starred": REC_DIR, "timelapse": DATA_DIR / "timelapse", "db-backup": DATA_DIR / "db-backup"}


def copy(kind, files, opts, timeout=6 * 3600):
    """rclone copy of a list of files (relative to the kind's source folder) to <target>/<kind>/."""
    if not files:
        return 0
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write("\n".join(files) + "\n")
    try:
        rclone("copy", str(SOURCES[kind]), dest(opts, kind),
               "--files-from-raw", f.name, "--no-traverse", "--transfers", "2", "--retries", "3", "--low-level-retries", "5",
               "--contimeout", "30s", "--timeout", "5m", timeout=timeout, bwlimit=opts["bwlimit_mbps"])
    finally:
        os.unlink(f.name)
    return len(files)


def prune(opts):
    """Delete what is older than keep_days at the destination (not starred/)."""
    for kind in ("clips", "timelapse", "db-backup"):
        rclone("delete", dest(opts, kind), "--min-age", f"{int(opts['keep_days'])}d", "--rmdirs", timeout=3600, check=False)


# ---------- alarms (queued by the recorder) ----------

def queue_alarm(day, stem):
    """Called by the recorder for a loud / unusual alert: upload it right away (when switched on)."""
    opts = options()
    if not (opts["enabled"] and opts["instant"] and opts["type"]):
        return
    QUEUE.mkdir(parents=True, exist_ok=True)
    path = QUEUE / f"{day}_{stem}.json"
    if not path.exists():
        path.write_text(json.dumps({"day": day, "stem": stem, "at": time.time(), "snapshot": False}))


def handle_queue(opts, log):
    """Upload what the alarms in the queue have so far. Returns how many uploads were made."""
    done = 0
    for path in sorted(QUEUE.glob("*.json")):
        try:
            job = json.loads(path.read_text())
        except (OSError, ValueError):
            path.unlink(missing_ok=True)
            continue
        folder = REC_DIR / job["day"]
        if not re.match(r"^\d{4}-\d\d-\d\d$", job["day"]) or "/" in job["stem"]:
            path.unlink(missing_ok=True)
            continue
        if not job["snapshot"] and (folder / f"{job['stem']}.jpg").exists():
            copy("clips", [f"{job['day']}/{job['stem']}.jpg"], opts, timeout=600)
            job["snapshot"] = True
            done += 1
            path.write_text(json.dumps(job))
            log.info("alarm snapshot uploaded: %s/%s", job["day"], job["stem"])
        saved = (folder / f"{job['stem']}.json").exists() and any((folder / f"{job['stem']}{e}").exists() for e in VIDEO_EXT)
        if saved:
            copy("clips", [f"{job['day']}/{n}" for n in _clip_files(folder, job["stem"])], opts, timeout=1800)
            log.info("alarm clip uploaded: %s/%s", job["day"], job["stem"])
            done += 1
            path.unlink(missing_ok=True)
        elif time.time() - job["at"] > INSTANT_GIVE_UP:
            log.warning("alarm clip %s/%s was not saved in time - left to the nightly upload", job["day"], job["stem"])
            path.unlink(missing_ok=True)
    return done


# ---------- status ----------

def status():
    try:
        return json.loads(STATUS.read_text())
    except (OSError, ValueError):
        return {}


def _set_status(**changes):
    STATE.mkdir(parents=True, exist_ok=True)
    data = {**status(), **changes}
    tmp = STATUS.with_suffix(".tmp")
    tmp.write_text(json.dumps(data))
    os.replace(tmp, STATUS)
    return data


def batch(opts, log):
    sel = selection(opts)
    counts = {k: copy(k, v, opts) for k, v in sel.items()}
    prune(opts)
    log.info("nightly upload done: %s", counts)
    return counts


def main():
    log = setup_logging("offsite")
    ntfy = Ntfy(log)
    STATE.mkdir(parents=True, exist_ok=True)
    if status().get("running"):          # a run cut short by a restart
        _set_status(running=False)
    last_batch_day = status().get("last_batch_day")
    retry_at = 0.0           # after a failure: wait before trying the batch again

    def heartbeat():         # a nightly upload can take hours: healthy = this process is alive
        while True:
            Path("/tmp/healthy").touch()
            time.sleep(30)
    threading.Thread(target=heartbeat, daemon=True).start()
    while True:
        opts = options()
        if not (opts["enabled"] and opts["type"] and connected()):
            for p in QUEUE.glob("*.json"):
                p.unlink(missing_ok=True)
            time.sleep(10)
            continue
        now = dt.datetime.now()
        worked = False
        try:
            worked = handle_queue(opts, log) > 0
            due = now.strftime("%H:%M") >= BATCH_AT and last_batch_day != now.date().isoformat() and time.time() >= retry_at
            if due or RUN_NOW.exists():
                RUN_NOW.unlink(missing_ok=True)
                _set_status(running=True, run_started=now.isoformat(timespec="seconds"))
                counts = batch(opts, log)
                last_batch_day = now.date().isoformat()
                _set_status(running=False, last_batch_day=last_batch_day, last_ok=dt.datetime.now().isoformat(timespec="seconds"),
                            last_counts=counts)
                worked = True
            if worked and status().get("failing_since"):
                if status().get("fail_pushed"):
                    ntfy.status("Off-site uploads work again.", title="camwatch: off-site storage OK", tags="white_check_mark", priority="low")
                _set_status(failing_since=None, error=None, fail_pushed=False)
        except RcloneError as exc:
            retry_at = time.time() + 900
            failing = status().get("failing_since") or time.time()
            st = _set_status(running=False, error=str(exc), error_at=now.isoformat(timespec="seconds"), failing_since=failing)
            log.warning("upload failed: %s", exc)
            if time.time() - failing >= FAIL_PUSH_HOURS * 3600 and not st.get("fail_pushed"):
                ntfy.status(f"Off-site uploads have failed for {FAIL_PUSH_HOURS:g} h: {exc}", title="camwatch: off-site storage failing")
                _set_status(fail_pushed=True)
            time.sleep(60)
        time.sleep(10)


if __name__ == "__main__":
    main()
