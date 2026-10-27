"""Files and small helpers shared by every module: state directory, JSON load/save, secrets."""
import json, os, socket, ssl, time

from .config import C, STATE

STATIC = C.STATIC
WALLS = os.path.join(STATE, 'walls')
SETTINGS = os.path.join(STATE, 'settings.json')          # panel settings saved from the pages (wallpaper, dim, ...)
SECRETS = os.path.join(STATE, 'secrets.json')            # HA token, ntfy topic (0600, never sent to pages)
NOCHECK = ssl.create_default_context(); NOCHECK.check_hostname = False; NOCHECK.verify_mode = ssl.CERT_NONE

os.makedirs(WALLS, exist_ok=True)


def load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def save(path, data, private=False):
    tmp = path + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(data, f)
    if private:
        os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def secret(name):
    return load(SECRETS, {}).get(name)


def tcp_ms(host, port, timeout=1.5):
    t = time.monotonic()
    try:
        socket.create_connection((host, port), timeout=timeout).close()
        return round((time.monotonic() - t) * 1000)
    except OSError:
        return None
