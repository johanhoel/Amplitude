"""Is there a newer Home Deck on GitHub, and what changed since this one.

Same shape as CamWatch's updater, and for the same reason: the panels run on
a wall and nobody wants to open a terminal to move them forward. The check is
read-only and cached; installing is a separate, deliberate POST.

What makes this safe is not this file. It is homedeck-apply, which already
checks every module and setting before restarting, waits for the panels to
answer, and puts the previous snapshot back if they do not. The updater only
has to put new files in place and call it.
"""
import datetime as dt
import json
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # /opt/panel-wrapper
REPO = 'johanhoel/Amplitude'
FOLDER = 'panels'
BRANCH = 'main'
CACHE_SECONDS = 180
STATUS = ROOT / '.update-status.json'
# Written at install time so the panels know which commit they are running.
# Without it the version number alone decides, which is coarser but still works.
STAMP = ROOT / '.commit'

_lock = threading.Lock()
_cache = {'at': 0, 'result': None}


class GitHubError(Exception):
    pass


def _get(path, raw=False):
    req = urllib.request.Request('https://api.github.com' + path, headers={
        'Accept': 'application/vnd.github.raw' if raw else 'application/vnd.github+json',
        'User-Agent': 'homedeck-updates'})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            body = r.read()
    except urllib.error.HTTPError as e:
        raise GitHubError(f'GitHub said {e.code}') from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise GitHubError(f'cannot reach GitHub: {e}') from e
    return body.decode('utf-8', 'replace') if raw else json.loads(body)


def current():
    """{version, commit} for what is running here."""
    def read(p, default=''):
        try:
            return p.read_text(encoding='utf-8').strip()
        except OSError:
            return default
    return {'version': read(ROOT / 'VERSION', 'unknown'), 'commit': read(STAMP)}


def _notes(commits, running):
    """One line per change since the running commit, newest first.

    Built from the commit list the check already fetched, so it costs no extra
    request. GitHub filters that list to this folder, which matters because
    the repository holds several projects: a CamWatch change is not a Home
    Deck change.
    """
    out = []
    for c in commits:
        if running and c['sha'].startswith(running):
            break
        line = (c.get('commit', {}).get('message') or '').split('\n')[0].strip()
        if not line or line.startswith('Merge '):
            continue
        out.append({'short': c['sha'][:7],
                    'date': c['commit']['committer']['date'][:10],
                    'text': line[:140]})
        if len(out) >= 15:
            break
    return out


def check(force=False):
    """{current, newer, latest:{sha, short, date, message, notes}} or {error}."""
    now = current()
    with _lock:
        if not force and _cache['result'] and time.time() - _cache['at'] < CACHE_SECONDS:
            return _cache['result']
    try:
        commits = _get(f'/repos/{REPO}/commits?sha={BRANCH}&path={FOLDER}&per_page=20')
        if not commits:
            raise GitHubError(f'no commits under {FOLDER}/ on {BRANCH}')
        sha = commits[0]['sha']
        info = commits[0]['commit']
        result = {
            'current': now,
            # Without a recorded commit we cannot tell new from old, so say so
            # rather than offer an update that might be a downgrade.
            'newer': bool(now['commit']) and not sha.startswith(now['commit']),
            'unknown_commit': not now['commit'],
            'checked': dt.datetime.now().isoformat(timespec='seconds'),
            'latest': {'sha': sha, 'short': sha[:7],
                       'date': info['committer']['date'][:10],
                       'message': info['message'].split('\n')[0][:120],
                       'notes': _notes(commits, now['commit'])},
        }
    except (GitHubError, KeyError, IndexError, TypeError, ValueError) as exc:
        result = {'current': now, 'error': str(exc)}
    with _lock:
        _cache.update(at=time.time(), result=result)
    return result


def status():
    """What the updater is doing: idle | running | done | failed."""
    try:
        return json.loads(STATUS.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {'state': 'idle'}


def ready():
    """The newer version from the last check, for the header pill. Never asks
    GitHub itself, so a page load costs nothing."""
    r = _cache['result']
    if r and r.get('newer') and time.time() - _cache['at'] < 6 * 3600:
        return r['latest']['short']
    return None
