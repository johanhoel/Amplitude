"""Last one home: the banner on Family info, and the "nobody home, door not locked" notice.

Timers: [leave] in homedeck.toml. The viewer is recognised by the request's LAN address (presence.ip_person).
"""
import time

from .config import C
from .home import home_state
from .notify import ntfy
from .presence import ip_person, presence


def lights_on_names(hs):
    return [f"{l['name']} ({r['room']})" if l['name'] != 'All' else r['room'] for r in hs.get('rooms', []) for l in r['lights'] if l['on']]


def leave_state(client_ip):
    hs = home_state()
    if not hs.get('configured'):
        return {'configured': False}
    home = [p['name'] for p in hs['people'] if p['home']]
    viewer = ip_person.get(client_ip)
    return {'configured': True, 'viewer': viewer.capitalize() if viewer else None, 'home': home,
            'last': home[0] if len(home) == 1 else None, 'lights_on': lights_on_names(hs), 'door': hs['door']['state']}


def leave_watch_loop():
    away_since, told = None, False
    while True:
        try:
            hs = home_state()
            if hs.get('configured') and presence and all(p.get('home') is not None for p in presence.values()):
                anyone = any(p['home'] for p in hs['people'])
                if anyone:
                    away_since, told = None, False
                else:
                    away_since = away_since or time.time()
                    if not told and time.time() - away_since >= C.LEAVE_GRACE:
                        told = True
                        door, lights = hs['door']['state'], lights_on_names(hs)
                        if door != 'locked':
                            extra = f"\nLights still on: {', '.join(lights)}." if lights else ''
                            ntfy('Nobody home, front door not locked', f'Everyone has left and the front door is {door}.{extra}\n'
                                 'Lock it from the Home Assistant app or the lock app.')
        except Exception as e:
            print('leave watch:', e, flush=True)
        time.sleep(30)
