"""Settings -> Updates: is there a newer camwatch on GitHub, and ask the host to install it.

The web UI only checks GitHub and writes DATA_DIR/update/request.json. The container cannot run Docker, so the host
helper (extras/update.py, started by a systemd path unit from extras/install-updater.sh) downloads that commit and
installs it with extras/release.sh: backup, build, health check, roll back on failure. It reports in status.json.

settings.json "update": {"repo": "owner/name", "folder": "CamWatch", "branch": "main", "token": "github_pat_…"}
A private repository needs a token: a fine-grained GitHub token with read access to Contents of that one repository.
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
CACHE_SECONDS = 600
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
    """{"current", "latest": {sha, short, version, date, message}, "newer": bool} or {"error": ...}. Cached 10 min."""
    opts, current = options(), app_version()
    key = (opts["repo"], opts["folder"], opts["branch"], opts["token"], current["commit"])
    with _lock:
        if not force and _cache["key"] == key and time.time() - _cache["at"] < CACHE_SECONDS:
            return _cache["result"]
    q = urllib.parse.quote
    try:
        commits = _get(f"/repos/{opts['repo']}/commits?sha={q(opts['branch'])}&path={q(opts['folder'])}&per_page=1",
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
                             "date": info["committer"]["date"][:10], "message": info["message"].split("\n")[0][:120]}}
    except (GitHubError, KeyError, IndexError, TypeError, ValueError) as exc:
        result = {"current": current, "error": str(exc) if isinstance(exc, GitHubError) else f"unexpected answer: {exc}"}
    with _lock:
        _cache.update(at=time.time(), key=key, result=result)
    return result


def status():
    """What the host helper reports: {"helper": bool, "state": idle|waiting|running|done|failed, "message", ...}."""
    try:
        data = json.loads(STATUS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    data.setdefault("state", "idle")
    data["helper"] = bool(data.get("helper"))
    if REQUEST.exists():
        data["state"] = "waiting"
    return data


def request_update(sha, version):
    """Ask the host helper to install this commit."""
    DIR.mkdir(parents=True, exist_ok=True)
    tmp = REQUEST.with_suffix(".tmp")
    tmp.write_text(json.dumps({"sha": sha, "version": version,
                               "asked": dt.datetime.now().isoformat(timespec="seconds")}), encoding="utf-8")
    os.replace(tmp, REQUEST)
