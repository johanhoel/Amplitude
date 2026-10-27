"""Last one home: the banner on Family info, and the "nobody home, door not locked" notice (people from Home
Assistant). Timers and on/off: [leave] in homedeck.toml."""
import time

from .config import C
from .home import home_state
from .notify import ntfy


def lights_on_names(hs):
    return [f"{l['name']} ({r['room']})" for r in hs.get('rooms', []) for l in r['lights'] if l['on']]


def leave_state(client_ip):
    hs = home_state()
    if not hs.get('configured'):
        return {'configured': False}
    home = [p['name'] for p in hs['people'] if p['home']]
    return {'configured': True, 'viewer': None, 'home': home, 'last': home[0] if len(home) == 1 else None,
            'lights_on': lights_on_names(hs), 'door': hs['door']['state']}


def leave_watch_loop():
    away_since, told = None, False
    while True:
        try:
            hs = home_state() if C.LEAVE_ON else {}
            if hs.get('configured') and hs['people']:
                if any(p['home'] for p in hs['people']):
                    away_since, told = None, False
                else:
                    away_since = away_since or time.time()
                    if not told and time.time() - away_since >= C.LEAVE_GRACE:
                        told = True
                        door, lights = hs['door']['state'], lights_on_names(hs)
                        if door and door != 'locked':
                            extra = f"\nLights still on: {', '.join(lights)}." if lights else ''
                            ntfy('Nobody home, front door not locked', f'Everyone has left and the front door is {door}.{extra}\n'
                                 'Lock it from the Home Assistant app or the lock app.')
        except Exception as e:
            print('leave watch:', e, flush=True)
        time.sleep(30)
