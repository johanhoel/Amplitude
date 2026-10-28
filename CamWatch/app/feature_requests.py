"""Request a feature: each request becomes a GitHub issue in the repository that Settings -> Updates points at.

Two ways, by whether Settings -> Updates holds an access key:
- no key: the page opens GitHub's "New issue" form, filled in; you press Submit there with your own GitHub account.
- a key with "Issues: Read and write": CamWatch creates the issue itself.
Every request is also kept in DATA_DIR/feature_requests.jsonl, so nothing is lost when GitHub refuses it.
"""
import datetime as dt
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import updates
from common import app_version, env

FILE = Path(env("DATA_DIR", "/data")) / "feature_requests.jsonl"
LABELS = ["feature request", "camwatch"]
_lock = threading.Lock()
_states = {"at": 0.0, "data": {}}


class GitHubError(Exception):
    pass


def _api(method, path, token, body=None):
    req = urllib.request.Request("https://api.github.com" + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None, headers={
                                     "Accept": "application/vnd.github+json", "User-Agent": "camwatch",
                                     "Content-Type": "application/json",
                                     **({"Authorization": f"Bearer {token}"} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8", "replace") or "null")
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403, 404):
            raise GitHubError("GitHub refused: the access key needs Issues - Read and write (see the guide)")
        if exc.code == 410:
            raise GitHubError("the repository has issues switched off")
        raise GitHubError(f"GitHub answered {exc.code}")
    except OSError as exc:
        raise GitHubError(f"GitHub is not reachable: {getattr(exc, 'reason', exc)}")


def load():
    """All requests, newest first."""
    try:
        rows = [json.loads(line) for line in FILE.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, ValueError):
        rows = []
    return sorted(rows, key=lambda r: r.get("id", ""), reverse=True)


def _save(rows):
    FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = FILE.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(r) + "\n" for r in sorted(rows, key=lambda r: r.get("id", ""))),
                   encoding="utf-8")
    tmp.replace(FILE)


def _body(row, limit=None):
    text = row["text"] if not limit or len(row["text"]) <= limit else row["text"][:limit] + " …"
    return (f"{text}\n\n---\nSent from CamWatch {row['version']}"
            f"{' · from ' + row['name'] if row.get('name') else ''}")


def new_issue_url(row):
    """GitHub's "New issue" form, filled in with this request (for a server without an access key)."""
    query = urllib.parse.urlencode({"title": f"[CamWatch] {row['title']}", "body": _body(row, 3000),
                                    "labels": ",".join(LABELS)})
    return f"https://github.com/{updates.options()['repo']}/issues/new?{query}"


def _send(row):
    """Create the GitHub issue for this request; fills in number/url, or error. Without a key: nothing to do here."""
    opts = updates.options()
    if not opts["token"]:
        row.update(browser=True, error=None)
        return row
    body = _body(row)
    try:
        issue = _api("POST", f"/repos/{opts['repo']}/issues", opts["token"],
                     {"title": f"[CamWatch] {row['title']}", "body": body, "labels": LABELS})
        row.update(number=issue["number"], url=issue["html_url"], state="open", error=None, browser=False)
    except (GitHubError, KeyError, TypeError) as exc:
        row["error"] = str(exc)
    return row


def submit(title, text, name=""):
    """Keep the request and send it to GitHub. Returns the stored row."""
    row = {"id": dt.datetime.now().strftime("%Y%m%d%H%M%S%f"), "created": dt.datetime.now().isoformat(timespec="seconds"),
           "title": title, "text": text, "name": name, "version": app_version()["text"]}
    _send(row)
    with _lock:
        rows = load()
        rows.append(row)
        _save(rows)
    return row


def resend(request_id):
    with _lock:
        rows = load()
        for row in rows:
            if row["id"] == request_id and not row.get("number"):
                _send(row)
                _save(rows)
                return row
    return None


def refresh_states(max_age=300):
    """Open/closed for the sent requests, from GitHub (at most every 5 minutes). Quietly keeps the old state on errors."""
    if time.time() - _states["at"] < max_age:
        return
    _states["at"] = time.time()
    opts = updates.options()
    with _lock:
        rows = load()
        changed = False
        for row in rows:
            if not row.get("number") or not opts["token"]:
                continue
            try:
                issue = _api("GET", f"/repos/{opts['repo']}/issues/{row['number']}", opts["token"])
            except GitHubError:
                break
            if issue and issue.get("state") and issue["state"] != row.get("state"):
                row["state"] = issue["state"]
                changed = True
        if changed:
            _save(rows)
