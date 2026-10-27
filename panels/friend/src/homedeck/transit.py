"""Buses for Family info: Västtrafik's public departure board feed (the one avgangstavla.vasttrafik.se uses, no key).
No stop is set at first: pick one in the Family info editor (saved in its layout) or set [transit] bus_stop."""
import json, re, threading, time, urllib.parse, urllib.request

from .config import C
from .layouts import layout_get

_bus = {'at': 0, 'data': None}
_bus_lock = threading.Lock()


def bus_stop():
    gid = str((layout_get('familyinfo').get('stop') or {}).get('gid') or '')
    return gid if re.fullmatch(r'\d{16}', gid) else C.BUS_STOP


def bus_snapshot():
    """Opens the feed (server-sent events), keeps the first full set of each kind, then hangs up."""
    want = {'departureRowsSet', 'arrivalRowsSet', 'trafficSituationsSet'}
    got, event, deadline = {}, None, time.time() + 10
    req = urllib.request.Request(C.BUS_FEED.format(g=bus_stop()), headers={'Accept': 'text/event-stream', 'User-Agent': 'home-deck'})
    with urllib.request.urlopen(req, timeout=10) as r:
        for raw in r:
            line = raw.decode('utf-8', 'replace').rstrip('\r\n')
            if line.startswith('event:'):
                event = line[6:].strip()
            elif line.startswith('data:') and event:
                if event in want or event == 'stopHeaderSet' or event.endswith('Error'):
                    got.setdefault(event, json.loads(line[5:]) if line[5:].strip().startswith(('{', '[')) else line[5:].strip())
            if want <= got.keys() or time.time() > deadline:
                break
    t = lambda x: (x or {}).get('time')
    deps = [{'line': d['line'], 'mode': d.get('transportMode'), 'to': d['destination']['name'], 'via': d['destination'].get('via'),
             'platform': d.get('platform'), 'next': d.get('next'), 'then': d.get('thereafter')}
            for d in (got.get('departureRowsSet') or {}).get('set', [])]
    arrs = [{'line': a['line'], 'mode': a.get('transportMode'), 'from': a.get('origin'), 'platform': a.get('platform'),
             'time': t(a.get('next')), 'planned': (a.get('next') or {}).get('targetTime'), 'cancelled': (a.get('next') or {}).get('isCancelled')}
            for a in (got.get('arrivalRowsSet') or {}).get('set', [])]
    sits = [{'title': x.get('title'), 'text': x.get('description'), 'severity': x.get('severity'),
             'lines': [l.get('shortName') for l in x.get('affectedLines', [])]}
            for x in (got.get('trafficSituationsSet') or {}).get('set', [])]
    name = ((got.get('stopHeaderSet') or {}).get('set') or {}).get('stopAreaName')
    errors = [k for k in got if k.endswith('Error')]
    return {'stop': name, 'departures': deps, 'arrivals': sorted(arrs, key=lambda a: a['time'] or ''), 'situations': sits,
            'errors': errors, 'complete': want <= got.keys(), 'fetched': time.time()}


def bus_state():
    if not bus_stop():
        return {'configured': False, 'stop': None, 'departures': [], 'arrivals': [], 'situations': [], 'errors': [], 'complete': True}
    with _bus_lock:
        if _bus.get('stop') != bus_stop():                   # stop changed in the editor: start over
            _bus.update(data=None, at=0, stop=bus_stop())
        if _bus['data'] is None or time.time() - _bus['at'] > 20:
            try:
                _bus['data'], _bus['at'] = bus_snapshot(), time.time()
            except Exception as e:
                if _bus['data'] is None:
                    raise
                _bus['data'] = {**_bus['data'], 'stale': str(e)[:120]}   # keep showing the last good board
                _bus['at'] = time.time() - 10                              # retry sooner
        return _bus['data']


def stop_search(q):
    url = C.STOP_SEARCH + '?search=' + urllib.parse.quote(q[:60])
    with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'home-deck'}), timeout=8) as r:
        return [{'gid': x.get('gid'), 'name': x.get('name'), 'municipality': x.get('municipality')} for x in json.load(r)][:15]
