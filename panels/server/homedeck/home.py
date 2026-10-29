"""The house from Home Assistant: rooms + lights, door, people, vacuum, players, Apple TV, and the allowed actions.

Entities and lists: [entities], [[players]], [rooms], [apple_tv] in homedeck.toml. Actions are a fixed list
(home_do); the door can be locked from a panel, never unlocked.
"""
import re, threading, time

from .config import C
from .ha import ha_call, ha_get, ha_states, ha_vacuum_rooms, invalidate
from .notify import ntfy
from .presence import presence
from .weather import entity as weather_entity


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


def lock_entity(by):
    """The front door has two lock entities in HA (lock.front_door and a re-added lock.front_door_2); use the one that works."""
    for e in (C.LOCK, C.LOCK + '_2'):
        if by.get(e, {}).get('state') not in (None, 'unavailable', 'unknown'):
            return e
    return C.LOCK


_vac = {'at': 0, 'rooms': [], 'busy': False}


def vac_rooms():
    """The vacuum's rooms (segment id + name), read from its map once an hour in the background; the last good list is kept."""
    if time.time() - _vac['at'] > 3600 and not _vac['busy']:
        _vac['busy'] = True
        def load():
            try:
                _vac['rooms'] = [{'id': i, 'name': n} for i, n in ha_vacuum_rooms(C.VACUUM)]
                _vac['at'] = time.time()
            except Exception as e:
                print('vacuum rooms:', e, flush=True); _vac['at'] = time.time() - 3300   # try again in 5 min
            finally:
                _vac['busy'] = False
        threading.Thread(target=load, daemon=True).start()
    return _vac['rooms']


def home_state():
    states = ha_states()
    if states is None:
        return {'configured': False}
    by = {s['entity_id']: s for s in states}
    rooms = {}
    for s in states:
        e, a = s['entity_id'], s['attributes']
        if not e.startswith('light.') or C.SKIP_LIGHTS.search(e) or s['state'] == 'unavailable':
            continue
        name = a.get('friendly_name', e)
        if e in C.ROOM_OF:
            short, room = C.ROOM_OF[e]
        elif 'entity_id' in a:                                # a group: show it under its own name
            room, short = name.replace('Belysning ', '').strip().capitalize(), 'All'
        elif ' - ' in name:
            short, room = [x.strip() for x in name.rsplit(' - ', 1)]
        else:
            short, room = name, 'Other'
        b = a.get('brightness')
        rooms.setdefault(room, []).append({'id': e, 'name': short, 'on': s['state'] == 'on',
                                           'bri': round(b / 2.55) if b is not None else None,
                                           'dim': 'brightness' in (a.get('supported_color_modes') or []) or
                                                  any(m != 'onoff' for m in (a.get('supported_color_modes') or []))})
    order = lambda r: (C.ROOM_ORDER.index(r) if r in C.ROOM_ORDER else 50, r)
    # Home/away follows the Wi-Fi presence (phones): a phone the Pi-holes have not seen recently = away, even when
    # HA's person still says home from an old companion-app GPS fix. People without a tracked phone keep HA's state.
    def at_home(s):
        p = presence.get(s['entity_id'][7:])
        return bool(p.get('home')) if p and p.get('home') is not None else s['state'] == 'home'
    people = [{'name': s['attributes'].get('friendly_name', s['entity_id'][7:]).capitalize(), 'home': at_home(s),
               'pic': bool(s['attributes'].get('entity_picture'))}
              for s in states if s['entity_id'].startswith('person.') and s['entity_id'] not in C.PEOPLE_HIDE
              and s['state'] not in ('unknown', 'unavailable')]
    lock_ = by.get(lock_entity(by), {})
    vac = by.get(C.VACUUM, {})
    det = by.get(C.CAM_DETECT, {})
    summ = ha_summary_from(states)
    wx = by.get(weather_entity(), {})
    return {'configured': True, 'rooms': [{'room': r, 'lights': sorted(rooms[r], key=lambda l: l['name'])}
                                          for r in sorted(rooms, key=order)],
            'door': {'id': lock_.get('entity_id', C.LOCK), 'state': lock_.get('state')}, 'people': people,
            'vacuum': {'state': vac.get('state'), 'battery': vac.get('attributes', {}).get('battery_level'), 'rooms': vac_rooms()},
            'detect': det.get('state') == 'on', 'charger_on': by.get(C.CHARGER, {}).get('state') == 'on',
            'tv': by.get(C.TV, {}).get('state'),
            'wx': {k: (wx.get('attributes', {}) or {}).get(k) for k in ('temperature', 'humidity', 'wind_speed', 'wind_bearing', 'cloud_coverage', 'uv_index')}
                  | {'condition': wx.get('state')},
            'sun': {k: by.get('sun.sun', {}).get('attributes', {}).get(k) for k in ('next_rising', 'next_setting', 'elevation')}
                   | {'state': by.get('sun.sun', {}).get('state')},
            'players': [player(by.get(e, {}), e, label) for e, label in C.PLAYERS],
            'appletv': {**player(by.get(C.APPLE_TV, {}), C.APPLE_TV, 'Living room · Apple TV'),
                        'apps': by.get(C.APPLE_TV, {}).get('attributes', {}).get('source_list') or []},
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
    if act == 'toggle' and re.fullmatch(r'light\.\w+', e):
        ha_call('light', 'toggle', {'entity_id': e})
    elif act == 'bri' and re.fullmatch(r'light\.\w+', e):
        ha_call('light', 'turn_on', {'entity_id': e, 'brightness_pct': max(1, min(100, int(v)))})
    elif act == 'room_off':
        room = next((r for r in home_state().get('rooms', []) if r['room'] == e), None)
        if not room:
            raise ValueError('unknown room')
        ha_call('light', 'turn_off', {'entity_id': [l['id'] for l in room['lights'] if l['on']] or [room['lights'][0]['id']]})
    elif act == 'lock':                                       # lock only: unlocking stays in the HA / lock app
        ent = lock_entity({s['entity_id']: s for s in ha_states(0)})
        ha_call('lock', 'lock', {'entity_id': ent})
        threading.Thread(target=lock_check, args=(ent,), daemon=True).start()
    elif act == 'all_off':                                    # "last one home": every light that is on
        on = [l['id'] for r in home_state().get('rooms', []) for l in r['lights'] if l['on']]
        if on:
            ha_call('light', 'turn_off', {'entity_id': on})
    elif act == 'vacuum' and v in ('start', 'return_to_base'):
        ha_call('vacuum', v, {'entity_id': C.VACUUM})
    elif act == 'vacuum_rooms':                               # clean only these rooms (segment ids from the vacuum's map)
        known = {r['id'] for r in vac_rooms()}
        ids = [int(x) for x in (v or []) if str(x).isdigit()]
        if not ids or not set(ids) <= known:
            raise ValueError('unknown room')
        ha_call('vacuum', 'send_command', {'entity_id': C.VACUUM, 'command': 'app_segment_clean', 'params': ids})
    elif act == 'detect':
        ha_call('input_boolean', 'toggle', {'entity_id': C.CAM_DETECT})
    elif act == 'charger':
        ha_call('switch', 'toggle', {'entity_id': C.CHARGER})
    elif act == 'wake_pc':
        ha_call('button', 'press', {'entity_id': C.WAKE_PC})
    elif act == 'tv':
        ha_call('media_player', 'media_play_pause', {'entity_id': C.TV})
    elif act == 'mp' and e in C.PLAYER_IDS and v in ('media_play_pause', 'media_next_track', 'media_previous_track', 'volume_up', 'volume_down', 'volume_set'):
        data = {'entity_id': e}
        if v == 'volume_set':
            data['volume_level'] = max(0.0, min(1.0, float(req.get('level', 0.3))))
        ha_call('media_player', v, data)
    elif act == 'atv' and v in C.ATV_COMMANDS:                # Apple TV remote buttons
        ha_call('remote', 'send_command', {'entity_id': C.APPLE_TV_REMOTE, 'command': v})
    elif act == 'atv_app':                                    # open an app (must be one the Apple TV lists)
        apps = (ha_get('/api/states/' + C.APPLE_TV).get('attributes', {}).get('source_list') or [])
        if v not in apps:
            raise ValueError('unknown app')
        ha_call('media_player', 'select_source', {'entity_id': C.APPLE_TV, 'source': v})
    elif act == 'atv_power' and v in ('turn_on', 'turn_off'):
        ha_call('media_player', v, {'entity_id': C.APPLE_TV})
    elif act == 'media' and v in ('media_play_pause', 'media_next_track', 'media_previous_track'):
        ha_call('media_player', v, {'entity_id': C.SPOTIFY})
    else:
        raise ValueError('not allowed')
    invalidate()


def ha_summary():
    states = ha_states(4)
    if states is None:
        return {'configured': False}
    return ha_summary_from(states)


def ha_summary_from(states):
    by = {s['entity_id']: s for s in states}
    lights = [s for s in states if s['entity_id'].startswith('light.') and 'entity_id' not in s['attributes']]
    temps = [{'id': s['entity_id'], 'name': s['attributes'].get('friendly_name', s['entity_id']),
              'value': num(s['state'])}
             for s in states if s['entity_id'].startswith('sensor.')
             and s['attributes'].get('device_class') == 'temperature' and num(s['state']) is not None]
    weather = next((s for s in states if s['entity_id'].startswith('weather.')), None)
    charger = next((s for s in states if s['entity_id'].startswith(C.CHARGER_HINT)
                    and s['attributes'].get('device_class') == 'power' and num(s['state']) is not None), None)
    sp = by.get(C.SPOTIFY, {})
    a = sp.get('attributes', {})
    return {
        'configured': True,
        'lights_on': sum(1 for s in lights if s['state'] == 'on'),
        'lights_total': sum(1 for s in lights if s['state'] in ('on', 'off')),
        'door': by.get(C.LOCK, {}).get('state'),
        'temps': temps,
        'outside': num(weather['attributes'].get('temperature')) if weather else None,
        'weather': weather['state'] if weather else None,
        'charger_w': num(charger['state']) if charger else None,
        'charger_unit': charger['attributes'].get('unit_of_measurement') if charger else None,
        'media': {'state': sp.get('state'), 'title': a.get('media_title'), 'artist': a.get('media_artist'),
                  'art': bool(a.get('entity_picture')), 'art_key': a.get('entity_picture', '')[-24:]},
    }
