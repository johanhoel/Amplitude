"""Home Deck Studio (/studio, admin): one list of every device, the registry of the ones you added, draft + apply, health watch.

Where devices come from (inventory): Home Assistant (lights, locks, sensors, players, cameras...), the network (both
Pi-holes: MAC, IP, name, vendor, last DNS query), Proxmox (guests from the lab panel service) and manual entries.
Home Assistant is only read: names, rooms and owners given here live in Home Deck ($STATE/studio/registry.json).

Changes are collected in a draft ($STATE/studio/draft.json) and applied together (POST /api/studio/apply). Every apply
keeps a copy of what it replaced (history/), so "Undo last apply" puts it back. A phone linked to a person for
presence is written to settings.json 'phones' (the override presence already reads), so nothing needs a restart.

Health watch: devices added with "watch" get an online dot; one that stays offline for [studio] watch_after_s sends a
home notice (ntfy), and another one when it is back.
"""
import json, os, re, threading, time, urllib.request

from .config import C, STATE
from .ha import ha_states
from .notify import ntfy
from .store import SETTINGS, load, phones, save

DIR = os.path.join(STATE, 'studio')
REG = os.path.join(DIR, 'registry.json')
DRAFT = os.path.join(DIR, 'draft.json')
HIST = os.path.join(DIR, 'history')
WATCH_AFTER = 600                                     # offline this long before a notice
NET_ONLINE = 900                                      # a network device with a DNS query this recent counts as online
_lock = threading.Lock()
_inv = {'at': 0, 'data': None}
_watch = {}                                           # key -> {'down_since', 'told'}

HA_KINDS = {'light': 'light', 'switch': 'switch', 'lock': 'lock', 'media_player': 'player', 'vacuum': 'vacuum', 'camera': 'camera',
            'climate': 'climate', 'cover': 'cover', 'fan': 'fan', 'person': 'person'}
SENSOR_CLASSES = {'temperature', 'humidity', 'power', 'energy', 'battery', 'door', 'window', 'motion', 'occupancy', 'moisture', 'smoke'}


def _read_json(url, timeout=6):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.load(r)


# ---------- inventory ----------
def _from_ha():
    out = []
    for s in ha_states(5) or []:
        e, a = s['entity_id'], s.get('attributes', {})
        dom = e.split('.', 1)[0]
        kind = HA_KINDS.get(dom)
        if dom in ('sensor', 'binary_sensor') and a.get('device_class') in SENSOR_CLASSES:
            kind = 'sensor'
        if not kind or a.get('entity_id'):           # groups list their members instead
            continue
        out.append({'key': 'ha:' + e, 'source': 'ha', 'kind': kind, 'name': a.get('friendly_name') or e, 'id': e,
                    'state': s.get('state'), 'online': s.get('state') not in ('unavailable', 'unknown'),
                    'detail': a.get('device_class') or dom, 'changed': s.get('last_changed')})
    return out


def _from_network():
    seen = {}
    for h in C.PIHOLES:
        try:
            devs = _read_json(f'http://{h}/api/network/devices?max_devices=400')['devices']
        except Exception:
            continue
        for d in devs:
            m = (d.get('hwaddr') or '').lower()
            if not re.fullmatch(r'[0-9a-f]{2}(:[0-9a-f]{2}){5}', m) or m == '00:00:00:00:00:00':
                continue
            x = seen.setdefault(m, {'ips': set(), 'names': set(), 'last': 0, 'first': d.get('firstSeen') or 0, 'vendor': d.get('macVendor') or ''})
            x['last'] = max(x['last'], d.get('lastQuery') or 0)
            for i in d.get('ips', []):
                if i.get('ip', '').startswith('192.168.') or i.get('ip', '').startswith('10.'):
                    x['ips'].add(i['ip'])
                if i.get('name'):
                    x['names'].add(i['name'].replace('.lan', ''))
    now, out = time.time(), []
    for m, x in seen.items():
        name = C.MAC_NAMES.get(m) or next(iter(sorted(x['names'])), '') or (x['vendor'].split(',')[0] if x['vendor'] else 'Unknown device')
        out.append({'key': 'net:' + m, 'source': 'net', 'kind': 'network', 'name': name, 'id': m, 'ips': sorted(x['ips']),
                    'vendor': x['vendor'], 'last': x['last'], 'first': x['first'], 'online': now - x['last'] < NET_ONLINE,
                    'detail': ', '.join(sorted(x['ips'])[:2]), 'private_mac': int(m[1], 16) & 2 == 2})
    return out


def _from_proxmox():
    try:
        snap = _read_json(f'{C.LABPANEL}/api/snapshot', 5)
    except Exception:
        return []
    return [{'key': f'pve:{g["vmid"]}', 'source': 'pve', 'kind': 'vm' if g.get('type') == 'qemu' else 'container', 'id': g['vmid'],
             'name': f'{g["vmid"]} {g.get("name", "")}', 'online': g.get('status') == 'running', 'state': g.get('status'),
             'detail': f'{g.get("node", "")} · {g.get("ip") or ""}'.strip(' ·')} for g in snap.get('guests', [])]


def inventory(max_age=20):
    """Every device from every source, with what the registry adds (name, room, owner, watch). Cached briefly."""
    with _lock:
        if _inv['data'] is not None and time.time() - _inv['at'] < max_age:
            items = _inv['data']
        else:
            items = []
            for fn in (_from_ha, _from_network, _from_proxmox):
                try:
                    items += fn()
                except Exception as e:
                    print('studio: inventory', fn.__name__, e, flush=True)
            _inv.update(at=time.time(), data=items)
    reg = load(REG, {})
    by_key = {i['key']: i for i in items}
    out = []
    for i in items:
        r = reg.get(i['key'])
        out.append({**i, 'added': bool(r), **({'reg': r} if r else {})})
    for k, r in reg.items():                          # manual devices, and added ones that are gone from their source
        if k not in by_key:
            out.append({'key': k, 'source': k.split(':', 1)[0], 'kind': r.get('kind', 'other'), 'name': r.get('name', k), 'id': k.split(':', 1)[1],
                        'online': None, 'detail': r.get('address', ''), 'added': True, 'reg': r, 'missing': not k.startswith('man:')})
    ph = phones()
    for i in out:
        if i['source'] == 'net':
            i['presence'] = next((p for p, macs in ph.items() if i['id'] in [m.lower() for m in macs]), None)
        w = _watch.get(i['key'])
        if w and w.get('down_since'):
            i['down_since'] = w['down_since']
    return out


def summary():
    items = inventory()
    reg = [i for i in items if i['added']]
    return {'counts': {s: sum(1 for i in items if i['source'] == s) for s in ('ha', 'net', 'pve', 'man')},
            'added': len(reg), 'watched': sum(1 for i in reg if i['reg'].get('watch')),
            'down': [{'key': i['key'], 'name': i['reg'].get('name') or i['name'], 'since': i.get('down_since')} for i in reg
                     if i['reg'].get('watch') and i.get('online') is False],
            'draft': len(load(DRAFT, [])), 'people': sorted(phones()), 'rooms': rooms()}


def rooms():
    reg = load(REG, {})
    names = {r.get('room') for r in reg.values() if r.get('room')}
    try:
        from . import home
        names |= {r['room'] for r in (home.rooms_from(ha_states(5) or []) if hasattr(home, 'rooms_from') else home.home_state().get('rooms', []))}
    except Exception:
        pass
    return sorted(n for n in names if n)


def watched():
    """GET /api/watched (no PIN; for the Device status card on boards): watched devices, name + online only."""
    out = []
    for i in inventory(max_age=50):
        r = i.get('reg') or {}
        if r.get('watch'):
            out.append({'key': i['key'], 'name': r.get('name') or i['name'], 'kind': r.get('kind') or i['kind'], 'room': r.get('room', ''),
                        'online': i.get('online'), 'down_since': i.get('down_since')})
    return sorted(out, key=lambda x: x['name'].lower())


# ---------- draft / apply / undo ----------
KINDS = ('light', 'switch', 'lock', 'player', 'vacuum', 'camera', 'climate', 'cover', 'fan', 'person', 'sensor', 'network', 'phone',
         'tablet', 'computer', 'tv', 'speaker', 'printer', 'iot', 'server', 'vm', 'container', 'other')


def _clean(c):
    """One change from the page -> a checked change, or ValueError."""
    op = c.get('op')
    key = str(c.get('key') or '')
    if op == 'manual':                                 # new manual device: key made here
        name = str(c.get('name') or '').strip()[:60]
        if not name:
            raise ValueError('a manual device needs a name')
        key = 'man:' + (re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')[:30] or 'device') + '-' + hex(int(time.time()))[-5:]
        op = 'add'
        c = {**c, 'address': str(c.get('address') or '').strip()[:120]}
    if not re.fullmatch(r'(ha|net|pve|man):[\w.:-]{1,80}', key):
        raise ValueError('bad device')
    if op in ('add', 'update'):
        f = {'name': str(c.get('name') or '').strip()[:60], 'room': str(c.get('room') or '').strip()[:40],
             'owner': str(c.get('owner') or '').strip()[:30], 'kind': c.get('kind') if c.get('kind') in KINDS else 'other',
             'watch': bool(c.get('watch')), 'notes': str(c.get('notes') or '').strip()[:300]}
        if c.get('address') is not None:
            f['address'] = str(c['address']).strip()[:120]
        return {'op': op, 'key': key, 'fields': f, 'label': c.get('label') or f['name'] or key}
    if op == 'remove':
        return {'op': op, 'key': key, 'label': c.get('label') or key}
    if op == 'presence':
        person = str(c.get('person') or '').strip().lower()
        if not re.fullmatch(r'[a-z][a-z0-9_-]{0,29}', person) or not key.startswith('net:'):
            raise ValueError('presence needs a person and a network device')
        return {'op': op, 'key': key, 'person': person, 'on': bool(c.get('on', True)), 'label': c.get('label') or key}
    raise ValueError('unknown change')


def draft_add(c):
    with _lock:
        d = load(DRAFT, [])
        ch = _clean(c)
        d = [x for x in d if not (x['key'] == ch['key'] and x['op'] == ch['op'] and x.get('person') == ch.get('person'))]   # newest wins
        d.append({**ch, 'at': time.time()})
        os.makedirs(DIR, exist_ok=True)
        save(DRAFT, d)
        return d


def draft_clear(index=None):
    with _lock:
        d = load(DRAFT, [])
        d = [] if index is None else [x for i, x in enumerate(d) if i != index]
        os.makedirs(DIR, exist_ok=True)
        save(DRAFT, d)
        return d


def apply():
    """Applies the whole draft. Keeps what it replaced (registry + phones) in history/ for undo."""
    with _lock:
        d = load(DRAFT, [])
        if not d:
            raise ValueError('nothing to apply')
        reg, settings = load(REG, {}), load(SETTINGS, {})
        ph = {p: [m.lower() for m in macs] for p, macs in phones().items()}
        os.makedirs(HIST, exist_ok=True)
        save(os.path.join(HIST, f'{int(time.time() * 1000)}.json'),
             {'registry': reg, 'phones': settings.get('phones'), 'changes': d, 'at': time.time()})
        for c in d:
            if c['op'] == 'add':
                reg[c['key']] = {**c['fields'], 'added': time.time()}
            elif c['op'] == 'update' and c['key'] in reg:
                reg[c['key']] = {**reg[c['key']], **c['fields']}
            elif c['op'] == 'remove':
                reg.pop(c['key'], None)
            elif c['op'] == 'presence':
                mac = c['key'][4:]
                for p in ph:
                    ph[p] = [m for m in ph[p] if m != mac]
                if c['on']:
                    ph.setdefault(c['person'], []).append(mac)
                ph = {p: macs for p, macs in ph.items() if macs or p in C.PHONES}
        save(REG, reg)
        if any(c['op'] == 'presence' for c in d):
            settings['phones'] = ph
            save(SETTINGS, settings)
        save(DRAFT, [])
        for old in sorted(os.listdir(HIST))[:-50]:
            os.remove(os.path.join(HIST, old))
        print(f'studio: applied {len(d)} change(s): ' + '; '.join(f'{c["op"]} {c["label"]}' for c in d), flush=True)
        return {'ok': True, 'applied': len(d)}


def history():
    out = []
    for f in sorted(os.listdir(HIST), reverse=True)[:20] if os.path.isdir(HIST) else []:
        h = load(os.path.join(HIST, f), {})
        out.append({'id': f[:-5], 'at': h.get('at'), 'changes': [f'{c["op"]} {c.get("label", c["key"])}' for c in h.get('changes', [])]})
    return out


def undo():
    """Puts back what the last apply replaced (registry + presence phones)."""
    with _lock:
        files = sorted(os.listdir(HIST)) if os.path.isdir(HIST) else []
        if not files:
            raise ValueError('nothing to undo')
        h = load(os.path.join(HIST, files[-1]), {})
        save(REG, h.get('registry') or {})
        settings = load(SETTINGS, {})
        if h.get('phones') is None:
            settings.pop('phones', None)
        else:
            settings['phones'] = h['phones']
        save(SETTINGS, settings)
        os.remove(os.path.join(HIST, files[-1]))
        print('studio: undid the last apply', flush=True)
        return {'ok': True}


# ---------- health watch ----------
def watch_loop():
    time.sleep(30)
    while True:
        try:
            now = time.time()
            for i in inventory(max_age=50):
                r = i.get('reg') or {}
                if not r.get('watch'):
                    _watch.pop(i['key'], None)
                    continue
                w = _watch.setdefault(i['key'], {'down_since': None, 'told': False})
                name = r.get('name') or i['name']
                if i.get('online') is False:
                    w['down_since'] = w['down_since'] or now
                    if not w['told'] and now - w['down_since'] > WATCH_AFTER:
                        w['told'] = True
                        ntfy(f'{name} is offline', f'{name} ({i.get("detail") or i["key"]}) has been offline for {int((now - w["down_since"]) / 60)} min.', tags='warning', priority='3')
                elif i.get('online'):
                    if w['told']:
                        ntfy(f'{name} is back', f'{name} is online again.', tags='white_check_mark', priority='2')
                    w.update(down_since=None, told=False)
        except Exception as e:
            print('studio: watch', e, flush=True)
        time.sleep(60)
