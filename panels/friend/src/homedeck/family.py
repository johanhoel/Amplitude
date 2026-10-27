"""Family panel (and Ambient, Desktop): who is home now, since when, and today's home/away timeline, from Home
Assistant's people (person.*) and their history. People to hide: [people] hide in homedeck.toml."""
import datetime, time

from . import discover
from .config import C
from .ha import ha_history, ha_states

_family = {'at': 0, 'data': None}


def _ts(iso):
    return datetime.datetime.fromisoformat(iso.replace('Z', '+00:00')).timestamp()


def family_state():
    if time.time() - _family['at'] < 20 and _family['data']:
        return _family['data']
    now = time.time()
    midnight = datetime.datetime.now(C.LOCAL_TZ).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    start = min(midnight, now - 6 * 3600)
    states = ha_states() or []
    persons = [s for s in discover.people(states)]
    hist = {}
    if persons:
        start_iso = datetime.datetime.fromtimestamp(start, datetime.timezone.utc).isoformat()
        for series in ha_history([p['entity_id'] for p in persons], start_iso):
            if series:
                hist[series[0]['entity_id']] = series
    people = []
    for s in persons:
        segs = []
        for h in hist.get(s['entity_id'], []):
            st = h.get('state')
            if st in ('unknown', 'unavailable'):
                continue
            t = max(start, _ts(h.get('last_changed') or h.get('last_updated')))
            home = st == 'home'
            if segs and segs[-1]['home'] == home:
                continue
            if segs:
                segs[-1]['to'] = t
            segs.append({'home': home, 'from': t, 'to': now})
        if not segs:
            segs = [{'home': s['state'] == 'home', 'from': start, 'to': now}]
        last_change = segs[-1]['from']
        people.append({'name': s['attributes'].get('friendly_name', s['entity_id'][7:]), 'home': s['state'] == 'home',
                       'silent_s': None, 'since': last_change if last_change > start + 1 else None, 'segments': segs,
                       'lookups_today': 0, 'fun_today': 0, 'hourly': []})
    data = {'now': now, 'midnight': midnight, 'start': start, 'people': people, 'camera': []}
    _family.update(at=time.time(), data=data)
    return data


def presence_summary():
    """GET /api/presence (Desktop): person id -> home / seconds since the last change."""
    d = family_state()
    return {p['name'].lower(): {'home': p['home'], 'devices': [], 'silent_s': round(d['now'] - p['since']) if p['since'] else None}
            for p in d['people']}
