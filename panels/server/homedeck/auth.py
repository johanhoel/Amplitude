"""Admin PIN for Home Deck: admin pages and admin actions need a session that only the PIN gives.

- The PIN is stored as a salted PBKDF2 hash in secrets.json ('admin_pin'), never in plain text.
- A correct PIN gives the browser a random session cookie (HttpOnly, SameSite=Strict) for [admin] session_hours,
  or remember_days with "remember this device". Sessions survive restarts (state file admin_sessions.json, 0600).
- [admin] max_tries wrong PINs from one address lock that address out for lock_minutes.
- First use: when no PIN is set, the keypad asks to choose one (setup). After that, changing it needs the old PIN.
Which pages / actions are protected: [admin] pages and the ADMIN_POSTS list below.
"""
import hashlib, hmac, os, secrets, threading, time

from .config import C, STATE
from .store import SECRETS, load, save

SESSIONS = os.path.join(STATE, 'admin_sessions.json')
COOKIE = 'hd_admin'
ADMIN_POSTS = ('/api/ops/act', '/api/settings', '/api/wallpaper', '/api/layout/', '/api/devices/', '/api/boards/', '/api/studio/', '/api/llm/', '/api/update/run', '/api/addons')   # change things only an admin should
_lock = threading.Lock()
_fails = {}                                           # ip -> [count, first_fail_at, locked_until]


def _hash(pin, salt):
    return hashlib.pbkdf2_hmac('sha256', pin.encode(), bytes.fromhex(salt), 200_000).hex()


def pin_set():
    return bool((load(SECRETS, {}).get('admin_pin') or {}).get('hash'))


def _valid_pin(pin):
    return isinstance(pin, str) and pin.isdigit() and C.ADMIN_PIN_MIN <= len(pin) <= 8


def _check(pin):
    rec = load(SECRETS, {}).get('admin_pin') or {}
    return bool(rec.get('hash')) and hmac.compare_digest(_hash(pin, rec['salt']), rec['hash'])


def _store_pin(pin):
    salt = secrets.token_hex(16)
    sec = load(SECRETS, {}); sec['admin_pin'] = {'salt': salt, 'hash': _hash(pin, salt), 'set': time.time()}
    save(SECRETS, sec, private=True)


def _sessions():
    now = time.time()
    return {t: s for t, s in load(SESSIONS, {}).items() if s.get('exp', 0) > now}


def _new_session(remember, ip):
    tok = secrets.token_urlsafe(32)
    ttl = C.ADMIN_REMEMBER_DAYS * 86400 if remember else C.ADMIN_SESSION_HOURS * 3600
    with _lock:
        s = _sessions(); s[tok] = {'exp': time.time() + ttl, 'ip': ip, 'at': time.time(), 'remember': bool(remember)}
        save(SESSIONS, s, private=True)
    return tok, ttl


def _cookie_token(headers):
    for part in (headers.get('Cookie') or '').split(';'):
        k, _, v = part.strip().partition('=')
        if k == COOKIE:
            return v
    return None


def is_admin(headers):
    tok = _cookie_token(headers)
    return bool(tok) and tok in _sessions()


def needs_admin_page(name):
    return name in C.ADMIN_PAGES


def needs_admin_post(path):
    return any(path == p or (p.endswith('/') and path.startswith(p)) for p in ADMIN_POSTS)


def _locked(ip):
    f = _fails.get(ip)
    return f and f[2] > time.time() and round(f[2] - time.time())


def _fail(ip):
    f = _fails.setdefault(ip, [0, time.time(), 0])
    if time.time() - f[1] > C.ADMIN_LOCK_MINUTES * 60:
        f[:] = [0, time.time(), 0]
    f[0] += 1
    if f[0] >= C.ADMIN_MAX_TRIES:
        f[2] = time.time() + C.ADMIN_LOCK_MINUTES * 60
        print(f'admin: {ip} locked out for {C.ADMIN_LOCK_MINUTES} min after {f[0]} wrong PINs', flush=True)
    return C.ADMIN_MAX_TRIES - f[0]


def status(headers, ip):
    return {'set': pin_set(), 'admin': is_admin(headers), 'locked_s': _locked(ip) or 0, 'min_len': C.ADMIN_PIN_MIN}


def handle(path, req, headers, ip):
    """POST /api/pin/setup|verify|change|logout -> (code, body, set_cookie or None)."""
    with _lock:
        wait = _locked(ip)
    if wait and path != '/api/pin/logout':
        return 429, {'error': 'locked', 'wait_s': wait}, None
    if path == '/api/pin/setup':
        if pin_set():
            return 409, {'error': 'A PIN is already set'}, None
        if not _valid_pin(req.get('pin')):
            return 400, {'error': f'Use {C.ADMIN_PIN_MIN} to 8 digits'}, None
        _store_pin(req['pin']); print(f'admin: PIN set from {ip}', flush=True)
        tok, ttl = _new_session(req.get('remember'), ip)
        return 200, {'ok': True}, (tok, ttl)
    if path == '/api/pin/verify':
        if not pin_set():
            return 409, {'error': 'No PIN set yet', 'setup': True}, None
        if not _check(str(req.get('pin', ''))):
            with _lock:
                left = _fail(ip)
            return 401, {'error': 'Wrong PIN', 'tries_left': max(0, left), 'wait_s': _locked(ip) or 0}, None
        _fails.pop(ip, None)
        tok, ttl = _new_session(req.get('remember'), ip)
        return 200, {'ok': True}, (tok, ttl)
    if path == '/api/pin/change':
        if not _check(str(req.get('old', ''))):
            with _lock:
                left = _fail(ip)
            return 401, {'error': 'Wrong PIN', 'tries_left': max(0, left)}, None
        if not _valid_pin(req.get('pin')):
            return 400, {'error': f'Use {C.ADMIN_PIN_MIN} to 8 digits'}, None
        _store_pin(req['pin'])
        with _lock:
            save(SESSIONS, {}, private=True)            # a new PIN signs every device out
        tok, ttl = _new_session(req.get('remember'), ip)
        return 200, {'ok': True}, (tok, ttl)
    if path == '/api/pin/logout':
        tok = _cookie_token(headers)
        with _lock:
            s = _sessions(); s.pop(tok, None); save(SESSIONS, s, private=True)
        return 200, {'ok': True}, ('', 0)
    return 404, {'error': 'unknown'}, None
