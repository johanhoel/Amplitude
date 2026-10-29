"""Settings -> Updates: is there a newer camwatch on GitHub, and ask the host to install it.

The web UI only checks GitHub and writes DATA_DIR/update/request.json. The container cannot run Docker, so the host
helper (extras/update.py, started by a systemd path unit from extras/install-updater.sh) downloads that commit and
installs it with extras/release.sh: backup, build, health check, roll back on failure. It reports in status.json.

settings.json "update": {"repo": "owner/name", "folder": "CamWatch", "branch": "main", "token": "github_pat_…"}
The repository is public, so no token is needed. A token (fine-grained, Contents read-only + Issues read and write)
lets Request a feature create issues itself, raises GitHub's limit of 60 checks an hour, and is needed when private.
"""
import datetime as dt
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import settings
from common import app_version, env

DIR = Path(env("DATA_DIR", "/data")) / "update"
REQUEST, STATUS = DIR / "request.json", DIR / "status.json"
DEFAULTS = {"repo": "johanhoel/Amplitude", "folder": "CamWatch", "branch": "main", "token": ""}
CACHE_SECONDS = 180
_cache = {"at": 0.0, "key": None, "result": None}
_lock = threading.Lock()


class GitHubError(Exception):
    pass


def options(conf=None):
    saved = (conf or settings.load()).get("update") or {}
    return {key: str(saved.get(key) or default) for key, default in DEFAULTS.items()}


def _get(path, token, raw=False):
    """GET api.github.com<path> as JSON (or text with raw=True)."""
    req = urllib.request.Request("https://api.github.com" + path, headers={
        "Accept": "application/vnd.github.raw" if raw else "application/vnd.github+json",
        "User-Agent": "camwatch-updater", **({"Authorization": f"Bearer {token}"} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            body = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        if token and exc.code in (401, 403):
            # an old or wrong key: a public repository answers without one
            return _get(path, "", raw)
        if exc.code == 403 and not token:
            raise GitHubError("GitHub allows 60 checks an hour without an access key - try again later")
        if exc.code in (401, 403, 404):
            raise GitHubError("GitHub refused: the repository is private or the access key is wrong"
                              if exc.code != 403 else "GitHub refused the access key (or too many checks - try later)")
        raise GitHubError(f"GitHub answered {exc.code}")
    except OSError as exc:
        raise GitHubError(f"GitHub is not reachable: {getattr(exc, 'reason', exc)}")
    return body if raw else json.loads(body)


def version_key(text):
    """2026.10.28.1 -> (2026, 10, 28, 1); "dev" or junk -> () (lower than any version)."""
    try:
        return tuple(int(part) for part in text.strip().split("."))
    except ValueError:
        return ()


def check(force=False):
    """{"current", "latest": {sha, short, version, date, message}, "newer": bool} or {"error": ...}. Cached 3 min."""
    opts, current = options(), app_version()
    key = (opts["repo"], opts["folder"], opts["branch"], opts["token"], current["commit"])
    with _lock:
        if not force and _cache["key"] == key and time.time() - _cache["at"] < CACHE_SECONDS:
            return _cache["result"]
    q = urllib.parse.quote
    try:
        # 20 rather than 1: the extra entries cost nothing on the same call and
        # are what the release notes are built from below.
        commits = _get(f"/repos/{opts['repo']}/commits?sha={q(opts['branch'])}&path={q(opts['folder'])}&per_page=20",
                       opts["token"])
        if not commits:
            raise GitHubError(f"no commits in {opts['folder']}/ on {opts['branch']}")
        sha = commits[0]["sha"]
        info = commits[0]["commit"]
        version = _get(f"/repos/{opts['repo']}/contents/{q(opts['folder'])}/app/VERSION?ref={sha}",
                       opts["token"], raw=True).strip()
        if current["commit"]:
            newer = not sha.startswith(current["commit"])
        else:       # an install from a git clone may not know its commit: then only a higher version number counts
            newer = version_key(version) > version_key(current["version"])
        if current["commit"] and newer:
            try:      # the running commit can be newer than the last change in the folder (or not on GitHub)
                state = _get(f"/repos/{opts['repo']}/compare/{current['commit']}...{sha}", opts["token"])["status"]
                newer = state == "ahead"
            except GitHubError:
                pass
        result = {"current": current, "newer": newer, "checked": dt.datetime.now().isoformat(timespec="seconds"),
                  "latest": {"sha": sha, "short": sha[:7], "version": version[:40],
                             "date": info["committer"]["date"][:10], "message": info["message"].split("\n")[0][:120],
                             "notes": _notes(commits, current["commit"])}}
    except (GitHubError, KeyError, IndexError, TypeError, ValueError) as exc:
        result = {"current": current, "error": str(exc) if isinstance(exc, GitHubError) else f"unexpected answer: {exc}"}
    with _lock:
        _cache.update(at=time.time(), key=key, result=result)
    return result


def _notes(commits, running):
    """What changed in this folder since the running commit: one line each.

    Built from the commit list the check already fetched, so it costs no extra
    request. Only commits that touched the folder are in that list, which is
    what makes this usable in a repository holding several projects.

    Stops at the running commit. An install that does not know its commit, or
    one further back than the page of commits fetched, gets the newest few and
    says so by returning everything it has.
    """
    out = []
    for c in commits:
        if running and c["sha"].startswith(running):
            break
        line = (c.get("commit", {}).get("message") or "").split("\n")[0].strip()
        if not line:
            continue
        # A merge commit is bookkeeping, not a change anyone reads about.
        if line.startswith("Merge "):
            continue
        out.append({"short": c["sha"][:7],
                    "date": c["commit"]["committer"]["date"][:10],
                    "text": line[:140]})
        if len(out) >= 15:
            break
    return out


def ready():
    """The newer version from the last check (for the top bar), or None. Never asks GitHub itself."""
    r = _cache["result"]
    if r and r.get("newer") and _cache["key"] and _cache["key"][-1] == app_version()["commit"] \
            and time.time() - _cache["at"] < 6 * 3600:
        return r["latest"]["version"]
    return None


def start_background_check(every=1800):
    """Ask GitHub every 30 minutes, so the top bar knows about a new version without making a page wait."""
    def loop():
        time.sleep(20)
        while True:
            try:
                check(force=True)
            except Exception:       # never let the check stop the web UI
                pass
            time.sleep(every)
    threading.Thread(target=loop, daemon=True, name="update-check").start()


def _waiting():
    """The action of the request the host helper has not picked up yet, or None."""
    try:
        return json.loads(REQUEST.read_text(encoding="utf-8")).get("action", "update")
    except (OSError, ValueError):
        return None


def status(path=None, action="update"):
    """What the host helper reports: {"helper": bool, "state": idle|waiting|running|done|failed, "message", ...}.
    status.json for updates; storage_status() for moving the recordings."""
    try:
        data = json.loads((path or STATUS).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    data.setdefault("state", "idle")
    try:
        data["helper"] = bool(json.loads(STATUS.read_text(encoding="utf-8")).get("helper"))
    except (OSError, ValueError):
        data["helper"] = False
    if _waiting() == action:
        data["state"] = "waiting"
    return data


def storage_status():
    return status(DIR / "storage.json", "storage")


def gpu_status():
    return status(DIR / "gpu.json", "gpu")


def host():
    """What the host helper saw on the host: {"recordings", "disks": [...], "can_mount", "mount_problem"} or {}."""
    try:
        return json.loads((DIR / "host.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def ask_host(request):
    """Hand a request to the host helper (it starts within a second)."""
    DIR.mkdir(parents=True, exist_ok=True)
    tmp = REQUEST.with_suffix(".tmp")
    tmp.write_text(json.dumps({**request, "asked": dt.datetime.now().isoformat(timespec="seconds")}), encoding="utf-8")
    os.chmod(tmp, 0o600)        # a network share's password passes through here
    os.replace(tmp, REQUEST)


def request_update(sha, version):
    """Ask the host helper to install this commit."""
    ask_host({"action": "update", "sha": sha, "version": version})
