"""The house from Home Assistant: rooms + lights, door, people, players, vacuum, weather, and the allowed actions.

Rooms come from Home Assistant's areas (Settings -> Areas); a light without an area goes under "Other".
homedeck.toml can rename lights / move them to a room ([rooms] names), hide rooms, people or players, and fix the
order. Actions are a fixed list (home_do): the door can be locked from a panel, never unlocked.
"""
import re, threading, time

from . import discover
from .config import C
from .ha import ha_call, ha_get, ha_states, invalidate
from .notify import ntfy


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def player(st, e, label):
    a = st.get('attributes', {})
    return {'id': e, 'label': label, 'state': st.get('state', 'unavailable'), 'title': a.get('media_title'), 'artist': a.get('media_artist'),
            'album': a.get('media_album_name'), 'volume': a.get('volume_level'), 'muted': a.get('is_volume_muted'),
            'duration': a.get('media_duration'), 'position': a.get('media_position'), 'position_at': a.get('media_position_updated_at'),
            'source': a.get('source'), 'app': a.get('app_name'), 'art': bool(a.get('entity_picture')), 'art_key': (a.get('entity_picture') or '')[-24:]}


def rooms_from(states):
    area_order, light_area = discover.areas()
    rooms = {}
    for s in states:
        e, a = s['entity_id'], s['attributes']
        if not e.startswith('light.') or C.SKIP_LIGHTS.search(e) or s['state'] == 'unavailable' or a.get('entity_id'):
            continue                                          # groups are skipped: their members are listed
        if e in C.ROOM_OF:
            short, room = C.ROOM_OF[e]
        else:
            room = light_area.get(e) or 'Other'
            short = discover.short_name(a.get('friendly_name', e), room)
        if room in C.HIDE_ROOMS:
            continue
        b = a.get('brightness')
        modes = a.get('supported_color_modes') or []
        rooms.setdefault(room, []).append({'id': e, 'name': short, 'on': s['state'] == 'on',
                                           'bri': round(b / 2.55) if b is not None else None,
                                           'dim': 'brightness' in modes or any(m != 'onoff' for m in modes)})
    order = C.ROOM_ORDER or area_order
    key = lambda r: (order.index(r) if r in order else (900 if r == 'Other' else 50), r)
    return [{'room': r, 'lights': sorted(rooms[r], key=lambda l: l['name'].lower())} for r in sorted(rooms, key=key)]


def home_state():
    states = ha_states()
    if states is None:
        return {'configured': False}
    by = discover.by_id(states)
    lock_id = discover.lock_entity(states)
    vac = next((s for s in states if s['entity_id'].startswith('vacuum.') and s['state'] != 'unavailable'), {})
    wx = by.get(discover.weather_entity(states), {})
    rooms = rooms_from(states)
    people = [{'name': s['attributes'].get('friendly_name', s['entity_id'][7:]), 'home': s['state'] == 'home',
               'id': s['entity_id'], 'pic': bool(s['attributes'].get('entity_picture'))}
              for s in discover.people(states) if s['state'] not in ('unknown', 'unavailable')]
    summ = ha_summary_from(states)
    return {'configured': True, 'rooms': rooms,
            'door': {'id': lock_id, 'state': by.get(lock_id, {}).get('state') if lock_id else None}, 'people': people,
            'vacuum': {'id': vac.get('entity_id'), 'state': vac.get('state'), 'battery': (vac.get('attributes') or {}).get('battery_level')},
            'detect': False, 'charger_on': False, 'tv': None,
            'wx': {k: (wx.get('attributes', {}) or {}).get(k) for k in ('temperature', 'humidity', 'wind_speed', 'wind_bearing', 'cloud_coverage', 'uv_index')}
                  | {'condition': wx.get('state'), 'wind_speed_unit': (wx.get('attributes', {}) or {}).get('wind_speed_unit')},
            'sun': {k: by.get('sun.sun', {}).get('attributes', {}).get(k) for k in ('next_rising', 'next_setting', 'elevation')}
                   | {'state': by.get('sun.sun', {}).get('state')},
            'players': [player(by.get(e, {}), e, label) for e, label in discover.players(states)],
            'appletv': {'id': None, 'state': 'unavailable', 'apps': []},
            **{k: summ[k] for k in ('outside', 'weather', 'temps', 'media', 'charger_w', 'charger_unit', 'lights_on')}}


def lock_check(ent):
    """A panel pressed Lock: if the door still is not locked after lock_check_s, send a home notice."""
    time.sleep(C.LOCK_CHECK_S)
    try:
        st = ha_get('/api/states/' + ent).get('state')
    except Exception as e:
        st = 'unknown (' + str(e)[:40] + ')'
    if st != 'locked':
        ntfy('Front door did not lock', f'Lock was pressed on a panel {C.LOCK_CHECK_S} s ago, the door now says: {st}. Check the door.')


def home_do(req):
    act, e, v = req.get('do'), req.get('entity') or '', req.get('value')
    states = ha_states(0) or []
    if act == 'toggle' and re.fullmatch(r'light\.\w+', e):
        ha_call('light', 'toggle', {'entity_id': e})
    elif act == 'bri' and re.fullmatch(r'light\.\w+', e):
        ha_call('light', 'turn_on', {'entity_id': e, 'brightness_pct': max(1, min(100, int(v)))})
    elif act == 'room_off':
        room = next((r for r in rooms_from(states) if r['room'] == e), None)
        if not room:
            raise ValueError('unknown room')
        ha_call('light', 'turn_off', {'entity_id': [l['id'] for l in room['lights'] if l['on']] or [room['lights'][0]['id']]})
    elif act == 'lock':                                       # lock only: unlocking stays in the HA / lock app
        ent = discover.lock_entity(states)
        if not ent:
            raise ValueError('no door lock in Home Assistant')
        ha_call('lock', 'lock', {'entity_id': ent})
        threading.Thread(target=lock_check, args=(ent,), daemon=True).start()
    elif act == 'all_off':                                    # "last one home": every light that is on
        on = [l['id'] for r in rooms_from(states) for l in r['lights'] if l['on']]
        if on:
            ha_call('light', 'turn_off', {'entity_id': on})
    elif act == 'vacuum' and v in ('start', 'return_to_base'):
        vac = next((s['entity_id'] for s in states if s['entity_id'].startswith('vacuum.')), None)
        if not vac:
            raise ValueError('no vacuum in Home Assistant')
        ha_call('vacuum', v, {'entity_id': vac})
    elif act == 'mp' and e in {p for p, _ in discover.players(states)} and v in (
            'media_play_pause', 'media_next_track', 'media_previous_track', 'volume_up', 'volume_down', 'volume_set'):
        data = {'entity_id': e}
        if v == 'volume_set':
            data['volume_level'] = max(0.0, min(1.0, float(req.get('level', 0.3))))
        ha_call('media_player', v, data)
    elif act == 'media' and v in ('media_play_pause', 'media_next_track', 'media_previous_track'):
        sp = discover.spotify(states)
        if not sp:
            raise ValueError('no Spotify player in Home Assistant')
        ha_call('media_player', v, {'entity_id': sp})
    else:
        raise ValueError('not allowed')
    invalidate()


def ha_summary():
    states = ha_states(4)
    if states is None:
        return {'configured': False}
    return ha_summary_from(states)


def ha_summary_from(states):
    by = discover.by_id(states)
    lights = [s for s in states if s['entity_id'].startswith('light.') and 'entity_id' not in s['attributes']]
    temps = [{'id': s['entity_id'], 'name': s['attributes'].get('friendly_name', s['entity_id']), 'value': num(s['state'])}
             for s in states if s['entity_id'].startswith('sensor.')
             and s['attributes'].get('device_class') == 'temperature' and num(s['state']) is not None]
    weather = by.get(discover.weather_entity(states))
    sp = by.get(discover.spotify(states), {})
    a = sp.get('attributes', {})
    lock_id = discover.lock_entity(states)
    return {
        'configured': True,
        'lights_on': sum(1 for s in lights if s['state'] == 'on'),
        'lights_total': sum(1 for s in lights if s['state'] in ('on', 'off')),
        'door': by.get(lock_id, {}).get('state') if lock_id else None,
        'temps': temps,
        'outside': num(weather['attributes'].get('temperature')) if weather else None,
        'weather': weather['state'] if weather else None,
        'charger_w': None, 'charger_unit': None,
        'media': {'state': sp.get('state'), 'title': a.get('media_title'), 'artist': a.get('media_artist'),
                  'art': bool(a.get('entity_picture')), 'art_key': a.get('entity_picture', '')[-24:]},
    }
