"""Settings -> Updates: the version check, the Update now button and the host helper (extras/update.py).
GitHub is faked: updates._get for the web UI, UPDATE_TARBALL for the helper."""
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

root = Path(tempfile.mkdtemp())
for d in ("recordings", "photos", "data", "live"):
    (root / d).mkdir()
REPO = Path(__file__).resolve().parents[1]
os.environ.setdefault("OBJECT_MODEL", str(REPO / "models" / "yolov8s-coco.onnx"))
os.environ.update(RECORDINGS_DIR=str(root / "recordings"), PHOTOS_DIR=str(root / "photos"), DATA_DIR=str(root / "data"),
                  LIVE_DIR=str(root / "live"), CAMERA_NAME="camera1", WEB_PASSWORD="", DB_SOCKET=str(root / "nosock"))
sys.path.insert(0, str(REPO / "app"))
import settings  # noqa: E402
import updates  # noqa: E402
import webui  # noqa: E402

ok = True


def report(good, text):
    global ok
    ok &= bool(good)
    print(f"{'PASS' if good else 'FAIL'} {text}")


running = webui.app_version()["commit"] or "0000000"
NEW = "f" * 40
seen = []


def fake_github(path, token, raw=False):
    seen.append((path, token))
    if "/commits?" in path:
        return [{"sha": NEW, "commit": {"committer": {"date": "2026-10-29T08:00:00Z"}, "message": "CamWatch: better\n\nmore"}}]
    if "/contents/" in path:
        return "2026.10.29\n"
    if "/compare/" in path:
        return {"status": fake_github.compare}
    raise AssertionError(path)


fake_github.compare = "ahead"
updates._get = fake_github
c = webui.app.test_client()

# ---------- the check ----------
r = c.get("/api/update").get_json()
report(r.get("newer") and r["latest"]["version"] == "2026.10.29" and r["latest"]["short"] == "fffffff",
       f"a newer commit on GitHub is a new version: {r.get('latest')}")
report(any("path=CamWatch" in p for p, _ in seen), "the check looks at the CamWatch folder only")
n = len(seen)
c.get("/api/update")
report(len(seen) == n, "a second check within 10 minutes uses the cached answer")
fake_github.compare = "behind"
r = c.get("/api/update?force=1").get_json()
report(r.get("newer") is False, "a running commit newer than GitHub's is not an update")
fake_github.compare = "ahead"


def github_down(path, token, raw=False):
    raise updates.GitHubError("GitHub refused: the repository is private or the access key is wrong")


updates._get = github_down
r = c.get("/api/update?force=1").get_json()
report("private" in r.get("error", ""), f"a refused check says why: {r.get('error')}")
updates._get = fake_github

# ---------- the Settings page and the access key ----------
page = c.get("/settings").get_data(as_text=True)
report('id="updates"' in page and "Update now" in page, "Settings has an Updates section with an Update now button")
report("not installed on the server" in page, "Settings says when the host helper is missing")
c.post("/settings/update", data={"repo": "johanhoel/Amplitude", "folder": "CamWatch", "branch": "main",
                                 "token": "github_pat_SECRET123"})
report(updates.options()["token"] == "github_pat_SECRET123", "the access key is saved")
page = c.get("/settings").get_data(as_text=True)
report("SECRET123" not in page and "saved - leave empty to keep" in page, "the page never shows the saved access key")
report("SECRET123" not in c.get("/api/update").get_data(as_text=True), "/api/update never shows the access key")
c.post("/settings/update", data={"repo": "johanhoel/Amplitude", "folder": "CamWatch", "branch": "main", "token": ""})
report(updates.options()["token"] == "github_pat_SECRET123", "an empty field keeps the saved access key")
report(seen[-1][1] == "github_pat_SECRET123", "the check sends the saved access key")
r = c.post("/settings/update", data={"repo": "not a repo", "folder": "CamWatch", "branch": "main"})
report("error=" in r.headers["Location"], "a repository that is not owner/name is refused")

# ---------- Update now ----------
r = c.post("/settings/update/run", data={"sha": NEW})
report("error=" in r.headers["Location"] and not updates.REQUEST.exists(), "Update now waits for the host helper")
updates.DIR.mkdir(parents=True, exist_ok=True)
updates.STATUS.write_text(json.dumps({"helper": True, "state": "idle"}))
r = c.post("/settings/update/run", data={"sha": "a" * 40})
report("error=" in r.headers["Location"] and not updates.REQUEST.exists(), "Update now refuses a commit that is not the newest")
c.post("/settings/update/run", data={"sha": NEW})
req = json.loads(updates.REQUEST.read_text()) if updates.REQUEST.exists() else {}
report(req.get("sha") == NEW and req.get("version") == "2026.10.29", f"Update now asks the host for the new commit: {req}")
s = c.get("/api/update/status").get_json()
report(s["state"] == "waiting" and s["version"]["version"], f"the status says the update is waiting: {s['state']}")
page = c.get("/settings").get_data(as_text=True)
report("Waiting for the server" in page, "Settings shows the waiting update")
updates.REQUEST.unlink()

# ---------- the host helper ----------
bash = shutil.which("bash")
if os.name == "nt":    # System32\bash.exe is WSL; use Git Bash
    git = shutil.which("git")
    found = [p / "bin" / "bash.exe" for p in Path(git).resolve().parents if (p / "bin" / "bash.exe").exists()] if git else []
    bash = str(found[0]) if found else None
if not bash:
    print("SKIP the host helper: no bash")
else:
    def tarball(release_sh):
        out = io.BytesIO()
        with tarfile.open(fileobj=out, mode="w:gz") as t:
            for name, body in {"johanhoel-Amplitude-fffffff/README.md": b"monorepo",
                               "johanhoel-Amplitude-fffffff/Other/app/x.py": b"not camwatch",
                               "johanhoel-Amplitude-fffffff/CamWatch/docker-compose.yml": b"services: {}",
                               "johanhoel-Amplitude-fffffff/CamWatch/app/VERSION": b"2026.10.29",
                               "johanhoel-Amplitude-fffffff/CamWatch/extras/release.sh": release_sh}.items():
                info = tarfile.TarInfo(name)
                info.size = len(body)
                t.addfile(info, io.BytesIO(body))
        path = root / "github.tar.gz"
        path.write_bytes(out.getvalue())
        return path

    host = root / "opt-camwatch"
    host.mkdir()
    (host / ".env").write_text(f"DATA_PATH={(root / 'data').as_posix()}\n")
    env = {**os.environ, "PATH": str(Path(bash).parent) + os.pathsep + os.environ["PATH"]}

    def helper(release_sh):
        updates.request_update(NEW, "2026.10.29")
        env["UPDATE_TARBALL"] = str(tarball(release_sh))
        p = subprocess.run([sys.executable, str(REPO / "extras" / "update.py"), str(host)], env=env,
                           capture_output=True, text=True)
        return p.returncode, json.loads(updates.STATUS.read_text())

    code, st = helper(b'set -e\nfiles=$(tar tf -)\necho "$files" | grep -qx app/VERSION\n'
                      b'echo "$files" | grep -q x.py && exit 9\necho ">> $1 is running the new version"\n')
    report(code == 0 and st["state"] == "done" and "2026.10.29" in st["message"], f"the helper installs the update: {st['message']}")
    report("staging is running" in st.get("log", ""), "the helper gives release.sh only the CamWatch folder")
    report(not updates.REQUEST.exists(), "the helper removes the request")
    code, st = helper(b'cat >/dev/null\necho ">> rolled back: staging runs the previous version again" >&2\nexit 1\n')
    report(code == 1 and st["state"] == "failed" and "previous version runs again" in st["message"],
           f"a failed update says the old version runs again: {st['message']}")
    updates.request_update("not-a-commit", "x")
    p = subprocess.run([sys.executable, str(REPO / "extras" / "update.py"), str(host)], env=env, capture_output=True, text=True)
    st = json.loads(updates.STATUS.read_text())
    report(p.returncode == 1 and "not a commit" in st["message"], "the helper refuses a request that is not a commit")

print("ALL PASSED" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
