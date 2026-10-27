"""Edit mode storage (Admin, Start, Family info): one JSON file per page, every older save kept for undo.
Pages and how many saves to keep: [layouts] in homedeck.toml."""
import os, threading, time

from .config import C, STATE
from .store import load, save

LAYOUTS = os.path.join(STATE, 'layouts')
_layout_lock = threading.Lock()


def layout_path(page):
    return os.path.join(LAYOUTS, page + '.json')


def layout_get(page):
    return load(layout_path(page), {})


def layout_history(page):
    d = os.path.join(LAYOUTS, 'history')
    return sorted((f for f in os.listdir(d) if f.startswith(page + '-') and f.endswith('.json')), reverse=True) if os.path.isdir(d) else []


def layout_save(page, req):
    """Keeps the current file in history before every change, so 'revert' can step back one save at a time."""
    with _layout_lock:
        os.makedirs(os.path.join(LAYOUTS, 'history'), exist_ok=True)
        cur = layout_path(page)
        if req.get('revert'):
            hist = layout_history(page)
            if not hist:
                raise ValueError('nothing to undo')
            os.replace(os.path.join(LAYOUTS, 'history', hist[0]), cur)
            return load(cur, {})
        hist_file = os.path.join(LAYOUTS, 'history', f'{page}-{int(time.time() * 1000)}.json')
        if os.path.exists(cur):
            os.replace(cur, hist_file)
        else:
            save(hist_file, {})                       # first save: undo then goes back to the page defaults
        if req.get('reset'):
            data = {}
        else:
            data = req.get('layout')
            if not isinstance(data, dict):
                raise ValueError('layout must be an object')
            data['saved'] = time.time()
            save(cur, data)
        for old in layout_history(page)[C.LAYOUT_KEEP:]:
            os.remove(os.path.join(LAYOUTS, 'history', old))
        return data
