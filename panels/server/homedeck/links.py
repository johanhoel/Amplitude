"""Status dots on Start / Admin: probe the fixed [links] list in homedeck.toml (never an address from a request).

Each answer carries the address it probed and whether it came from [links.extra] - the house's own machines,
which the setup wizard writes and the user adds to. The pages list those; they ship with none of their own.
"""
import concurrent.futures, threading, time, urllib.error, urllib.request

from .config import C
from .store import NOCHECK

_links = {'at': 0, 'data': {}}
_links_lock = threading.Lock()


def link_status():
    """Any HTTP answer (incl. 401/403/redirect) counts as up; timeouts and refused connections as down."""
    with _links_lock:
        if time.time() - _links['at'] < 25:
            return _links['data']

        def probe(item):
            key, url = item
            t = time.time()
            try:
                req = urllib.request.Request(url, method='GET', headers={'User-Agent': 'home-deck-start'})
                urllib.request.urlopen(req, timeout=4, context=NOCHECK).close()
                up = True
            except urllib.error.HTTPError:
                up = True
            except Exception:
                up = False
            return key, {'up': up, 'ms': round((time.time() - t) * 1000), 'url': url, 'extra': key in C.LINK_EXTRA}
        with concurrent.futures.ThreadPoolExecutor(max_workers=24) as ex:
            _links.update(at=time.time(), data=dict(ex.map(probe, C.LINK_CHECKS.items())))
        return _links['data']
