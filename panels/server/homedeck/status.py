"""Wall-panel status (/api/status): HA summary, Genelec and Dante refreshed in the background, plus internet and PC."""
import threading, time

from .audio import dante_summary, genelec_summary
from .config import C
from .home import ha_summary
from .store import tcp_ms

lock = threading.Lock()
cache = {'dante': None, 'dante_at': 0, 'ha': None, 'ha_at': 0, 'genelec': None, 'genelec_at': 0}


def refresh_soon(*keys):
    """An action changed something: refresh these parts on the next background round."""
    with lock:
        for k in keys:
            cache[k + '_at'] = 0


def refresher():
    while True:
        now = time.time()
        for key, fn, every in (('ha', ha_summary, 8), ('genelec', genelec_summary, 6), ('dante', dante_summary, 30)):
            if now - cache[key + '_at'] >= every:
                try:
                    val = fn()
                except Exception as e:
                    val = {'configured': True, 'error': str(e)[:120]}
                with lock:
                    cache[key], cache[key + '_at'] = val, time.time()
        time.sleep(2)


def status():
    with lock:
        snap = {k: cache[k] for k in ('ha', 'genelec', 'dante')}
    return {'time': time.time(), 'internet_ms': tcp_ms('1.1.1.1', 443), 'pc_online': tcp_ms(*C.PC) is not None, **snap}
