"""Home Assistant REST calls (token from secrets.json) and a short cache of all states."""
import json, time, urllib.request

from .config import C
from .store import NOCHECK, secret


def ha_get(path, raw=False):
    tok = secret('ha_token')
    if not tok:
        return None
    req = urllib.request.Request(C.HA + path, headers={'Authorization': 'Bearer ' + tok})
    with urllib.request.urlopen(req, context=NOCHECK, timeout=5) as r:
        return r.read() if raw else json.load(r)


def ha_call(domain, service, data):
    tok = secret('ha_token')
    req = urllib.request.Request(f'{C.HA}/api/services/{domain}/{service}', method='POST',
                                 data=json.dumps(data).encode(),
                                 headers={'Authorization': 'Bearer ' + tok, 'Content-Type': 'application/json'})
    urllib.request.urlopen(req, context=NOCHECK, timeout=5).read()


def ha_forecast(kind, entity=None):
    entity = entity or C.WEATHER
    tok = secret('ha_token')
    req = urllib.request.Request(f'{C.HA}/api/services/weather/get_forecasts?return_response', method='POST',
                                 data=json.dumps({'entity_id': entity, 'type': kind}).encode(),
                                 headers={'Authorization': 'Bearer ' + tok, 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, context=NOCHECK, timeout=8) as r:
        return json.load(r)['service_response'][entity]['forecast']


def ha_vacuum_rooms(entity):
    """The rooms on the vacuum's map, from the Roborock integration: [(segment id, name), ...]."""
    tok = secret('ha_token')
    req = urllib.request.Request(f'{C.HA}/api/services/roborock/get_maps?return_response', method='POST',
                                 data=json.dumps({'entity_id': entity}).encode(),
                                 headers={'Authorization': 'Bearer ' + tok, 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, context=NOCHECK, timeout=15) as r:
        maps = json.load(r)['service_response'][entity]['maps']
    return [(int(k), v.strip()) for m in maps for k, v in (m.get('rooms') or {}).items()]


_states = {'at': 0, 'data': None}


def ha_states(max_age=1.5):
    if time.time() - _states['at'] > max_age:
        _states['data'], _states['at'] = ha_get('/api/states'), time.time()
    return _states['data']


def entities(domain):
    """[{id, name}] for one domain, sorted by name - what the edit-mode pickers list."""
    pre = domain + '.'
    out = [{'id': s['entity_id'], 'name': s.get('attributes', {}).get('friendly_name') or s['entity_id'][len(pre):]}
           for s in (ha_states(30) or []) if s['entity_id'].startswith(pre)]
    return sorted(out, key=lambda e: e['name'].lower())


def invalidate():
    """After an action: the next state read is fresh."""
    _states['at'] = 0
