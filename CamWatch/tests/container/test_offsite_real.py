"""Off-site storage with the real rclone, in a throwaway container: fake S3 and SFTP servers on localhost."""
import datetime as dt, json, os, subprocess, sys, time
from pathlib import Path
os.environ.update(DATA_DIR="/tmp/data", RECORDINGS_DIR="/tmp/rec", NTFY_TOPIC="")
sys.path.insert(0, "/app")
import settings, offsite, logging

ok = True
def check(text, cond):
    global ok; ok &= bool(cond); print(f"{'PASS' if cond else 'FAIL'}  {text}", flush=True)

for d in ("/tmp/s3/bucket1", "/tmp/sftp", "/tmp/data", "/tmp/rec"):
    Path(d).mkdir(parents=True, exist_ok=True)
servers = [subprocess.Popen(["rclone", "serve", "s3", "/tmp/s3", "--auth-key", "AKIATESTKEY12345,secretTESTKEY1234567890abcd", "--addr", "127.0.0.1:8099"], stderr=subprocess.DEVNULL),
           subprocess.Popen(["rclone", "serve", "sftp", "/tmp/sftp", "--user", "u", "--pass", "p w", "--addr", "127.0.0.1:2022"], stderr=subprocess.DEVNULL)]
time.sleep(2)

today = dt.date.today()
def clip(day, stem, faces=False, star=False, age_days=0):
    f = Path("/tmp/rec") / day.isoformat(); f.mkdir(exist_ok=True)
    (f / f"{stem}.mp4").write_bytes(os.urandom(200_000)); (f / f"{stem}.jpg").write_bytes(b"jpg")
    (f / f"{stem}.json").write_text(json.dumps({"start": f"{day}T12:00:00"}))
    if faces: (f / f"{stem}.faces.json").write_text(json.dumps({"known": [{"name": "Alex"}], "unknown": []}))
    if star: (f / f"{stem}.star").touch()
    t = time.time() - age_days * 86400
    for p in f.glob(f"{stem}*"): os.utime(p, (t, t))
clip(today, "camera1_120000", faces=True)
clip(today, "camera1_130000")                         # nobody: not copied with "people"
clip(today - dt.timedelta(days=3), "garden_090000", star=True, age_days=3)
Path("/tmp/data/timelapse").mkdir(); (Path("/tmp/data/timelapse") / f"{today}-camera1-timelapse.mp4").write_bytes(b"t" * 1000)
Path("/tmp/data/db-backup").mkdir(); (Path("/tmp/data/db-backup") / "camwatch-x.sql.gz").write_bytes(b"d" * 1000)

# ---------- S3 + encryption ----------
step = offsite.create_remote("s3", {"provider": "Rclone", "endpoint": "http://127.0.0.1:8099", "access_key_id": "AKIATESTKEY12345", "secret_access_key": "secretTESTKEY1234567890abcd"})
check(f"S3 remote created: {step}", step == {"step": "done"} and offsite.connected())
check("rclone.conf is private", oct(offsite.CONF.stat().st_mode & 0o777) == "0o600")
opts = {**offsite.DEFAULTS, "type": "s3", "path": "bucket1/home", "enabled": True, "encrypt": True, "keep_days": 2}
settings.update(offsite=opts)
offsite.ensure_crypt("bucket1/home")
check(f"test upload: {offsite.test(opts)}", offsite.test(opts) is None)
counts = offsite.batch(offsite.options(), logging.getLogger("t"))
check(f"batch counts: {counts}", counts == {"clips": 3, "starred": 3, "timelapse": 1, "db-backup": 1})
raw = sorted(str(p.relative_to("/tmp/s3")) for p in Path("/tmp/s3").rglob("*") if p.is_file())
check(f"stored encrypted ({len(raw)} files, names unreadable): {raw[0][:60]}", raw and all(p.startswith("bucket1/home/encrypted/") for p in raw)
      and not any("camera1" in p or "timelapse" in p for p in raw))
listing = offsite.rclone("lsf", "-R", "camwatch-crypt:").split()
check(f"readable through camwatch-crypt: {sorted(x for x in listing if not x.endswith('/'))}",
      f"clips/{today}/camera1_120000.mp4" in listing and f"starred/{today - dt.timedelta(days=3)}/garden_090000.mp4" in listing
      and f"clips/{today}/camera1_130000.mp4" not in listing and "timelapse/" in listing and "db-backup/" in listing)
# a clip larger than the raw size check: content identical after decrypting
offsite.rclone("copyto", f"camwatch-crypt:clips/{today}/camera1_120000.mp4", "/tmp/back.mp4")
check("downloaded clip is byte-identical", Path("/tmp/back.mp4").read_bytes() == (Path("/tmp/rec") / today.isoformat() / "camera1_120000.mp4").read_bytes())
# recovery file alone is enough to decrypt
rec = offsite.recovery_text(offsite.options())
pw = [l.split(":", 1)[1].strip() for l in rec.splitlines() if l.strip().startswith("password  (")][0]
salt = [l.split(":", 1)[1].strip() for l in rec.splitlines() if l.strip().startswith("password2")][0]
cfg = "/tmp/fresh.conf"; open(cfg, "w").close()
run = lambda *a: subprocess.run(["rclone", "--config", cfg, *a], capture_output=True, text=True)
run("config", "create", "cloud", "s3", "provider=Rclone", "endpoint=http://127.0.0.1:8099", "access_key_id=AKIATESTKEY12345", "secret_access_key=secretTESTKEY1234567890abcd", "--non-interactive")
run("config", "create", "dec", "crypt", "remote=cloud:bucket1/home/encrypted", f"password={pw}", f"password2={salt}", "--obscure", "--non-interactive")
check("a fresh rclone with only the recovery keys can read the clips", f"camera1_120000.mp4" in run("lsf", f"dec:clips/{today}").stdout)
# second batch: nothing new is re-uploaded (same files)
before = {p: p.stat().st_mtime for p in Path("/tmp/s3").rglob("*") if p.is_file()}
offsite.batch(offsite.options(), logging.getLogger("t"))
after = {p: p.stat().st_mtime for p in Path("/tmp/s3").rglob("*") if p.is_file()}
check("second run uploads nothing again", before == after)
# retention: a clip uploaded 5 days ago goes, starred stays
clip(today - dt.timedelta(days=5), "camera1_080000", faces=True, age_days=5)
offsite.copy("clips", [f"{today - dt.timedelta(days=5)}/camera1_080000.mp4"], offsite.options())
check("old clip uploaded for the retention test", f"camera1_080000.mp4" in offsite.rclone("lsf", "-R", "camwatch-crypt:clips"))
offsite.prune(offsite.options())
listing = offsite.rclone("lsf", "-R", "camwatch-crypt:")
check("retention removed the 5-day-old clip (keep 2 days)", "camera1_080000" not in listing)
check("retention kept today's clip and the 3-day-old STARRED clip", "camera1_120000.mp4" in listing and "garden_090000.mp4" in listing)

# ---------- alarm queue ----------
offsite.queue_alarm(today.isoformat(), "camera1_140000")
f = Path("/tmp/rec") / today.isoformat()
(f / "camera1_140000.jpg").write_bytes(b"snap")
offsite.handle_queue(offsite.options(), logging.getLogger("t"))
check("alarm snapshot is up before the clip exists", "camera1_140000.jpg" in offsite.rclone("lsf", f"camwatch-crypt:clips/{today}"))
(f / "camera1_140000.mp4").write_bytes(b"v" * 5000); (f / "camera1_140000.json").write_text("{}")
offsite.handle_queue(offsite.options(), logging.getLogger("t"))
check("alarm clip follows once saved; queue empty", "camera1_140000.mp4" in offsite.rclone("lsf", f"camwatch-crypt:clips/{today}") and not list(offsite.QUEUE.glob("*")))

# ---------- unencrypted + bandwidth limit ----------
settings.update(offsite={**offsite.options(), "encrypt": False, "bwlimit_mbps": 0.5})
t0 = time.time(); offsite.copy("clips", [f"{today}/camera1_120000.mp4"], offsite.options()); took = time.time() - t0
check(f"plain copy readable at bucket1/home/clips", (Path("/tmp/s3/bucket1/home/clips") / today.isoformat() / "camera1_120000.mp4").exists())
check(f"0.5 MB/s limit: 200 KB took {took:.1f}s", took >= 0.2)

# ---------- SFTP (NAS) ----------
step = offsite.create_remote("sftp", {"host": "127.0.0.1", "port": "2022", "user": "u", "pass": "p w"})
settings.update(offsite={**offsite.options(), "type": "sftp", "path": "nas/camwatch", "encrypt": False})
check(f"SFTP: {step} test={offsite.test(offsite.options())}", step == {"step": "done"} and offsite.test(offsite.options()) is None)
settings.update(offsite={**offsite.options(), "type": "sftp", "path": "nas/camwatch", "encrypt": False})
s = offsite.create_remote("sftp", {"host": "127.0.0.1", "port": "2022", "user": "u", "pass": "wrong"})
err = offsite.test(offsite.options())
check(f"wrong NAS password -> clear error: {err}", err and ("auth" in err.lower() or "password" in err.lower() or "unable" in err.lower()))

# ---------- OAuth start: rclone gives the provider's sign-in address ----------
for kind, host in (("drive", "accounts.google.com"), ("dropbox", "www.dropbox.com"), ("onedrive", "login.microsoftonline.com")):
    try:
        url = offsite.authorizer.start(kind)
        check(f"{kind} sign-in address: {url[:70]}...", host in url and ("redirect_uri=http%3A%2F%2F127.0.0.1%3A53682" in url or "redirect_uri=http%3A%2F%2Flocalhost%3A53682" in url))
    except offsite.RcloneError as e:
        check(f"{kind} sign-in start failed: {e}", False)
try:
    offsite.authorizer.finish("http://localhost:53682/?state=x&code=fake")
    check("fake code accepted?!", False)
except offsite.RcloneError as e:
    check(f"a wrong code is refused cleanly: {str(e)[:90]}", True)
offsite.authorizer.stop()
for p in servers: p.kill()
print("ALL PASS" if ok else "SOME FAILED")
