"""What the house has, read from Home Assistant (refreshed every minute): which room each light is in (HA areas),
the people, the media players, the front door lock and the weather entity. homedeck.toml can override each part."""
import json, re, threading, time

from .config import C
from .ha import ha_states, ha_template

# area of every light, and the areas in Home Assistant's own order (area_name() also follows the device's area)
_AREA_TEMPLATE = ('{"areas": {{ areas() | map("area_name") | list | tojson }}, "lights": {'
                  '{% for s in states.light %}{{ s.entity_id | tojson }}: {{ (area_name(s.entity_id) or "") | tojson }}'
                  '{% if not loop.last %},{% endif %}{% endfor %}}}')
_cache = {'at': 0, 'areas': [], 'light_area': {}, 'error': None}
_lock = threading.Lock()


def areas():
    """-> (area names in HA order, {light entity: area name})"""
    with _lock:
        if time.time() - _cache['at'] > 60:
            try:
                d = json.loads(ha_template(_AREA_TEMPLATE))
                _cache.update(areas=d.get('areas') or [], light_area=d.get('lights') or {}, error=None)
            except Exception as e:                    # keep the last good answer; no areas at all -> names decide
                _cache['error'] = str(e)[:120]
            _cache['at'] = time.time()
        return _cache['areas'], _cache['light_area']


def short_name(friendly, room):
    """'Kitchen Ceiling' in room 'Kitchen' -> 'Ceiling'; 'Ceiling - Kitchen' -> 'Ceiling'."""
    n = friendly.strip()
    if room and n.lower().startswith(room.lower() + ' ') and len(n) > len(room) + 1:
        n = n[len(room):].strip(' -–·:')
        n = n[:1].upper() + n[1:]
    if ' - ' in n and room and n.rsplit(' - ', 1)[1].strip().lower() == room.lower():
        n = n.rsplit(' - ', 1)[0].strip()
    return n or friendly


def by_id(states=None):
    return {s['entity_id']: s for s in (states if states is not None else ha_states() or [])}


def lock_entity(states):
    if C.LOCK:
        return C.LOCK
    locks = [s for s in states if s['entity_id'].startswith('lock.') and s['state'] not in ('unavailable', 'unknown')]
    return locks[0]['entity_id'] if locks else ''


def weather_entity(states):
    if C.WEATHER:
        return C.WEATHER
    ids = [s['entity_id'] for s in states if s['entity_id'].startswith('weather.')]
    return 'weather.forecast_home' if 'weather.forecast_home' in ids else (ids[0] if ids else '')


def players(states):
    """[(entity, label)]: homedeck.toml [players] list if set, else every media player HA has (Spotify first)."""
    if C.PLAYERS_FIXED:
        return C.PLAYERS_FIXED
    out = [(s['entity_id'], s['attributes'].get('friendly_name') or s['entity_id'][13:]) for s in states
           if s['entity_id'].startswith('media_player.') and s['entity_id'] not in C.HIDE_PLAYERS and s['state'] != 'unavailable'
           and not s['attributes'].get('entity_id')]                       # skip groups
    return sorted(out, key=lambda p: (not p[0].startswith('media_player.spotify'), p[1].lower()))


def spotify(states):
    p = [e for e, _ in players(states) if e.startswith('media_player.spotify')]
    return p[0] if p else ''


def people(states):
    return [s for s in states if s['entity_id'].startswith('person.') and s['entity_id'] not in C.HIDE_PEOPLE]
