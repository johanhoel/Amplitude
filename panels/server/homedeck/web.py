"""Every web address the panels use. GET/POST /api/... -> the modules; anything else -> a file from www/.

  GET  /api/health            is the server OK, and are the settings (homedeck.toml) OK? (homedeck-apply checks this)
  GET  /api/status            live data (network, PC, Dante, Genelec, Home Assistant)
  GET  /api/settings          public settings + which secrets are set (never the secrets)
  POST /api/settings          {wallpaper, dim, temps[], ha_token?, genelec_password?}
  POST /api/wallpaper         raw image body -> stored, returns {name};  GET /wall/<name> the image
  GET  /api/art?e=<player>    album / show art (proxied from Home Assistant)
  POST /api/genelec           {action: volume|mute|power, value};  POST /api/dante/source {source: pc|bt}
  POST /api/media             {action: play_pause|next|previous} (Spotify)
  POST /api/pc/mic            PC microphone mute via deck-listener (Home Assistant only);  POST /api/pc/do {action}
  GET  /api/lab/state, POST /api/lab/close, GET /lab   lab panel (service on monitor)
  GET  /api/llm/status, POST /api/llm/load|unload/<id>, /api/llm/launch/<setup>/<id>, /api/llm/video-use   Local AI (admin)
  GET  /api/llm/chats[/<id>], POST /api/llm/chats {text, model, id?}, /api/llm/chats/<id>/stop|delete   saved chats (admin)
  GET  /api/cams, /api/cam/<entity>/snap|stream        cameras through the lab panel service
  GET  /api/family /api/net   Family and Network panels;  GET /api/sec/visits, /api/sec/thumb|crop/...  camera visits
  GET  /api/presence, /api/presence/unassigned, /metrics   Wi-Fi presence (and for Prometheus)
  GET  /api/home/state, POST /api/home/do   rooms, lights, door, people, players, Apple TV; allowed actions
  GET  /api/bus, /api/bus/stops?q=, /api/weather, /api/leave   Family info
  GET  /api/layout/<page>[/history], POST /api/layout/<page>   edit mode (Admin, Start, Family info)
  GET  /api/news?f=<feed>     SVT headlines (Start);  GET /api/links  status dots
  GET  /api/ops/snapshot, /api/ops/events, POST /api/ops/act   Lab touch panel (lab panel service)
  GET  /api/pin/status, POST /api/pin/setup|verify|change|logout   admin PIN (auth.py); admin pages + admin POSTs need it
  GET  /<page>                www/<page>.html for the pages in PAGES (admin pages: /pin?next= first, unless unlocked)
"""
import json, os, re, subprocess, time, urllib.error, urllib.parse, urllib.request
from http.server import SimpleHTTPRequestHandler

from . import addons, audio, auth, devices, localai, studio, home, insights, layouts, leave, links, news, presence, status, transit, weather
from .config import C, REPORT
from .ha import entities as entity_list, ha_call, ha_get
from .store import SECRETS, SETTINGS, STATIC, WALLS, load, save

PAGES = ('ops', 'living', 'remote', 'family', 'net', 'security', 'ambient', 'media', 'start', 'familyinfo', 'admin', 'desktop',
         'pulse', 'today', 'rooms', 'control', 'atlas', 'pin', 'devices', 'pair', 'app', 'boards', 'studio', 'cameras', 'localai')
STARTED = time.time()


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=STATIC, **kw)

    def log_message(self, *a):
        pass

    def send_json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_bytes(self, data, ctype, cache=None):
        self.send_response(200)
        self.send_header('Content-Type', ctype)
        if cache:
            self.send_header('Cache-Control', cache)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        return self.wfile.write(data)

    def send_json_cookie(self, obj, code, cookie):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json'); self.send_header('Cache-Control', 'no-store')
        if cookie is not None:
            tok, ttl = cookie
            self.send_header('Set-Cookie', f'{auth.COOKIE}={tok}; Path=/; Max-Age={ttl}; HttpOnly; SameSite=Strict')
        self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)

    def admin_gate(self):
        """An admin page without a PIN session -> the keypad page, which comes back here after the PIN."""
        name = self.path.split('?')[0].strip('/')
        name = name[:-5] if name.endswith('.html') else name
        if auth.needs_admin_page(name) and not auth.is_admin(self.headers):
            self.send_response(302); self.send_header('Location', '/pin?next=' + urllib.parse.quote(self.path)); self.send_header('Cache-Control', 'no-store'); self.end_headers()
            return True
        return False

    def body(self, limit=64 * 1024):
        n = int(self.headers.get('Content-Length') or 0)
        if n > limit:
            raise ValueError('too large')
        return self.rfile.read(n)

    def json_or_502(self, fn, limit=160, code_key=None):
        try:
            return self.send_json(fn())
        except Exception as e:
            return self.send_json({'error': str(e)[:limit]} if not code_key else {'configured': True, 'error': str(e)[:limit]}, 502)

    def proxy_json(self, url, timeout):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                return self.send_json(json.load(r))
        except Exception as e:
            return self.send_json({'error': str(e)[:120]}, 502)

    # ---------- GET ----------
    def do_GET(self):
        p = self.path
        if devices.from_edge(self) and not devices.edge_allowed(self):    # from the internet: paired devices only
            return self.send_json({'error': 'not paired'}, 401)
        if p == '/api/pair/check':                                        # nginx auth_request on the edge
            code, hdrs = devices.check(self)
            self.send_response(code)
            for k, v in hdrs.items():
                self.send_header(k, v)
            self.send_header('Content-Length', '0'); self.end_headers()
            return
        if p == '/api/devices':
            if not auth.is_admin(self.headers):
                return self.send_json({'error': 'admin PIN needed', 'admin': True}, 401)
            return self.send_json({'devices': devices.public_list(), 'public_url': C.REMOTE_URL})
        if self.admin_gate():
            return
        if p == '/api/pin/status':
            return self.send_json(auth.status(self.headers, devices.client_ip(self)))
        if p == '/api/health':
            return self.send_json({'ok': True, 'started': STARTED, 'settings': REPORT})
        if p == '/api/status':
            return self.send_json(status.status())
        if p == '/api/lab/state':
            return self.proxy_json(f'{C.LABPANEL}/state/{C.LAB_PANEL_ID}', 3)
        if p == '/metrics':
            return self.send_bytes(presence.presence_metrics(), 'text/plain; version=0.0.4')
        if p == '/api/family':
            return self.json_or_502(insights.family_state)
        if p == '/api/net':
            return self.json_or_502(insights.net_state)
        if p == '/api/sec/days':                                          # Cameras panel: days with recordings
            return self.json_or_502(lambda: insights.camfeed('/days'))
        m = re.fullmatch(r'/api/sec/video/(\d{4}-\d\d-\d\d)/(camera\w+)\.mp4', p.split('?')[0])
        if m:
            return self.sec_video(m.group(1), m.group(2))
        if p.startswith('/api/sec/visits'):
            q = p.split('?', 1)[1] if '?' in p else 'days=2&limit=60'
            return self.json_or_502(lambda: insights.camfeed('/visits?' + q), 120)
        m = re.fullmatch(r'/api/sec/(thumb/\d{4}-\d\d-\d\d/camera\w+\.jpg(?:\?w=\d{2,4})?|crop/\d{4}-\d\d-\d\d/camera\w+_faces/\w+\.jpg)', p)
        if m:
            try:
                data = insights.camfeed('/' + m.group(1), raw=True)
            except Exception:
                return self.send_error(404)
            return self.send_bytes(data, 'image/jpeg', 'max-age=300')
        if p == '/api/presence/unassigned':
            return self.send_json({'burst_active': time.time() < presence.cam_burst['until'], 'last_camera_event': presence.cam_burst['stem'],
                                   'unassigned_arrivals': presence.unassigned_arrivals})
        if p == '/api/presence':
            return self.send_json(presence.presence_summary())
        if p == '/api/cams':
            return self.proxy_json(f'{C.LABPANEL}/cams', 3)
        m = re.fullmatch(r'/api/cam/(camera\.\w{1,80})/(snap|stream)(?:\?w=(\d{1,4}))?(?:[&?]t=\d+)?', p)
        if m:
            return self.camera(m.group(1), m.group(2), m.group(3))
        if p == '/api/leave':
            return self.json_or_502(lambda: leave.leave_state(devices.client_ip(self)))
        m = re.fullmatch(r'/api/layout/(\w+)(/history)?', p)
        if m and layouts.editable(m.group(1)):
            if m.group(2):
                return self.send_json([{'at': int(f.rsplit('-', 1)[1][:-5]) / 1000} for f in layouts.layout_history(m.group(1))])
            return self.send_json(layouts.layout_get(m.group(1)))
        if p.startswith('/api/bus/stops?'):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(p).query).get('q', [''])[0].strip()
            return self.json_or_502(lambda: transit.stop_search(q) if len(q) >= 2 else [], 120)
        m = re.fullmatch(r'/api/ha/entities\?domain=([a-z_]+)', p)
        if m:
            # Everything Home Assistant has in one domain, for the pickers in
            # edit mode. Names, not states: this answers "which one", not "how is it".
            return self.json_or_502(lambda: entity_list(m.group(1)), 30)
        m = re.fullmatch(r'/api/news\?f=([a-z]+)', p)
        if m and m.group(1) in C.NEWS_FEEDS:
            return self.json_or_502(lambda: news.news(m.group(1)), 120)
        if p == '/api/weather':
            return self.json_or_502(weather.weather_state)
        if p == '/api/bus':
            return self.json_or_502(transit.bus_state)
        if p == '/api/addons':
            # What this house has, derived from its settings. The pages hide
            # what is off, so one set of pages serves any house.
            return self.send_json({'enabled': addons.enabled(), 'state': addons.state()})
        if p.split('?')[0] == '/ha':                                      # Studio's Home Assistant link
            self.send_response(302); self.send_header('Location', C.HA + '/'); self.send_header('Content-Length', '0'); self.end_headers(); return
        if p == '/api/watched':                                           # Device status card (names + online only, no PIN)
            return self.json_or_502(studio.watched)
        if p == '/api/llm/status':                                        # Local AI panel (admin only, reads too)
            if not auth.is_admin(self.headers):
                return self.send_json({'error': 'admin PIN needed', 'admin': True}, 401)
            return self.json_or_502(localai.state)
        if p.startswith('/api/llm/chats'):                                # saved chats (admin only, reads too)
            if not auth.is_admin(self.headers):
                return self.send_json({'error': 'admin PIN needed', 'admin': True}, 401)
            if p == '/api/llm/chats':
                return self.send_json({'chats': localai.chats()})
            c = localai.chat_get(p.rsplit('/', 1)[1])
            return self.send_json(c) if c else self.send_json({'error': 'unknown chat'}, 404)
        if p.startswith('/api/studio/'):                                  # Home Deck Studio (admin only, reads too)
            if not auth.is_admin(self.headers):
                return self.send_json({'error': 'admin PIN needed', 'admin': True}, 401)
            q = p.split('?')[0]
            fn = {'/api/studio/inventory': lambda: {'items': studio.inventory(), 'rooms': studio.rooms()},
                  '/api/studio/summary': studio.summary, '/api/studio/draft': lambda: {'draft': studio.load(studio.DRAFT, [])},
                  '/api/studio/history': lambda: {'history': studio.history()}}.get(q)
            return self.json_or_502(fn) if fn else self.send_json({'error': 'unknown'}, 404)
        if p == '/api/boards':                                            # your own dashboards (/boards)
            return self.send_json({'boards': layouts.boards()})
        if re.fullmatch(r'/board/[a-z0-9_]{1,30}', p.split('?')[0]):      # one board: the same page, the name picks its layout
            self.path = '/board.html'
            return super().do_GET()
        if p == '/api/links':
            return self.send_json(links.link_status())
        if p.split('?')[0].strip('/') in PAGES:
            self.path = '/' + p.split('?')[0].strip('/') + '.html'
            return super().do_GET()
        if p == '/api/ops/snapshot':
            return self.proxy_json(f'{C.LABPANEL}/api/snapshot', 5)
        if p == '/api/ops/events':
            return self.relay_events()
        if p == '/api/home/state':
            return self.json_or_502(home.home_state, 120, code_key=True)
        if p.split('?')[0] in ('/lab', '/lab/'):
            self.path = '/index.html'
        if p == '/api/settings':
            s, sec = load(SETTINGS, {}), load(SECRETS, {})
            return self.send_json({**s, 'ha_token_set': bool(sec.get('ha_token')),
                                   'genelec_set': bool(sec.get('genelec_password')),
                                   'walls': sorted(os.listdir(WALLS))})
        if p.startswith('/wall/'):
            name = os.path.basename(p[6:].split('?')[0])
            path = os.path.join(WALLS, name)
            if not re.fullmatch(r'wall-\d+\.(jpg|png|webp|gif)', name) or not os.path.exists(path):
                return self.send_error(404)
            with open(path, 'rb') as f:
                return self.send_bytes(f.read(), 'image/' + ('jpeg' if name.endswith('jpg') else name.rsplit('.', 1)[1]), 'max-age=31536000, immutable')
        if p.startswith('/api/art'):
            try:
                ent = urllib.parse.parse_qs(urllib.parse.urlparse(p).query).get('e', [C.SPOTIFY])[0]
                st = ha_get('/api/states/' + (ent if ent in C.PLAYER_IDS else C.SPOTIFY))
                data = ha_get(st['attributes']['entity_picture'], raw=True)
            except Exception:
                return self.send_error(404)
            return self.send_bytes(data, 'image/jpeg', 'max-age=300')
        return super().do_GET()

    def relay_events(self):
        try:
            r = urllib.request.urlopen(f'{C.LABPANEL}/api/events', timeout=30)
        except Exception as e:
            return self.send_json({'error': str(e)[:120]}, 502)
        with r:
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            try:
                while chunk := r.read1(65536):
                    self.wfile.write(chunk)
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass

    def camera(self, entity, kind, width):
        url = f'{C.LABPANEL}/cam/{entity}/{kind}' + (f'?w={width}' if width else '')
        try:
            r = urllib.request.urlopen(url, timeout=10 if kind == 'snap' else 20)
        except urllib.error.HTTPError as e:
            return self.send_json({'error': e.read().decode(errors='replace').strip()[:120]}, e.code)
        except Exception as e:
            return self.send_json({'error': str(e)[:120]}, 502)
        with r:
            if kind == 'snap':
                return self.send_bytes(r.read(), r.headers.get('Content-Type', 'image/jpeg'), 'no-store')
            self.send_response(200)
            self.send_header('Content-Type', r.headers.get('Content-Type', 'image/jpeg'))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            try:                                   # MJPEG: relay chunk by chunk, never buffer
                while chunk := r.read1(65536):
                    self.wfile.write(chunk)
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass

    def sec_video(self, day, stem):
        """A recording from camwatch-feed, streamed through with Range (phones seek; Safari plays nothing without it)."""
        req = urllib.request.Request(f'{C.CAMFEED}/video/{day}/{stem}.mp4')
        if self.headers.get('Range'):
            req.add_header('Range', self.headers['Range'])
        try:
            r = urllib.request.urlopen(req, timeout=15)
        except urllib.error.HTTPError as e:
            return self.send_json({'error': 'no such recording' if e.code == 404 else 'camera feed error'}, e.code)
        except Exception as e:
            return self.send_json({'error': str(e)[:120]}, 502)
        with r:
            self.send_response(r.status)
            for h in ('Content-Type', 'Content-Length', 'Content-Range', 'Accept-Ranges'):
                if r.headers.get(h):
                    self.send_header(h, r.headers[h])
            self.send_header('Cache-Control', 'private, max-age=3600')
            self.end_headers()
            try:
                while chunk := r.read1(262144):
                    self.wfile.write(chunk)
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass

    # ---------- POST ----------
    def do_POST(self):
        try:
            if devices.from_edge(self) and not devices.edge_allowed(self):
                return self.send_json({'error': 'not paired'}, 401)
            if self.path == '/api/pair/claim':                            # home network only; sets the device cookie
                code, body, token = devices.pair_claim(json.loads(self.body(4096) or b'{}'), self)
                data = json.dumps(body).encode()
                self.send_response(code)
                self.send_header('Content-Type', 'application/json'); self.send_header('Cache-Control', 'no-store')
                if token:
                    self.send_header('Set-Cookie', devices.cookie_header(token))
                self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)
                return
            if self.path.startswith('/api/pin/'):
                code, body, cookie = auth.handle(self.path, json.loads(self.body(4096) or b'{}'), self.headers, devices.client_ip(self))
                return self.send_json_cookie(body, code, cookie)
            if auth.needs_admin_post(self.path) and not auth.is_admin(self.headers):
                return self.send_json({'error': 'admin PIN needed', 'admin': True}, 401)
            if self.path.startswith('/api/llm/'):                         # Local AI (admin, auth.ADMIN_POSTS)
                if self.path == '/api/llm/chats':                         # ask (new chat, or more in one): a job, not tied to the page
                    try:
                        return self.send_json(localai.chat_send(json.loads(self.body(64 * 1024) or b'{}')))
                    except ValueError as e:
                        return self.send_json({'error': str(e)}, 400)
                m = re.fullmatch(r'/api/llm/chats/([\w-]+)/(stop|delete)', self.path)
                if m:
                    try:
                        (localai.chat_stop if m.group(2) == 'stop' else localai.chat_delete)(m.group(1))
                    except ValueError as e:
                        return self.send_json({'error': str(e)}, 400)
                    return self.send_json({'ok': True})
                m = re.fullmatch(r'/api/llm/(load|unload)/(\w+)|/api/llm/launch/(opencode|claude)/(\w+)|/api/llm/(video-use)', self.path)
                if not m:
                    return self.send_json({'error': 'unknown'}, 404)
                try:
                    if m.group(1):
                        return self.send_json(localai.act(m.group(1), m.group(2)))
                    if m.group(3):
                        return self.send_json(localai.act('launch', m.group(4), m.group(3)))
                    return self.send_json(localai.act('video-use'))
                except ValueError as e:
                    return self.send_json({'error': str(e)}, 409 if 'busy' in str(e) else 400)
            if self.path.startswith('/api/studio/'):                      # admin (auth.ADMIN_POSTS)
                req = json.loads(self.body(64 * 1024) or b'{}')
                try:
                    if self.path == '/api/studio/draft':
                        d = studio.draft_clear() if req.get('clear') else studio.draft_clear(int(req['remove'])) if 'remove' in req else studio.draft_add(req.get('change') or {})
                        return self.send_json({'draft': d})
                    if self.path == '/api/studio/apply':
                        return self.send_json(studio.apply())
                    if self.path == '/api/studio/undo':
                        return self.send_json(studio.undo())
                except (ValueError, KeyError) as e:
                    return self.send_json({'error': str(e)}, 400)
                return self.send_json({'error': 'unknown'}, 404)
            if self.path == '/api/boards/delete':                         # admin (auth.ADMIN_POSTS)
                try:
                    layouts.board_delete(str(json.loads(self.body(4096) or b'{}').get('name', '')))
                except ValueError as e:
                    return self.send_json({'error': str(e)}, 400)
                return self.send_json({'ok': True})
            if self.path.startswith('/api/devices/'):                     # admin (auth.ADMIN_POSTS)
                req = json.loads(self.body(4096) or b'{}')
                try:
                    if self.path == '/api/devices/pair':
                        return self.send_json(devices.pair_start(req, devices.client_ip(self)))
                    if self.path == '/api/devices/remove':
                        devices.remove(str(req.get('id', ''))); return self.send_json({'ok': True})
                    if self.path == '/api/devices/rename':
                        devices.rename(str(req.get('id', '')), req.get('name')); return self.send_json({'ok': True})
                except ValueError as e:
                    return self.send_json({'error': str(e)}, 400)
                return self.send_json({'error': 'unknown'}, 404)
            m = re.fullmatch(r'/api/layout/(\w+)', self.path)
            if m and layouts.editable(m.group(1)):
                try:
                    return self.send_json({'ok': True, 'layout': layouts.layout_save(m.group(1), json.loads(self.body(512 * 1024) or b'{}'))})
                except ValueError as e:
                    return self.send_json({'error': str(e)}, 400)
            if self.path == '/api/wallpaper':
                ctype = self.headers.get('Content-Type', '')
                ext = {'image/jpeg': 'jpg', 'image/png': 'png', 'image/webp': 'webp', 'image/gif': 'gif'}.get(ctype)
                if not ext:
                    return self.send_json({'error': 'jpg, png, webp or gif only'}, 400)
                data = self.body(15 * 1024 * 1024)
                name = f'wall-{int(time.time() * 1000)}.{ext}'
                with open(os.path.join(WALLS, name), 'wb') as f:
                    f.write(data)
                return self.send_json({'name': name})
            if self.path == '/api/pc/mic':
                if self.client_address[0] not in C.PC_PROXY_CLIENTS:
                    return self.send_json({'error': 'forbidden'}, 403)
                with urllib.request.urlopen(f'http://{C.PC[0]}:{C.PC[1]}/mic', data=b'', timeout=5) as r:
                    return self.send_json({'mic': r.read().decode()[:20]})
            if self.path == '/api/lab/close':
                req = urllib.request.Request(f'{C.LABPANEL}/popup/close/{C.LAB_PANEL_ID}', data=b'', method='POST')
                with urllib.request.urlopen(req, timeout=4) as r:
                    r.read()
                return self.send_json({'ok': True})
            req = json.loads(self.body() or b'{}')
            if self.path == '/api/ops/act':
                q = urllib.request.Request(f'{C.LABPANEL}/api/act', method='POST', data=json.dumps({'key': req.get('key', '')}).encode(),
                                           headers={'Content-Type': 'application/json'})
                try:
                    with urllib.request.urlopen(q, timeout=200) as r:
                        return self.send_json(json.load(r))
                except urllib.error.HTTPError as e:
                    return self.send_json(json.loads(e.read() or b'{}') or {'error': str(e)}, e.code)
            if self.path == '/api/pc/do':
                path = C.PC_ACTIONS.get(req.get('action'))
                if not path:
                    return self.send_json({'error': 'unknown action'}, 400)
                try:
                    with urllib.request.urlopen(f'http://{C.PC[0]}:{C.PC[1]}{path}', timeout=6) as r:
                        return self.send_json({'ok': True, 'result': r.read().decode(errors='replace')[:60]})
                except Exception as e:
                    return self.send_json({'error': 'PC not answering' if 'timed out' in str(e) or 'refused' in str(e) else str(e)[:80]}, 502)
            if self.path == '/api/home/do':
                try:
                    home.home_do(req)
                except ValueError as e:
                    return self.send_json({'error': str(e)}, 400)
                return self.send_json({'ok': True})
            if self.path == '/api/settings':
                s, sec = load(SETTINGS, {}), load(SECRETS, {})
                for k in ('wallpaper', 'dim', 'blur', 'temps', 'accent', 'deck_mode', 'camera', 'motion'):
                    if k in req:
                        s[k] = req[k]
                for k in ('ha_token', 'genelec_password'):
                    if req.get(k) is not None:
                        sec[k] = req[k].strip() or None
                if 'delete_wall' in req:
                    name = os.path.basename(req['delete_wall'])
                    if re.fullmatch(r'wall-\d+\.(jpg|png|webp|gif)', name) and os.path.exists(os.path.join(WALLS, name)):
                        os.remove(os.path.join(WALLS, name))
                save(SETTINGS, s)
                save(SECRETS, sec, private=True)
                status.refresh_soon('ha', 'genelec')
                return self.send_json({'ok': True})
            if self.path == '/api/genelec':
                done, errors = audio.genelec_do(req.get('action'), req.get('value'))
                status.refresh_soon('genelec')
                if not done:
                    msg = 'password rejected' if any('401' in e for e in errors) else '; '.join(errors)
                    return self.send_json({'error': 'speakers: ' + msg}, 502)
                return self.send_json({'ok': True, 'speakers': len(done), 'skipped': errors})
            if self.path == '/api/dante/source':
                if req.get('source') not in C.SOURCES:
                    return self.send_json({'error': 'unknown source'}, 400)
                audio.dante_set_source(req['source'])
                status.refresh_soon('dante')
                return self.send_json({'ok': True})
            if self.path == '/api/media':
                svc = {'play_pause': 'media_play_pause', 'next': 'media_next_track',
                       'previous': 'media_previous_track'}.get(req.get('action'))
                if not svc:
                    return self.send_json({'error': 'unknown action'}, 400)
                ha_call('media_player', svc, {'entity_id': C.SPOTIFY})
                status.refresh_soon('ha')
                return self.send_json({'ok': True})
            return self.send_error(404)
        except subprocess.CalledProcessError as e:
            return self.send_json({'error': (e.stderr or e.stdout or 'failed')[-200:]}, 500)
        except Exception as e:
            return self.send_json({'error': str(e)[:200]}, 500)
