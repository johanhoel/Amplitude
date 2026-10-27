"""Paired devices: the Android app and phones' home-screen web app, and the key check for access from the internet.

How it works
- An admin (PIN session) starts a pairing on /devices: a 6-digit code + a QR code, valid [remote] pair_minutes.
- The phone claims it from the HOME network only (its real address must be private: home Wi-Fi or WireGuard).
  It gets its own random key (shown once; only a SHA-256 hash is stored in devices.json) as the cookie hd_device
  (browsers) and in the JSON answer (the app).
- From the internet, everything goes through the edge proxy ([remote] edge). nginx asks GET /api/pair/check on every
  request; only a paired device that was not removed gets through. Home Deck checks again itself: a request that
  arrives from the edge without a valid key gets 401 (except the pairing page), so a mistake on the edge cannot open it.
- Removing a device on /devices locks it out at once.
Files: $STATE/devices.json (0600). Settings: [remote] in homedeck.toml.
"""
import hashlib, hmac, ipaddress, json, os, secrets, threading, time

from .config import C, STATE
from .store import load, save

DEVICES = os.path.join(STATE, 'devices.json')
COOKIE = 'hd_device'
COOKIE_MAX_AGE = 400 * 86400                      # browsers cap cookies at 400 days; the app re-sends its key anyway
OPEN_PATHS = ('/pair', '/pair.html', '/api/pair/claim', '/api/pair/check', '/favicon.ico')   # reachable without a key
_lock = threading.Lock()
_pending = {}                                     # secret -> {code, name, person, exp, by}
_claim_fails = {}                                 # real ip -> [count, first_at]
_seen_write = {}                                  # device id -> last time last_seen was written (throttle)


def _h(token):
    return hashlib.sha256(token.encode()).hexdigest()


# ---------- who is asking ----------
def from_edge(handler):
    return handler.client_address[0] in C.REMOTE_EDGE


def client_ip(handler):
    """The visitor's real address: the edge passes it in X-Real-IP (it overwrites any value the visitor sent)."""
    if from_edge(handler):
        return (handler.headers.get('X-Real-IP') or handler.client_address[0]).strip()
    return handler.client_address[0]


def at_home(handler):
    """Home network = a private address (home Wi-Fi, WireGuard), directly or through the edge (split DNS)."""
    try:
        return ipaddress.ip_address(client_ip(handler)).is_private
    except ValueError:
        return False


def token_of(headers):
    a = headers.get('Authorization') or ''
    if a.startswith('Bearer '):
        return a[7:].strip()
    for part in (headers.get('Cookie') or '').split(';'):
        k, _, v = part.strip().partition('=')
        if k == COOKIE:
            return v.strip()
    return ''


# ---------- devices ----------
def _all():
    return load(DEVICES, {})


def device_for(headers, ip=None):
    """-> (device id, record) for a valid key, else (None, None). Updates last seen (at most once a minute)."""
    tok = token_of(headers)
    if not tok or len(tok) < 30:
        return None, None
    h = _h(tok)
    for did, d in _all().items():
        if hmac.compare_digest(d.get('hash', ''), h) and not d.get('removed'):
            now = time.time()
            if now - _seen_write.get(did, 0) > 60:
                _seen_write[did] = now
                with _lock:
                    devs = _all()
                    if did in devs:
                        devs[did].update(last_seen=now, last_ip=ip or devs[did].get('last_ip'))
                        save(DEVICES, devs, private=True)
            return did, d
    return None, None


def edge_allowed(handler):
    """Request from the edge: the pairing page is open; everything else needs a paired device's key."""
    path = handler.path.split('?')[0]
    if path in OPEN_PATHS:
        return True
    did, _ = device_for(handler.headers, client_ip(handler))
    return bool(did)


def check(handler):
    """GET /api/pair/check (nginx auth_request on the edge): 204 + X-Device-Id, or 401."""
    did, d = device_for(handler.headers, client_ip(handler))
    return (204, {'X-Device-Id': did, 'X-Device-Name': (d or {}).get('name', '').encode('ascii', 'replace').decode()}) if did else (401, {})


def public_list():
    out = []
    for did, d in sorted(_all().items(), key=lambda x: -x[1].get('created', 0)):
        if d.get('removed'):
            continue
        out.append({k: d.get(k) for k in ('name', 'person', 'platform', 'model', 'created', 'last_seen', 'last_ip')} | {'id': did})
    return out


def pair_start(req, by_ip):
    name = str(req.get('name') or '').strip()[:40] or 'Phone'
    person = str(req.get('person') or '').strip()[:30] or None
    now = time.time()
    with _lock:
        for s in [s for s, p in _pending.items() if p['exp'] < now]:
            _pending.pop(s, None)
        codes = {p['code'] for p in _pending.values()}
        code = next(c for c in (f'{secrets.randbelow(10 ** 6):06d}' for _ in range(50)) if c not in codes)
        secret = secrets.token_urlsafe(24)
        _pending[secret] = {'code': code, 'name': name, 'person': person, 'exp': now + C.PAIR_MINUTES * 60, 'by': by_ip}
    print(f'devices: pairing started for "{name}" from {by_ip}', flush=True)
    return {'code': code, 'secret': secret, 'expires': now + C.PAIR_MINUTES * 60, 'name': name,
            'url': f'{C.REMOTE_URL}/pair?s={secret}', 'public_url': C.REMOTE_URL}


def pair_claim(req, handler):
    """-> (code, body, token or None). Only from the home network; a code or the QR secret, once, before it expires."""
    ip = client_ip(handler)
    if not at_home(handler):
        print(f'devices: claim refused from {ip} (not the home network)', flush=True)
        return 403, {'error': 'Pair this device at home (on the home Wi-Fi), then it works everywhere.'}, None
    now = time.time()
    with _lock:
        f = _claim_fails.get(ip)
        if f and f[0] >= 8 and now - f[1] < 600:
            return 429, {'error': 'Too many wrong codes. Wait 10 minutes.'}, None
        secret = str(req.get('secret') or '')
        code = str(req.get('code') or '').strip()
        hit = _pending.get(secret) if secret else next((s for s, p in _pending.items() if code and hmac.compare_digest(p['code'], code)), None)
        if isinstance(hit, str):
            secret, hit = hit, _pending.get(hit)
        if not hit or hit['exp'] < now:
            if not f or now - f[1] > 600:
                f = _claim_fails[ip] = [0, now]
            f[0] += 1
            return 400, {'error': 'That code is wrong or has expired. Start a new pairing on /devices.'}, None
        _pending.pop(secret, None)
        _claim_fails.pop(ip, None)
        token = secrets.token_urlsafe(32)
        did = secrets.token_hex(6)
        devs = _all()
        devs[did] = {'name': hit['name'], 'person': hit['person'], 'hash': _h(token), 'created': now, 'last_seen': now, 'last_ip': ip,
                     'platform': str(req.get('platform') or 'browser')[:20], 'model': str(req.get('model') or '')[:60]}
        save(DEVICES, devs, private=True)
    print(f'devices: paired "{hit["name"]}" ({did}) from {ip}', flush=True)
    return 200, {'ok': True, 'token': token, 'id': did, 'name': hit['name'], 'public_url': C.REMOTE_URL}, token


def remove(did):
    with _lock:
        devs = _all()
        if did not in devs:
            raise ValueError('unknown device')
        devs[did].update(removed=time.time(), hash='')
        save(DEVICES, devs, private=True)
    print(f'devices: removed {did}', flush=True)


def rename(did, name):
    with _lock:
        devs = _all()
        if did not in devs or devs[did].get('removed'):
            raise ValueError('unknown device')
        devs[did]['name'] = str(name or '').strip()[:40] or devs[did]['name']
        save(DEVICES, devs, private=True)


def cookie_header(token, max_age=COOKIE_MAX_AGE):
    return f'{COOKIE}={token}; Path=/; Max-Age={max_age}; HttpOnly; Secure; SameSite=Lax'
