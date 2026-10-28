"""Settings -> Storage: how long clips stay, and moving the recordings (folder, NFS, SMB) through the host helper."""
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

root = Path(tempfile.mkdtemp())
for d in ("recordings", "photos", "data", "live"):
    (root / d).mkdir()
REPO = Path(__file__).resolve().parents[1]
os.environ.setdefault("OBJECT_MODEL", str(REPO / "models" / "yolov8s-coco.onnx"))
os.environ.update(RECORDINGS_DIR=str(root / "recordings"), PHOTOS_DIR=str(root / "photos"), DATA_DIR=str(root / "data"),
                  LIVE_DIR=str(root / "live"), CAMERA_NAME="camera1", WEB_PASSWORD="", DB_SOCKET=str(root / "nosock"),
                  RETENTION_DAYS="21", MIN_FREE_GB="15")
sys.path.insert(0, str(REPO / "app"))
import settings  # noqa: E402
import updates  # noqa: E402
import webui  # noqa: E402

ok = True


def report(good, text):
    global ok
    ok &= bool(good)
    print(f"{'PASS' if good else 'FAIL'} {text}")


c = webui.app.test_client()

# ---------- keep clips ----------
s = settings.storage()
report(s == {"retention_days": 21, "keep_days": 90, "min_free_gb": 15.0}, f"before saving, the values come from .env: {s}")
page = c.get("/settings").get_data(as_text=True)
report('id="storage"' in page and "Keep clips" in page and 'value="21"' in page and "GB free" in page,
       "Settings shows Keep clips with the disk use")
c.post("/settings/storage", data={"retention_days": "7", "keep_days": "60", "min_free_gb": "40"})
report(settings.storage() == {"retention_days": 7, "keep_days": 60, "min_free_gb": 40.0}, "Save stores how long clips stay")
r = c.post("/settings/storage", data={"retention_days": "-1", "keep_days": "60", "min_free_gb": "40"})
report("error=" in r.headers["Location"] and settings.storage()["retention_days"] == 7, "a negative number of days is refused")
r = c.post("/settings/storage", data={"retention_days": "x", "keep_days": "60", "min_free_gb": "40"})
report("error=" in r.headers["Location"], "text instead of a number is refused")

# ---------- where recordings go ----------
report("helper on the server is not installed" in page, "without the helper, Storage says how to install it")
r = c.post("/settings/storage/move", data={"kind": "folder", "path": "/mnt/disk2/rec", "copy": "1"})
report("error=" in r.headers["Location"] and not updates.REQUEST.exists(), "a move waits for the helper")
updates.DIR.mkdir(parents=True, exist_ok=True)
updates.STATUS.write_text(json.dumps({"helper": True, "state": "done"}))
(updates.DIR / "host.json").write_text(json.dumps({"recordings": "/srv/camwatch/recordings", "can_mount": False,
    "mount_problem": "lxc-unprivileged", "hostname": "camwatch",
    "disks": [{"mount": "/srv/camwatch", "fs": "ext4", "size": 52e9, "free": 43e9, "network": False},
              {"mount": "/mnt/nas", "fs": "cifs", "size": 4e12, "free": 3e12, "network": True}]}))
page = c.get("/settings").get_data(as_text=True)
report("/srv/camwatch/recordings" in page and "/mnt/nas · 3000 GB free" in page and "network" in page,
       "Storage lists the host's disks and the current folder")
report("cannot connect to a network share itself" in page and "pct set" in page,
       "an unprivileged container gets the Proxmox steps for a network share")
for bad in ("relative/path", "/mnt/../etc", "/mnt/disk2;rm -rf"):
    r = c.post("/settings/storage/move", data={"kind": "folder", "path": bad})
    report("error=" in r.headers["Location"] and not updates.REQUEST.exists(), f"a bad folder is refused: {bad}")
c.post("/settings/storage/move", data={"kind": "folder", "path": "/mnt/nas/camwatch/recordings/", "copy": "1"})
req = json.loads(updates.REQUEST.read_text())
report(req["action"] == "storage" and req["path"] == "/mnt/nas/camwatch/recordings" and req["copy"] is True,
       f"Move asks the host helper: {req}")
page = c.get("/settings").get_data(as_text=True)
report("Waiting for the server to start" in page, "Settings shows the waiting move")
report(updates.status()["state"] != "waiting", "a waiting move does not show as a waiting update")
updates.REQUEST.unlink()
c.post("/settings/storage/move", data={"kind": "smb", "server": "nas.local", "share": "camwatch", "user": "cam",
                                       "password": "pw-123", "copy": ""})
req = json.loads(updates.REQUEST.read_text())
report(req.get("network") == {"kind": "smb", "server": "nas.local", "share": "camwatch", "user": "cam", "password": "pw-123"}
       and req["copy"] is False, "an SMB share goes to the helper with its login")
report("pw-123" not in c.get("/settings").get_data(as_text=True), "the page never shows the share's password")
updates.REQUEST.unlink()
r = c.post("/settings/storage/move", data={"kind": "nfs", "server": "nas;reboot", "share": "x"})
report("error=" in r.headers["Location"] and not updates.REQUEST.exists(), "a bad server name is refused")

# ---------- the host helper's checks ----------
host_dir = root / "opt-camwatch"
host_dir.mkdir()
(host_dir / ".env").write_text(f"DATA_PATH={(root / 'data').as_posix()}\nRECORDINGS_PATH=/srv/camwatch/recordings\nTZ=x\n")
sys.argv = ["update.py", str(host_dir)]
spec = importlib.util.spec_from_file_location("helper", REPO / "extras" / "update.py")
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
old = Path("/srv/camwatch/recordings")
helper.DATA = Path("/srv/camwatch/data")      # the test's own data folder is in /tmp, itself a system folder on Linux
for target, want in (("/etc/camwatch", "system folder"), ("/srv/camwatch/recordings", "already"),
                     ("/srv/camwatch/recordings/new", "inside"), ("/srv/camwatch/data/rec", "data folder"),
                     ("/mnt/nas/camwatch/recordings", None)):
    got = helper.check_target(Path(target), old)
    report((got is None) if want is None else (want in (got or "")), f"helper check for {target}: {got}")
code = helper.move_storage({"action": "storage", "path": "/etc/camwatch", "copy": True})
st = json.loads((root / "data" / "update" / "storage.json").read_text())
report(code == 1 and st["state"] == "failed" and "system folder" in st["message"] and "Nothing changed" in st["message"]
       and "CamWatch" not in (host_dir / ".env").read_text().split("RECORDINGS_PATH=")[1][:5],
       f"a move to a refused folder reports why and changes nothing: {st['message']}")
helper.set_env("RECORDINGS_PATH", "/mnt/nas/camwatch/recordings")
env = (host_dir / ".env").read_text()
report("RECORDINGS_PATH=/mnt/nas/camwatch/recordings" in env and env.count("RECORDINGS_PATH=") == 1 and "TZ=x" in env,
       "the helper changes one line in .env and keeps the rest")

print("ALL PASSED" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
