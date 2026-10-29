"""Settings for Home Deck: read homedeck.toml, check every value, and fall back to the last good copy.

Every address, entity, phone, timer and list lives in /opt/panel-wrapper/homedeck.toml. A typo there must never
take the panels down, so:
  - the file is checked value by value against SPEC below (types, URLs, IP addresses, entity ids, MACs, regexes);
  - when it is fine, a copy is kept as $STATE_DIRECTORY/homedeck.last-good.toml;
  - when it is not (bad TOML, missing key, wrong type), the server starts with that last good copy instead and
    reports the problems at /api/health (the Admin page shows them).
`python3 -m homedeck.check` runs the same checks without starting anything (homedeck-apply does that first).
"""
import ipaddress, os, re, shutil, tomllib, zoneinfo
from types import SimpleNamespace

ROOT = os.environ.get('HOMEDECK_ROOT', '/opt/panel-wrapper')
CONFIG_FILE = os.environ.get('HOMEDECK_CONFIG', os.path.join(ROOT, 'homedeck.toml'))
STATE = os.environ.get('STATE_DIRECTORY', '/var/lib/panel-wrapper')
LAST_GOOD = os.path.join(STATE, 'homedeck.last-good.toml')

# ---------- value checks: each returns an error text, or None when the value is fine ----------
def _url(v):
    return None if isinstance(v, str) and re.fullmatch(r'https?://[^\s/]+(/\S*)?', v) else 'must be a web address like http://192.168.1.70:8123'


def _ip(v):
    try:
        ipaddress.ip_address(v)
        return None
    except (ValueError, TypeError):
        return 'must be an IP address like 192.168.1.30'


def _hostport(v):
    m = re.fullmatch(r'([^\s:]+):(\d{1,5})', v) if isinstance(v, str) else None
    return None if m and 0 < int(m.group(2)) < 65536 else 'must be host:port like 192.168.1.200:8765'


def _entity(v):
    return None if isinstance(v, str) and re.fullmatch(r'[a-z_]+\.[a-z0-9_]+', v) else 'must be a Home Assistant entity id like light.kitchen'


def _mac(v):
    return None if isinstance(v, str) and re.fullmatch(r'([0-9a-f]{2}:){5}[0-9a-f]{2}', v.lower()) else 'must be a MAC address like 02:00:ae:6e:6f:73'


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


def _int(lo=0, hi=10 ** 9):
    def f(v):
        return None if isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi else f'must be a whole number from {lo} to {hi}'
    return f


def _opt(check):
    """A setting the house may not have: empty means 'not here', and the panels for it stay away (addons.py).
    Leaving the line out means the same, so a settings file written before the setting existed still runs."""
    def f(v):
        return None if v in ('', [], {}) else check(v)
    f.optional = True
    return f


def _list(inner, min_len=0):
    def f(v):
        if not isinstance(v, list):
            return 'must be a list in [brackets]'
        if len(v) < min_len:
            return f'needs at least {min_len} item(s)'
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


def _links(v):
    """[links] holds Home Deck's own pages; the setup wizard writes what it found under [links.extra]."""
    if not isinstance(v, dict):
        return 'must be a table of  name = address  lines'
    for k, x in v.items():
        e = _map(_url)(x) if k == 'extra' else _url(x)
        if e:
            return f'{k!r} {e}'


def _hours(v):
    return None if isinstance(v, list) and len(v) == 2 and all(isinstance(x, int) and 0 <= x <= 24 for x in v) else 'must be [start hour, end hour], e.g. [0, 7]'


# every setting: dotted name -> check
SPEC = {
    'server.port': _int(1, 65535), 'server.static_dir': _str, 'server.netaudio': _str, 'server.timezone': _tz,
    'homeassistant.url': _url,
    'services.pc': _opt(_hostport), 'services.pc_proxy_clients': _list(_ip), 'services.labpanel': _opt(_url),
    'services.lab_panel_id': _str, 'services.buttons_panel': _opt(_url), 'services.prometheus': _opt(_url), 'services.camfeed': _opt(_url),
    'services.ollama': _opt(_url), 'services.ntfy': _url, 'services.piholes': _list(_ip),
    'entities.spotify': _opt(_entity), 'entities.lock': _opt(_entity), 'entities.charger': _opt(_entity),
    'entities.charger_power_prefix': _opt(_str),
    'entities.cam_detect': _opt(_entity), 'entities.wake_pc': _opt(_entity), 'entities.tv': _opt(_entity),
    'entities.vacuum': _opt(_entity), 'entities.weather': _opt(_entity), 'entities.apple_tv': _opt(_entity),
    'entities.apple_tv_remote': _opt(_entity),
    'players': _list(_record({'entity': _entity, 'label': _str})),
    'people.hide': _opt(_list(_entity)),
    'apple_tv.commands': _list(_str, 1),
    'pc_actions': _map(lambda v: None if isinstance(v, str) and v.startswith('/') else 'must be a path starting with /'),
    'rooms.order': _list(_str), 'rooms.skip_lights': _regex, 'rooms.names': _map(_pair, key=_entity),
    'presence.phones': _map(_list(_mac, 1)), 'presence.away_after_s': _map(_int(60, 86400)), 'presence.default_away_after_s': _int(60, 86400),
    'presence.night_hours': _hours, 'presence.night_limit_s': _int(60, 86400), 'presence.probe_after_s': _int(30, 86400),
    'presence.probe_trust_s': _int(60, 7 * 86400), 'presence.cam_burst_s': _int(30, 3600), 'presence.cam_leave_silent_s': _int(10, 3600),
    'presence.cam_leave_people': _list(_str), 'presence.cam_leave_after_s': _int(120, 7200),
    'audio.genelecs': _list(_ip), 'audio.front_pair': _list(_str),
    'audio.sources': _map(_record({'device': _str, 'channels': _list(_str, 1)})),
    'transit.bus_stop': _opt(lambda v: None if isinstance(v, str) and re.fullmatch(r'\d{16}', v) else 'must be a 16-digit Västtrafik stop id in quotes'),
    'transit.feed': lambda v: _url(v) or (None if '{g}' in v else 'must contain {g} where the stop id goes'),
    'transit.stop_search': _url,
    'leave.grace_s': _int(30, 86400), 'leave.lock_check_s': _int(5, 600),
    'admin.pages': _list(lambda v: None if isinstance(v, str) and re.fullmatch(r'[a-z0-9_-]+', v) else 'must be a page name like admin'),
    'admin.pin_min_digits': _int(4, 8), 'admin.session_hours': _int(1, 720), 'admin.remember_days': _int(1, 365),
    'admin.max_tries': _int(3, 20), 'admin.lock_minutes': _int(1, 1440),
    'remote.edge': _list(_ip), 'remote.public_url': _opt(_url), 'remote.pair_minutes': _int(2, 60),
    'layouts.pages': _list(lambda v: None if isinstance(v, str) and re.fullmatch(r'\w+', v) else 'must be a page name (letters only)', 1),
    'layouts.keep': _int(1, 500),
    'news.feeds': _map(_url, key=lambda k: None if re.fullmatch(r'[a-z]+', k) else 'must be lower-case letters'), 'news.max_items': _int(1, 200),
    'links': _links,
    'network.names': _map(_pair, key=lambda k: None if re.fullmatch(r'\d{1,3}', k) else 'must be the last number of an IP address, e.g. "30"'),
    'network.mac_names': _map(_str, key=_mac),
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
    for key, check in SPEC.items():
        v = _get(tree, key)
        if v is KeyError:
            if not getattr(check, 'optional', False):
                errs.append(f'{key}: missing')
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


def _derive(t):
    """The validated file -> the constants the modules use (one place, so the modules never parse the file)."""
    host, _, port = t['services']['pc'].rpartition(':')      # no PC: ('', 0), which addons.py reads as "not here"
    p, e, pr = t['presence'], t['entities'], t['players']
    return SimpleNamespace(
        PORT=t['server']['port'], STATIC=t['server']['static_dir'], NETAUDIO=t['server']['netaudio'],
        LOCAL_TZ=zoneinfo.ZoneInfo(t['server']['timezone']),
        HA=t['homeassistant']['url'].rstrip('/'),
        PC=(host, int(port or 0)), PC_PROXY_CLIENTS=set(t['services']['pc_proxy_clients']),
        LABPANEL=t['services']['labpanel'].rstrip('/'), LAB_PANEL_ID=t['services']['lab_panel_id'],
        BUTTONS_PANEL=(t['services'].get('buttons_panel') or ''),
        PROM=t['services']['prometheus'].rstrip('/'), CAMFEED=t['services']['camfeed'].rstrip('/'), OLLAMA=t['services']['ollama'].rstrip('/'),
        NTFY=t['services']['ntfy'].rstrip('/'), PIHOLES=list(t['services']['piholes']),
        SPOTIFY=e['spotify'], LOCK=e['lock'], CHARGER=e['charger'], CHARGER_HINT=e['charger_power_prefix'],
        CAM_DETECT=e['cam_detect'], WAKE_PC=e['wake_pc'], TV=e['tv'], VACUUM=e['vacuum'], WEATHER=e['weather'],
        APPLE_TV=e['apple_tv'], APPLE_TV_REMOTE=e['apple_tv_remote'], ATV_COMMANDS=set(t['apple_tv']['commands']),
        PLAYERS=[(x['entity'], x['label']) for x in pr], PLAYER_IDS={x['entity'] for x in pr},
        PEOPLE_HIDE=set(t.get('people', {}).get('hide') or []),
        PC_ACTIONS=dict(t['pc_actions']),
        ROOM_ORDER=list(t['rooms']['order']), SKIP_LIGHTS=re.compile(t['rooms']['skip_lights']),
        ROOM_OF={k: tuple(v) for k, v in t['rooms']['names'].items()},
        PHONES={k: list(v) for k, v in p['phones'].items()}, AWAY_AFTER=dict(p['away_after_s']),
        DEFAULT_AWAY_AFTER=p['default_away_after_s'], NIGHT=tuple(p['night_hours']), NIGHT_LIMIT=p['night_limit_s'],
        PROBE_AFTER=p['probe_after_s'], PROBE_TRUST_S=p['probe_trust_s'], CAM_BURST_S=p['cam_burst_s'],
        CAM_LEAVE_SILENT=p['cam_leave_silent_s'], CAM_LEAVE_PEOPLE=set(p['cam_leave_people']), CAM_LEAVE_AFTER=p['cam_leave_after_s'],
        GENELECS=list(t['audio']['genelecs']), FRONT_PAIR=list(t['audio']['front_pair']),
        SOURCES={k: (v['device'], list(v['channels'])) for k, v in t['audio']['sources'].items()},
        BUS_STOP=t['transit']['bus_stop'], BUS_FEED=t['transit']['feed'], STOP_SEARCH=t['transit']['stop_search'],
        LEAVE_GRACE=t['leave']['grace_s'], LOCK_CHECK_S=t['leave']['lock_check_s'],
        REMOTE_EDGE=set(t['remote']['edge']), REMOTE_URL=t['remote']['public_url'].rstrip('/'), PAIR_MINUTES=t['remote']['pair_minutes'],
        ADMIN_PAGES=set(t['admin']['pages']), ADMIN_PIN_MIN=t['admin']['pin_min_digits'], ADMIN_SESSION_HOURS=t['admin']['session_hours'],
        ADMIN_REMEMBER_DAYS=t['admin']['remember_days'], ADMIN_MAX_TRIES=t['admin']['max_tries'], ADMIN_LOCK_MINUTES=t['admin']['lock_minutes'],
        LAYOUT_PAGES=set(t['layouts']['pages']), LAYOUT_KEEP=t['layouts']['keep'],
        NEWS_FEEDS=dict(t['news']['feeds']), NEWS_MAX=t['news']['max_items'],
        LINK_CHECKS={k: v for k, v in t['links'].items() if k != 'extra'} | dict(t['links'].get('extra') or {}),
        LINK_EXTRA=set(t['links'].get('extra') or {}),
        NET_NAMES={k: tuple(v) for k, v in t['network']['names'].items()},
        MAC_NAMES={k.lower(): v for k, v in t['network']['mac_names'].items()},
    )


def load():
    """-> (settings, report). report = {file, ok, problems, using}: what /api/health shows."""
    tree, errs = read(CONFIG_FILE)
    report = {'file': CONFIG_FILE, 'ok': not errs, 'problems': errs, 'using': CONFIG_FILE}
    if not errs:
        try:
            c = _derive(tree)
            if os.environ.get('HOMEDECK_READONLY') != '1':   # checks and test copies must not touch the service's files
                try:                                   # remember this one as the fallback for a later typo
                    shutil.copyfile(CONFIG_FILE, LAST_GOOD)
                except OSError:
                    pass
            return c, report
        except Exception as e:                         # a value that passed the checks but still cannot be used
            report.update(ok=False, problems=[f'{type(e).__name__}: {e}'])
    tree2, errs2 = read(LAST_GOOD)
    if tree2 is None or errs2:
        raise SystemExit('homedeck.toml has problems and there is no good copy to fall back to:\n  ' + '\n  '.join(errs))
    report['using'] = LAST_GOOD
    print('settings: homedeck.toml has problems, running on the last good copy:\n  ' + '\n  '.join(errs), flush=True)
    return _derive(tree2), report


# check.py reads and validates the file itself first (HOMEDECK_CHECKONLY=1), then imports normally
C, REPORT = (None, None) if os.environ.get('HOMEDECK_CHECKONLY') == '1' else load()
