"""Settings for Home Deck: read homedeck.toml, check every value, and fall back to the last good copy.

Only the Home Assistant address is required. Everything else has a default, and the house itself (rooms, lights,
people, media players, door lock, weather) is read from Home Assistant, so a new install works without editing.
  - the file is checked value by value against SPEC below; a bad value is reported with its name;
  - when it is fine, a copy is kept as $STATE_DIRECTORY/homedeck.last-good.toml;
  - when it is not, the server starts with that last good copy (or the defaults) and /api/health lists the problems.
`python3 -m homedeck.check` runs the same checks without starting anything (homedeck-apply does that first).
"""
import ipaddress, os, re, shutil, tomllib, zoneinfo
from types import SimpleNamespace

ROOT = os.environ.get('HOMEDECK_ROOT', '/opt/panel-wrapper')
CONFIG_FILE = os.environ.get('HOMEDECK_CONFIG', os.path.join(ROOT, 'homedeck.toml'))
STATE = os.environ.get('STATE_DIRECTORY', '/var/lib/panel-wrapper')
LAST_GOOD = os.path.join(STATE, 'homedeck.last-good.toml')
VERSION_FILE = os.path.join(ROOT, 'VERSION')


# ---------- value checks: each returns an error text, or None when the value is fine ----------
def _url(v):
    return None if isinstance(v, str) and re.fullmatch(r'https?://[^\s/]+(/\S*)?', v) else 'must be a web address like http://192.168.1.20:8123'


def _entity_or_empty(v):
    return None if isinstance(v, str) and (v == '' or re.fullmatch(r'[a-z_]+\.[a-z0-9_]+', v)) else \
        'must be a Home Assistant entity id like lock.front_door, or "" to find it automatically'


def _regex(v):
    try:
        re.compile(v)
        return None
    except (re.error, TypeError) as e:
        return f'is not a valid regular expression ({e})'


def _tz(v):
    try:
        zoneinfo.ZoneInfo(v)
        return None
    except Exception:
        return 'must be a time zone like Europe/Stockholm'


def _str(v):
    return None if isinstance(v, str) and v.strip() else 'must be a non-empty text in quotes'


def _bool(v):
    return None if isinstance(v, bool) else 'must be true or false (no quotes)'


def _int(lo=0, hi=10 ** 9):
    def f(v):
        return None if isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi else f'must be a whole number from {lo} to {hi}'
    return f


def _list(inner):
    def f(v):
        if not isinstance(v, list):
            return 'must be a list in [brackets]'
        for i, x in enumerate(v):
            e = inner(x)
            if e:
                return f'item {i + 1} ({x!r}) {e}'
    return f


def _map(inner, key=None):
    def f(v):
        if not isinstance(v, dict):
            return 'must be a table of  name = value  lines'
        for k, x in v.items():
            if key and key(k):
                return f'name {k!r} {key(k)}'
            e = inner(x)
            if e:
                return f'{k!r} {e}'
    return f


def _record(fields):
    def f(v):
        if not isinstance(v, dict):
            return 'must be a table'
        for k, check in fields.items():
            if k not in v:
                return f'is missing {k!r}'
            e = check(v[k])
            if e:
                return f'{k!r} {e}'
    return f


def _pair(v):
    return None if isinstance(v, list) and len(v) == 2 and all(isinstance(x, str) for x in v) else 'must be ["short name", "room"]'


def _entity(v):
    return None if isinstance(v, str) and re.fullmatch(r'[a-z_]+\.[a-z0-9_]+', v) else 'must be a Home Assistant entity id like light.kitchen'


def _stop(v):
    return None if isinstance(v, str) and (v == '' or re.fullmatch(r'\d{16}', v)) else 'must be a 16-digit Västtrafik stop id in quotes, or ""'


# every setting: dotted name -> (check, default). Missing settings take the default.
SPEC = {
    'server.port': (_int(1, 65535), 80),
    'server.timezone': (_tz, 'Europe/Stockholm'),
    'server.title': (_str, 'Home Deck'),
    'homeassistant.url': (_url, None),                                   # required
    'entities.lock': (_entity_or_empty, ''),
    'entities.weather': (_entity_or_empty, ''),
    'rooms.order': (_list(_str), []),
    'rooms.skip_lights': (_regex, r'^$'),
    'rooms.names': (_map(_pair, key=_entity), {}),
    'rooms.hide': (_list(_str), []),
    'players.list': (_list(_record({'entity': _entity, 'label': _str})), []),
    'players.hide': (_list(_entity), []),
    'people.hide': (_list(_entity), []),
    'transit.bus_stop': (_stop, ''),
    'transit.feed': (_url, 'https://avgangstavla.vasttrafik.se/api/events?board1Gids={g}&board1Modules=departures&board1Modules=trafficSituations&board2Gids={g}&board2Modules=arrivals'),
    'transit.stop_search': (_url, 'https://avgangstavla.vasttrafik.se/api/stopAreas'),
    'leave.enabled': (_bool, True),
    'leave.grace_s': (_int(30, 86400), 180),
    'leave.lock_check_s': (_int(5, 600), 45),
    'notify.ntfy_server': (_url, 'https://ntfy.sh'),
    'layouts.keep': (_int(1, 500), 30),
    'news.enabled': (_bool, True),
    'news.max_items': (_int(1, 200), 40),
    'news.feeds': (_map(_url, key=lambda k: None if re.fullmatch(r'[a-z]+', k) else 'must be lower-case letters'),
                   {'vast': 'https://www.svt.se/nyheter/lokalt/vast/rss.xml', 'all': 'https://www.svt.se/nyheter/rss.xml'}),
    'links.extra': (_map(_url), {}),
}


def _get(tree, dotted):
    cur = tree
    for part in dotted.split('.'):
        if not isinstance(cur, dict) or part not in cur:
            return KeyError
        cur = cur[part]
    return cur


def validate(tree):
    """-> list of readable problems ('section.key: what is wrong'); empty when everything is fine."""
    errs = []
    for key, (check, default) in SPEC.items():
        v = _get(tree, key)
        if v is KeyError:
            if default is None:
                errs.append(f'{key}: missing (required)')
            continue
        e = check(v)
        if e:
            errs.append(f'{key}: {e}')
    return errs


def read(path):
    """-> (tree, problems). A broken file gives the TOML error with its line number."""
    try:
        with open(path, 'rb') as f:
            tree = tomllib.load(f)
    except FileNotFoundError:
        return None, [f'{path} not found']
    except tomllib.TOMLDecodeError as e:
        return None, [f'{os.path.basename(path)}: {e}']
    return tree, validate(tree)


def _val(t, key):
    v = _get(t, key)
    return SPEC[key][1] if v is KeyError else v


def _derive(t):
    v = lambda k: _val(t, k)
    try:
        version = open(VERSION_FILE).read().strip()
    except OSError:
        version = 'dev'
    return SimpleNamespace(
        VERSION=version, PORT=v('server.port'), TITLE=v('server.title'), STATIC=os.path.join(ROOT, 'www'),
        LOCAL_TZ=zoneinfo.ZoneInfo(v('server.timezone')), TIMEZONE=v('server.timezone'),
        HA=v('homeassistant.url').rstrip('/'),
        LOCK=v('entities.lock'), WEATHER=v('entities.weather'),
        ROOM_ORDER=list(v('rooms.order')), SKIP_LIGHTS=re.compile(v('rooms.skip_lights')),
        ROOM_OF={k: tuple(x) for k, x in v('rooms.names').items()}, HIDE_ROOMS=set(v('rooms.hide')),
        PLAYERS_FIXED=[(x['entity'], x['label']) for x in v('players.list')], HIDE_PLAYERS=set(v('players.hide')),
        HIDE_PEOPLE=set(v('people.hide')),
        BUS_STOP=v('transit.bus_stop'), BUS_FEED=v('transit.feed'), STOP_SEARCH=v('transit.stop_search'),
        LEAVE_ON=v('leave.enabled'), LEAVE_GRACE=v('leave.grace_s'), LOCK_CHECK_S=v('leave.lock_check_s'),
        NTFY=v('notify.ntfy_server').rstrip('/'),
        LAYOUT_PAGES={'start', 'familyinfo'}, LAYOUT_KEEP=v('layouts.keep'),
        NEWS_ON=v('news.enabled'), NEWS_FEEDS=dict(v('news.feeds')), NEWS_MAX=v('news.max_items'),
        LINKS_EXTRA=dict(v('links.extra')),
    )


def load():
    """-> (settings, report). report = {file, ok, problems, using}: what /api/health shows."""
    tree, errs = read(CONFIG_FILE)
    report = {'file': CONFIG_FILE, 'ok': not errs, 'problems': errs, 'using': CONFIG_FILE}
    if not errs:
        try:
            c = _derive(tree)
            if os.environ.get('HOMEDECK_READONLY') != '1':
                try:
                    shutil.copyfile(CONFIG_FILE, LAST_GOOD)
                except OSError:
                    pass
            return c, report
        except Exception as e:
            report.update(ok=False, problems=[f'{type(e).__name__}: {e}'])
    tree2, errs2 = read(LAST_GOOD)
    if tree2 is None or errs2:
        raise SystemExit('homedeck.toml has problems and there is no good copy to fall back to:\n  ' + '\n  '.join(errs))
    report['using'] = LAST_GOOD
    print('settings: homedeck.toml has problems, running on the last good copy:\n  ' + '\n  '.join(errs), flush=True)
    return _derive(tree2), report


C, REPORT = (None, None) if os.environ.get('HOMEDECK_CHECKONLY') == '1' else load()
