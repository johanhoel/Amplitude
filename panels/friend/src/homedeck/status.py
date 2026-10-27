"""Status for the pages (/api/status): Home Assistant summary refreshed in the background, plus internet."""
import threading, time

from .home import ha_summary
from .store import tcp_ms

lock = threading.Lock()
cache = {'ha': None, 'ha_at': 0}
OFF = {'configured': False}


def refresh_soon(*keys):
    with lock:
        for k in keys:
            if k + '_at' in cache:
                cache[k + '_at'] = 0


def refresher():
    while True:
        if time.time() - cache['ha_at'] >= 8:
            try:
                val = ha_summary()
            except Exception as e:
                val = {'configured': True, 'error': str(e)[:120]}
            with lock:
                cache['ha'], cache['ha_at'] = val, time.time()
        time.sleep(2)


def status():
    with lock:
        ha = cache['ha']
    return {'time': time.time(), 'internet_ms': tcp_ms('1.1.1.1', 443), 'pc_online': None, 'ha': ha,
            'genelec': OFF, 'dante': {'ok': False}}
