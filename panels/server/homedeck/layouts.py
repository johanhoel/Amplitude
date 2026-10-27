"""Edit mode storage (Admin, Start, Family info): one JSON file per page, every older save kept for undo.
Pages and how many saves to keep: [layouts] in homedeck.toml."""
import os, re, threading, time

from .config import C, STATE
from .store import load, save

LAYOUTS = os.path.join(STATE, 'layouts')
_layout_lock = threading.Lock()


def editable(page):
    """Pages with an edit mode: [layouts] pages, plus every board (board_<name>, your own dashboards on /board/<name>)."""
    return page in C.LAYOUT_PAGES or bool(re.fullmatch(r'board_[a-z0-9_]{1,30}', page))


def boards():
    """GET /api/boards: every saved board, for the /boards list."""
    out = []
    for f in sorted(os.listdir(LAYOUTS)) if os.path.isdir(LAYOUTS) else []:
        m = re.fullmatch(r'board_([a-z0-9_]{1,30})\.json', f)
        if not m:
            continue
        b = load(os.path.join(LAYOUTS, f), {})
        if not isinstance(b.get('modules'), list):
            continue
        out.append({'name': m.group(1), 'title': b.get('title') or m.group(1), 'count': len(b['modules']),
                    'icons': [x.get('type') for x in b['modules'][:8]], 'saved': b.get('saved')})
    return sorted(out, key=lambda b: b['title'].lower())


def board_delete(name):
    """POST /api/boards/delete (admin): the board goes into the history folder, so it can be put back by hand."""
    if not re.fullmatch(r'[a-z0-9_]{1,30}', name or ''):
        raise ValueError('bad board name')
    with _layout_lock:
        cur = layout_path('board_' + name)
        if not os.path.exists(cur):
            raise ValueError('no such board')
        os.makedirs(os.path.join(LAYOUTS, 'history'), exist_ok=True)
        os.replace(cur, os.path.join(LAYOUTS, 'history', f'board_{name}-{int(time.time() * 1000)}.json'))


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
