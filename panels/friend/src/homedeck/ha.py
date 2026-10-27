"""Home Assistant REST calls (token from secrets.json, set on the /setup page) and a short cache of all states."""
import json, time, urllib.request

from .config import C
from .store import NOCHECK, secret


def _req(path, data=None):
    tok = secret('ha_token')
    if not tok:
        raise PermissionError('no Home Assistant token yet: open /setup')
    return urllib.request.Request(C.HA + path, method='POST' if data is not None else 'GET',
                                  data=json.dumps(data).encode() if data is not None else None,
                                  headers={'Authorization': 'Bearer ' + tok, 'Content-Type': 'application/json'})


def ha_get(path, raw=False):
    if not secret('ha_token'):
        return None
    with urllib.request.urlopen(_req(path), context=NOCHECK, timeout=6) as r:
        return r.read() if raw else json.load(r)


def ha_call(domain, service, data):
    urllib.request.urlopen(_req(f'/api/services/{domain}/{service}', data), context=NOCHECK, timeout=6).read()


def ha_template(template):
    """Render a Jinja template in Home Assistant (used for rooms: area of every light)."""
    with urllib.request.urlopen(_req('/api/template', {'template': template}), context=NOCHECK, timeout=10) as r:
        return r.read().decode()


def ha_forecast(entity, kind):
    with urllib.request.urlopen(_req('/api/services/weather/get_forecasts?return_response', {'entity_id': entity, 'type': kind}),
                                context=NOCHECK, timeout=8) as r:
        return json.load(r)['service_response'][entity]['forecast']


def ha_history(entities, start_iso):
    q = f'/api/history/period/{start_iso}?filter_entity_id={",".join(entities)}&minimal_response&no_attributes'
    return ha_get(q) or []


_states = {'at': 0, 'data': None}


def ha_states(max_age=1.5):
    if time.time() - _states['at'] > max_age:
        _states['data'], _states['at'] = ha_get('/api/states'), time.time()
    return _states['data']


def invalidate():
    """After an action: the next state read is fresh."""
    _states['at'] = 0
