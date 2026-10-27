"""Status dots on Start: this Home Deck's own pages, Home Assistant and the editor, plus [links] extra in homedeck.toml."""
import concurrent.futures, threading, time, urllib.error, urllib.request

from .config import C
from .store import NOCHECK

PAGES = ('start', 'living', 'media', 'family', 'familyinfo', 'ambient', 'desktop')
_links = {'at': 0, 'data': {}}
_links_lock = threading.Lock()


def checks():
    port = '' if C.PORT == 80 else f':{C.PORT}'
    d = {p: f'http://127.0.0.1{port}/{p}' for p in PAGES}
    d.update(ha=C.HA + '/manifest.json', editor='http://127.0.0.1:8088/')
    d.update(C.LINKS_EXTRA)
    return d


def link_status():
    """Any HTTP answer (incl. 401/403/redirect) counts as up; timeouts and refused connections as down."""
    with _links_lock:
        if time.time() - _links['at'] < 25:
            return _links['data']

        def probe(item):
            key, url = item
            t = time.time()
            try:
                urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'home-deck-start'}), timeout=4, context=NOCHECK).close()
                up = True
            except urllib.error.HTTPError:
                up = True
            except Exception:
                up = False
            return key, {'up': up, 'ms': round((time.time() - t) * 1000)}
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
            _links.update(at=time.time(), data=dict(ex.map(probe, checks().items())))
        return _links['data']
