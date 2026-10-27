"""Home Deck first-run setup: scan the network, connect Home Assistant, suggest settings, you confirm, then apply.

Runs as root on :8089 next to Home Deck (Home Deck runs as a locked-down service user and cannot change its own
settings or scan as root). It is protected by a one-time setup code: install.sh and `homedeck-onboard` print it.

  GET  /                  the wizard (onboard.html)
  POST /api/login         {code} -> session cookie
  POST /api/scan          start a network scan;  GET /api/scan  {running, pct, text, done}
  POST /api/ha            {url, token?} test Home Assistant (no token = the one already saved); the token stays here
  GET  /api/plan          every setting the wizard covers: current value, what was found, the suggestion
  POST /api/preview       {choices} -> {diff, problems} for homedeck.toml (nothing written)
  POST /api/finish        {choices} -> backup, write homedeck.toml + the token, homedeck-apply, then this service stops
Settings start from the current homedeck.toml; only values you confirm change. Comments in the file stay.
"""
import difflib, hmac, json, os, re, secrets as pysecrets, shutil, ssl, subprocess, sys, threading, time, tomllib, urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import discover, tomledit  # noqa: E402

ROOT = os.environ.get('ONBOARD_ROOT', '/opt/panel-wrapper')
STATE = os.environ.get('ONBOARD_STATE', '/var/lib/panel-wrapper')
APPLY = os.environ.get('ONBOARD_APPLY', '/usr/local/sbin/homedeck-apply')
CODE_FILE = os.environ.get('ONBOARD_CODE_FILE', '/etc/homedeck-onboard.code')
STOP = os.environ.get('ONBOARD_STOP', 'systemctl disable --now homedeck-onboard')
PORT = int(os.environ.get('ONBOARD_PORT', '8089'))
CONFIG = os.path.join(ROOT, 'homedeck.toml')
os.environ['HOMEDECK_CHECKONLY'] = '1'
sys.path.insert(0, ROOT)
from homedeck import config as hdconfig  # noqa: E402  (the panels' own value checks)

NOVERIFY = ssl._create_unverified_context()
S = {'sessions': set(), 'fails': [], 'scan': {'running': False, 'pct': 0, 'text': '', 'result': None},
     'ha': {'url': None, 'token': None, 'states': None, 'error': None}}
LOCK = threading.Lock()


# ---------- Home Assistant ----------
def saved_token():
    try:
        with open(os.path.join(STATE, 'secrets.json')) as f:
            return json.load(f).get('ha_token')
    except (OSError, ValueError):
        return None


def ha_states(url, token):
    req = urllib.request.Request(url.rstrip('/') + '/api/states', headers={'Authorization': 'Bearer ' + token})
    with urllib.request.urlopen(req, timeout=8, context=NOVERIFY) as r:
        return json.load(r)


def ha_config(url, token):
    req = urllib.request.Request(url.rstrip('/') + '/api/config', headers={'Authorization': 'Bearer ' + token})
    with urllib.request.urlopen(req, timeout=8, context=NOVERIFY) as r:
        return json.load(r)


# ---------- the plan: what each setting is now, what was found, what we suggest ----------
def current():
    with open(CONFIG, 'rb') as f:
        return tomllib.load(f)


def _get(tree, dotted):
    for part in dotted.split('.'):
        tree = tree.get(part) if isinstance(tree, dict) else None
    return tree


def _ents(states, domain, prefer=None):
    """-> [(entity_id, friendly name)] of a domain, best match first."""
    out = [(s['entity_id'], s.get('attributes', {}).get('friendly_name') or s['entity_id'])
           for s in states if s['entity_id'].split('.')[0] == domain]
    if prefer:
        out.sort(key=lambda e: not re.search(prefer, e[0] + ' ' + e[1], re.I))
    return out


# step, dotted key, label, kind, HA domain + preferred pattern (for entity fields), help
ENTITY_FIELDS = [
    ('home', 'entities.lock', 'Front door lock', 'lock', 'front|door|ytter|entre', 'Shown on Start, Pulse and the leave check.'),
    ('home', 'entities.weather', 'Weather', 'weather', 'forecast_home|home', 'Weather on Start, Ambient and Family info.'),
    ('home', 'entities.vacuum', 'Robot vacuum', 'vacuum', '', 'Start / dock buttons on Control.'),
    ('home', 'entities.charger', 'EV charger switch', 'switch', 'charg|easee', 'Charger on Control and Pulse.'),
    ('cameras', 'entities.cam_detect', 'Camera alerts on/off', 'input_boolean', 'cam|detect|motion', 'The switch that turns camera alerts to phones on and off.'),
    ('lab', 'entities.wake_pc', 'Wake the PC', 'button', 'wake|wol', 'Wake-on-LAN button for the desk PC.'),
    ('media', 'entities.spotify', 'Spotify', 'media_player', 'spotify', 'Spotify player on Media and Start.'),
    ('media', 'entities.tv', 'TV / soundbar', 'media_player', r'\btv|beam|soundbar', 'The TV room player.'),
    ('media', 'entities.apple_tv', 'Apple TV', 'media_player', 'apple|vardagsrum|living', 'Apple TV on Media.'),
    ('media', 'entities.apple_tv_remote', 'Apple TV remote', 'remote', 'apple|vardagsrum|living', 'Arrow keys on Media and Remote.'),
]
STEPS = [('ha', 'Home Assistant'), ('home', 'Home'), ('media', 'Media and speakers'), ('cameras', 'Cameras'),
         ('lab', 'Lab and network'), ('people', 'People and phones')]


def _field(step, key, label, kind, cur, options, help, info=None):
    vals = [o['value'] for o in options]
    if kind == 'one':
        suggest = cur if cur in vals or not options else options[0]['value']
        if cur is not None and cur not in vals:
            options = options + [{'value': cur, 'label': f'{cur}', 'why': 'current setting, not seen in the scan', 'seen': False}]
    else:
        cur = cur or []
        seen = [v for v in cur if v in vals]
        suggest = seen or [o['value'] for o in options if o.get('pick')] or cur
        options = options + [{'value': v, 'label': str(v), 'why': 'current setting, not seen in the scan', 'seen': False}
                             for v in cur if v not in vals]
    return {'step': step, 'key': key, 'label': label, 'kind': kind, 'current': cur, 'suggest': suggest,
            'options': options, 'help': help, 'info': info or []}


def plan():
    tree, scan, ha = current(), S['scan']['result'] or {'found': {}, 'devices': []}, S['ha']
    found, states = scan['found'], ha['states'] or []
    F = []
    # Home Assistant
    opts = [{'value': x['url'], 'label': x['label'], 'why': f"found at {x['ip']}", 'seen': True}
            for x in found.get('homeassistant', []) if x.get('url')]
    cur = tree['homeassistant']['url']
    if ha['url'] and ha['url'] not in [o['value'] for o in opts]:
        opts.insert(0, {'value': ha['url'], 'label': ha['url'], 'why': 'the address you connected with', 'seen': True})
    F.append(_field('ha', 'homeassistant.url', 'Home Assistant address', 'one', cur, opts,
                    'The panels talk to Home Assistant at this address.'))
    # entities from Home Assistant
    for step, key, label, domain, prefer, help in ENTITY_FIELDS:
        opts = [{'value': e, 'label': n, 'why': e, 'seen': True} for e, n in _ents(states, domain, prefer)]
        F.append(_field(step, key, label, 'one', _get(tree, key), opts, help))
    # media players
    cur_players = {p['entity']: p['label'] for p in tree.get('players', [])}
    opts = [{'value': e, 'label': cur_players.get(e, n), 'why': e, 'seen': True, 'pick': e in cur_players}
            for e, n in _ents(states, 'media_player', 'spotify|tv|beam')]
    f = _field('media', 'players', 'Players on the Media and Deck pages', 'many', list(cur_players), opts,
               'Tick the speakers and players to show, in this order.')
    for o in f['options']:
        o['label'] = cur_players.get(o['value'], o['label'])     # keep the names you gave them
    F.append(f)
    info = [f"{x['label']} ({x['ip']})" for r in ('sonos', 'cast', 'appletv', 'airplay') for x in found.get(r, [])]
    F[-1]['info'] = info
    # Genelec speakers on Dante
    gen = [x for x in found.get('dante', []) if x['dante_name'].lower().startswith('genelec')]
    F.append(_field('media', 'audio.genelecs', 'Genelec speakers', 'many', tree['audio']['genelecs'],
                    [{'value': x['ip'], 'label': x['dante_name'], 'why': x['ip'], 'seen': True, 'pick': True} for x in gen],
                    'Volume, mute and power for these speakers (Genelec API on each).',
                    [f"{x['label']} ({x['ip']})" for x in found.get('dante', []) if x not in gen]))
    # cameras
    F.append(_field('cameras', 'services.camfeed', 'Camera feed (camwatch)', 'one', tree['services']['camfeed'],
                    [{'value': x['url'], 'label': x['label'], 'why': x['ip'], 'seen': True} for x in found.get('camfeed', [])],
                    'Visits, thumbnails and recordings on Cameras, Security and Today.',
                    [f"{x['label']} ({x['ip']})" for r in ('camera', 'nvr') for x in found.get(r, [])]
                    + [f'Home Assistant camera: {n}' for e, n in _ents(states, 'camera')]))
    # lab and network
    F.append(_field('lab', 'services.piholes', 'Pi-hole DNS servers', 'many', tree['services']['piholes'],
                    [{'value': x['ip'], 'label': x['label'], 'why': x['ip'], 'seen': True, 'pick': True} for x in found.get('pihole', [])],
                    'Network names, presence by Wi-Fi and the DNS tiles.'))
    for key, role, label, help in (('services.labpanel', 'labpanel', 'Lab panel', 'Lab tiles on Admin and the lab touch panel.'),
                                   ('services.prometheus', 'prometheus', 'Prometheus', 'Graphs on Network and Pulse.')):
        F.append(_field('lab', key, label, 'one', _get(tree, key),
                        [{'value': x['url'], 'label': x['label'], 'why': x['ip'], 'seen': True} for x in found.get(role, [])], help))
    F.append(_field('lab', 'services.pc', 'Desk PC (deck-listener)', 'one', tree['services']['pc'],
                    [{'value': x['hostport'], 'label': x['label'], 'why': x['ip'], 'seen': True} for x in found.get('pc', [])],
                    'Mic mute, sleep and keys on the PC. The PC only answers while it is on.',
                    [f"{x['label']} ({x['ip']})" for r in ('router', 'proxmox', 'pbs', 'grafana') for x in found.get(r, [])]))
    # people and phones
    phones = found.get('phone', [])
    people = {e.split('.', 1)[1]: n for e, n in _ents(states, 'person')}
    cur_ph = tree['presence']['phones']
    for pid in list(cur_ph) + [p for p in people if p not in cur_ph]:
        opts = [{'value': x['mac'], 'label': x['label'], 'why': f"{x['ip']} · {x['mac']}" + (' · private address' if x['private_mac'] else ''),
                 'seen': True} for x in phones]
        f = _field('people', f'presence.phones.{pid}', people.get(pid, pid.title()), 'many', cur_ph.get(pid, []), opts,
                   'Phones that mean this person is home. Only ticked phones are used.')
        f['suggest'] = cur_ph.get(pid, [])                 # phones are never ticked for you
        F.append(f)
    return {'steps': STEPS, 'fields': F, 'scan': {k: scan.get(k) for k in ('subnet', 'took_s')} | {'devices': len(scan['devices'])},
            'ha': {'connected': bool(states), 'url': ha['url'], 'error': ha['error'], 'entities': len(states)},
            'devices': scan['devices']}


def render(choices):
    """choices {key: value} -> (new text, problems). Only keys whose value differs from now are written."""
    with open(CONFIG, encoding='utf-8') as f:
        text = f.read()
    tree, phones = tomllib.loads(text), {}
    for key, v in choices.items():
        if key.startswith('presence.phones.'):
            if v != tree['presence']['phones'].get(key.rsplit('.', 1)[1], []) and v:
                phones[key.rsplit('.', 1)[1]] = v
        elif key == 'players':
            labels = (choices.get('_labels') or {}) | {p['entity']: p['label'] for p in tree.get('players', [])}
            new = [{'entity': e, 'label': labels.get(e) or e.split('.', 1)[1].replace('_', ' ').title()} for e in v]
            if new != tree.get('players'):
                text = tomledit.set_players(text, new)
        elif key != '_labels' and v is not None and v != _get(tree, key):
            text = tomledit.set_value(text, key, v)
    if phones:
        text = tomledit.set_table(text, 'presence.phones', phones)
    try:
        problems = hdconfig.validate(tomllib.loads(text))
    except tomllib.TOMLDecodeError as e:
        problems = [str(e)]
    return text, problems


# ---------- web ----------
class H(SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send_json(self, obj, code=200, cookie=None):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json'); self.send_header('Cache-Control', 'no-store')
        if cookie:
            self.send_header('Set-Cookie', f'hd_onboard={cookie}; Path=/; HttpOnly; SameSite=Strict')
        self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)

    def authed(self):
        m = re.search(r'hd_onboard=([\w-]+)', self.headers.get('Cookie', ''))
        return bool(m and m.group(1) in S['sessions'])

    def req(self):
        n = int(self.headers.get('Content-Length') or 0)
        return json.loads(self.rfile.read(min(n, 256 * 1024)) or b'{}')

    def do_GET(self):
        p = self.path.split('?')[0]
        if p in ('/', '/onboard'):
            with open(os.path.join(HERE, 'onboard.html'), 'rb') as f:
                data = f.read()
            self.send_response(200); self.send_header('Content-Type', 'text/html; charset=utf-8'); self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(data))); self.end_headers(); return self.wfile.write(data)
        if p == '/api/session':
            return self.send_json({'ok': self.authed(), 'token_saved': bool(saved_token())})
        if not self.authed():
            return self.send_json({'error': 'setup code needed'}, 401)
        if p == '/api/scan':
            sc = S['scan']
            return self.send_json({'running': sc['running'], 'pct': sc['pct'], 'text': sc['text'], 'done': sc['result'] is not None})
        if p == '/api/plan':
            try:
                return self.send_json(plan())
            except Exception as e:
                return self.send_json({'error': f'{type(e).__name__}: {e}'}, 500)
        return self.send_json({'error': 'not found'}, 404)

    def do_POST(self):
        p = self.path.split('?')[0]
        try:
            r = self.req()
        except ValueError:
            return self.send_json({'error': 'bad request'}, 400)
        if p == '/api/login':
            now = time.time()
            S['fails'] = [t for t in S['fails'] if now - t < 300]
            if len(S['fails']) >= 10:
                return self.send_json({'error': 'Too many wrong codes. Wait 5 minutes.'}, 429)
            try:
                with open(CODE_FILE) as f:
                    code = f.read().strip()
            except OSError:
                return self.send_json({'error': 'No setup code on the server. Run homedeck-onboard there.'}, 500)
            if hmac.compare_digest(str(r.get('code', '')).strip().replace(' ', '').replace('-', ''), code.replace('-', '')):
                tok = pysecrets.token_urlsafe(24)
                S['sessions'].add(tok)
                return self.send_json({'ok': True}, cookie=tok)
            S['fails'].append(now)
            return self.send_json({'error': 'That code is not right.'}, 403)
        if not self.authed():
            return self.send_json({'error': 'setup code needed'}, 401)
        if p == '/api/scan':
            with LOCK:
                if not S['scan']['running']:
                    S['scan'].update(running=True, pct=0, text='Starting ...')
                    threading.Thread(target=run_scan, daemon=True).start()
            return self.send_json({'ok': True})
        if p == '/api/ha':
            url = (r.get('url') or '').strip().rstrip('/')
            token = (r.get('token') or '').strip() or S['ha']['token'] or saved_token()
            if not re.fullmatch(r'https?://[^\s/]+', url):
                return self.send_json({'error': 'Address like http://192.168.1.20:8123'}, 400)
            if not token:
                return self.send_json({'error': 'Paste a token first.'}, 400)
            try:
                states = ha_states(url, token)
            except Exception as e:
                S['ha'].update(error=str(e)[:160])
                msg = 'Home Assistant said the token is wrong.' if '401' in str(e) else f'Could not reach Home Assistant: {str(e)[:120]}'
                return self.send_json({'error': msg}, 502)
            try:
                cfg = ha_config(url, token)                    # name + version only; fine without
            except Exception:
                cfg = {}
            S['ha'].update(url=url, token=token, states=states, error=None)
            doms = {}
            for s in states:
                doms[s['entity_id'].split('.')[0]] = doms.get(s['entity_id'].split('.')[0], 0) + 1
            return self.send_json({'ok': True, 'name': cfg.get('location_name'), 'version': cfg.get('version'),
                                   'counts': {k: doms.get(k, 0) for k in ('light', 'media_player', 'person', 'camera', 'lock', 'switch')}})
        if p in ('/api/preview', '/api/finish'):
            try:
                text, problems = render(r.get('choices') or {})
            except (KeyError, ValueError, TypeError) as e:
                return self.send_json({'error': str(e)}, 400)
            with open(CONFIG, encoding='utf-8') as f:
                old = f.read()
            diff = ''.join(difflib.unified_diff(old.splitlines(True), text.splitlines(True), 'homedeck.toml now', 'after setup', n=1))
            token_new = bool(S['ha']['token']) and S['ha']['token'] != saved_token()
            if p == '/api/preview' or problems:
                return self.send_json({'diff': diff, 'problems': problems, 'token_new': token_new}, 200 if p == '/api/preview' else 400)
            return self.send_json(finish(old, text, token_new))
        return self.send_json({'error': 'not found'}, 404)


def run_scan():
    sc = S['scan']
    try:
        sc['result'] = discover.scan(lambda pct, text: sc.update(pct=pct, text=text))
    except Exception as e:
        sc.update(text=f'Scan failed: {e}')
    finally:
        sc['running'] = False


def finish(old, text, token_new):
    stamp = time.strftime('%Y%m%d-%H%M%S')
    steps = []
    if text != old:
        shutil.copyfile(CONFIG, f'{CONFIG}.bak-onboard-{stamp}')
        with open(CONFIG, 'w', encoding='utf-8') as f:
            f.write(text)
        steps.append(f'homedeck.toml saved (previous copy: homedeck.toml.bak-onboard-{stamp})')
    if token_new:
        path = os.path.join(STATE, 'secrets.json')
        try:
            with open(path) as f:
                sec = json.load(f)
        except (OSError, ValueError):
            sec = {}
        sec['ha_token'] = S['ha']['token']
        st = os.stat(os.path.realpath(STATE))
        fd = os.open(path + '.tmp', os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as f:
            json.dump(sec, f, indent=2)
        os.chown(path + '.tmp', st.st_uid, st.st_gid)     # the panels' own service user must be able to read it
        os.replace(path + '.tmp', path)
        steps.append('Home Assistant token saved for the panels')
    if not steps:
        return {'ok': True, 'steps': ['Nothing to change: the settings already match.'], 'output': ''}
    res = subprocess.run(APPLY, shell=True, capture_output=True, text=True, timeout=120)
    ok = res.returncode == 0
    if ok:
        threading.Timer(3, lambda: subprocess.run(STOP, shell=True)).start()   # the wizard is done: stop and stay stopped
    return {'ok': ok, 'steps': steps, 'output': (res.stdout + res.stderr)[-3000:]}


if __name__ == '__main__':
    print(f'Home Deck setup listening on :{PORT}', flush=True)
    ThreadingHTTPServer(('0.0.0.0', PORT), H).serve_forever()
