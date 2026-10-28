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
report(len(seen) == n, "a second check within 3 minutes uses the cached answer")
fake_github.compare = "behind"
r = c.get("/api/update?force=1").get_json()
report(r.get("newer") is False, "a running commit newer than GitHub's is not an update")
fake_github.compare = "ahead"


real_version = updates.app_version
for running_version, want in (("2026.10.29", False), ("2026.10.28.9", True), ("dev", True)):
    updates.app_version = lambda v=running_version: {"version": v, "commit": "", "date": "", "text": v}
    r = c.get("/api/update?force=1").get_json()
    report(r.get("newer") is want, f"without a known commit, {running_version} vs 2026.10.29 on GitHub: newer={r.get('newer')}")
updates.app_version = real_version
report(updates.version_key("2026.10.28.1") > updates.version_key("2026.10.28") > updates.version_key("dev"),
       "version numbers compare part by part")


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
report("/settings/update/key" in page, "Settings links to the guide for the access key")
guide = c.get("/settings/update/key").get_data(as_text=True)
report("Generate token" in guide and "Read-only" in guide and "<b>Amplitude</b>" in guide,
       "the guide explains each step and names the repository")
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

# ---------- feature requests ----------
import feature_requests  # noqa: E402

made = []


def fake_issues(method, path, token, body=None):
    made.append((method, path, token, body))
    if fake_issues.refuse:
        raise feature_requests.GitHubError("GitHub refused: the access key needs Issues - Read and write (see the guide)")
    if method == "POST":
        return {"number": 42, "html_url": "https://github.com/johanhoel/Amplitude/issues/42"}
    return {"state": "closed"}


fake_issues.refuse = True
feature_requests._api = fake_issues
page = c.get("/requests").get_data(as_text=True)
report("Request a feature" in page and "Send request" in page, "the Request a feature page opens")
report("/requests" in c.get("/settings").get_data(as_text=True), "Settings and the footer link to Request a feature")
r = c.post("/requests", data={"title": "Quiet  hours", "text": "No pushes at night, please.", "name": ""})
page = c.get(r.headers["Location"]).get_data(as_text=True)
rows = feature_requests.load()
report(len(rows) == 1 and rows[0]["title"] == "Quiet hours" and not rows[0].get("number"),
       "a request GitHub refuses is still saved")
report("did not get it" in page and "Send again" in page and "Issues - Read and write" in page,
       "the page says GitHub refused, why, and offers Send again")
fake_issues.refuse = False
c.post(f"/requests/{rows[0]['id']}/resend")
rows = feature_requests.load()
post = [m for m in made if m[0] == "POST"][-1]
report(rows[0].get("number") == 42 and rows[0]["url"].endswith("/42"), "Send again creates the GitHub issue")
report(post[1] == "/repos/johanhoel/Amplitude/issues" and post[2] == "github_pat_SECRET123"
       and post[3]["title"] == "[CamWatch] Quiet hours" and "feature request" in post[3]["labels"]
       and "No pushes at night" in post[3]["body"], f"the issue goes to the update repository with a clear title: {post[3]['title']}")
c.post("/requests", data={"title": "Bigger buttons", "text": "On the phone.", "name": "Alex"})
rows = feature_requests.load()
report(len(rows) == 2 and rows[0]["title"] == "Bigger buttons" and "Alex" in [m for m in made if m[0] == "POST"][-1][3]["body"],
       "a new request goes first, with the optional name")
feature_requests._states["at"] = 0
page = c.get("/requests").get_data(as_text=True)
report("✓ done" in page, "a closed issue shows as done")
r = c.post("/requests", data={"title": "", "text": "x"})
report("error=" in r.headers["Location"] and len(feature_requests.load()) == 2, "an empty request is refused")
report("SECRET123" not in page, "the requests page never shows the access key")
guide = c.get("/settings/update/key").get_data(as_text=True)
report("Issues" in guide and "Read and write" in guide, "the guide adds Issues - Read and write to the key")

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
