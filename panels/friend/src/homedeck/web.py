"""Every web address the panels use. GET/POST /api/... -> the modules; anything else -> a file from www/.

  GET  /api/health            is the server OK, and are the settings (homedeck.toml) OK? (homedeck-apply checks this)
  GET  /api/info              title, version, Home Assistant address and which optional parts are on (Start page)
  GET  /api/setup             first-run check: token set? Home Assistant reachable? what was found (rooms, people, ...)
  GET  /api/status            internet + Home Assistant summary
  GET  /api/settings          public settings + which secrets are set (never the secrets)
  POST /api/settings          {wallpaper, dim, temps[], accent, ha_token?}
  POST /api/wallpaper         raw image body -> stored, returns {name};  GET /wall/<name> the image
  GET  /api/art?e=<player>    album / show art (proxied from Home Assistant)
  POST /api/media             {action: play_pause|next|previous} (Spotify)
  GET  /api/home/state, POST /api/home/do   rooms, lights, door, people, players; allowed actions
  GET  /api/family, /api/presence           who is home and today's timeline (Home Assistant people)
  GET  /api/bus, /api/bus/stops?q=, /api/weather, /api/leave   Family info
  GET  /api/layout/<page>[/history], POST /api/layout/<page>   edit mode (Start, Family info)
  GET  /api/news?f=<feed>     SVT headlines (Start);  GET /api/links  status dots
  GET  /<page>                www/<page>.html for the pages in PAGES;  /  = Start (or /setup);  /ha, /editor  redirects
"""
import json, os, re, time, urllib.parse

from http.server import SimpleHTTPRequestHandler

from . import discover, family, home, layouts, leave, links, news, status, transit, weather
from .config import C, REPORT
from .ha import ha_call, ha_get, ha_states
from .store import SECRETS, SETTINGS, STATIC, WALLS, load, save, secret

PAGES = ('living', 'media', 'family', 'familyinfo', 'ambient', 'desktop', 'start', 'setup')
STARTED = time.time()


def setup_report():
    out = {'ha_url': C.HA, 'token_set': bool(secret('ha_token')), 'version': C.VERSION, 'connected': False,
           'ntfy_topic': secret('ntfy_topic')}
    if not out['token_set']:
        return out
    try:
        ha_get('/api/')
        out['connected'] = True
        states = ha_states(0) or []
        rooms = home.rooms_from(states)
        out['found'] = {
            'rooms': [{'room': r['room'], 'lights': len(r['lights'])} for r in rooms],
            'people': [p['attributes'].get('friendly_name', p['entity_id']) for p in discover.people(states)],
            'players': [label for _, label in discover.players(states)],
            'lock': discover.lock_entity(states) or None, 'weather': discover.weather_entity(states) or None,
            'areas_ok': not discover._cache.get('error'), 'areas_error': discover._cache.get('error')}
    except Exception as e:
        msg = str(e)
        out['error'] = 'the token was refused (401): make a new long-lived token' if '401' in msg else msg[:160]
    return out


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

    def redirect(self, to):
        self.send_response(302)
        self.send_header('Location', to)
        self.send_header('Content-Length', '0')
        self.end_headers()

    def body(self, limit=64 * 1024):
        n = int(self.headers.get('Content-Length') or 0)
        if n > limit:
            raise ValueError('too large')
        return self.rfile.read(n)

    def json_or_502(self, fn, limit=160):
        try:
            return self.send_json(fn())
        except PermissionError as e:
            return self.send_json({'configured': False, 'error': str(e)}, 503)
        except Exception as e:
            return self.send_json({'error': str(e)[:limit]}, 502)

    # ---------- GET ----------
    def do_GET(self):
        p = self.path
        path = p.split('?')[0]
        if p == '/api/health':
            return self.send_json({'ok': True, 'started': STARTED, 'version': C.VERSION, 'settings': REPORT})
        if p == '/api/info':
            return self.send_json({'title': C.TITLE, 'version': C.VERSION, 'ha_url': C.HA, 'token_set': bool(secret('ha_token')),
                                   'bus': bool(transit.bus_stop()), 'news': C.NEWS_ON and bool(C.NEWS_FEEDS)})
        if p == '/api/setup':
            return self.send_json(setup_report())
        if path == '/' or path == '':                      # first visit without a token -> setup, else Start
            return self.redirect('/start' if secret('ha_token') else '/setup')
        if path == '/ha':                                  # Start's Home Assistant card
            return self.redirect(C.HA + '/')
        if path == '/editor':                              # the panel editor on this server (port 8088)
            host = (self.headers.get('Host') or '').split(':')[0] or '127.0.0.1'
            return self.redirect(f'http://{host}:8088/')
        if p == '/api/status':
            return self.send_json(status.status())
        if p == '/api/family':
            return self.json_or_502(family.family_state)
        if p == '/api/presence':
            return self.json_or_502(family.presence_summary)
        if p == '/api/leave':
            return self.json_or_502(lambda: leave.leave_state(self.client_address[0]))
        m = re.fullmatch(r'/api/layout/(\w+)(/history)?', p)
        if m and m.group(1) in C.LAYOUT_PAGES:
            if m.group(2):
                return self.send_json([{'at': int(f.rsplit('-', 1)[1][:-5]) / 1000} for f in layouts.layout_history(m.group(1))])
            return self.send_json(layouts.layout_get(m.group(1)))
        if p.startswith('/api/bus/stops?'):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(p).query).get('q', [''])[0].strip()
            return self.json_or_502(lambda: transit.stop_search(q) if len(q) >= 2 else [], 120)
        m = re.fullmatch(r'/api/news\?f=([a-z]+)', p)
        if m and C.NEWS_ON and m.group(1) in C.NEWS_FEEDS:
            return self.json_or_502(lambda: news.news(m.group(1)), 120)
        if p == '/api/weather':
            return self.json_or_502(weather.weather_state)
        if p == '/api/bus':
            return self.json_or_502(transit.bus_state)
        if p == '/api/links':
            return self.send_json(links.link_status())
        if p == '/api/home/state':
            return self.json_or_502(home.home_state, 120)
        if path.strip('/') in PAGES:
            self.path = '/' + path.strip('/') + '.html'
            return super().do_GET()
        if p == '/api/settings':
            s, sec = load(SETTINGS, {}), load(SECRETS, {})
            return self.send_json({**s, 'ha_token_set': bool(sec.get('ha_token')), 'genelec_set': False,
                                   'walls': sorted(os.listdir(WALLS))})
        if p.startswith('/wall/'):
            name = os.path.basename(p[6:].split('?')[0])
            fpath = os.path.join(WALLS, name)
            if not re.fullmatch(r'wall-\d+\.(jpg|png|webp|gif)', name) or not os.path.exists(fpath):
                return self.send_error(404)
            with open(fpath, 'rb') as f:
                return self.send_bytes(f.read(), 'image/' + ('jpeg' if name.endswith('jpg') else name.rsplit('.', 1)[1]), 'max-age=31536000, immutable')
        if p.startswith('/api/art'):
            try:
                states = ha_states() or []
                ids = {e for e, _ in discover.players(states)}
                ent = urllib.parse.parse_qs(urllib.parse.urlparse(p).query).get('e', [discover.spotify(states)])[0]
                if ent not in ids:
                    return self.send_error(404)
                st = ha_get('/api/states/' + ent)
                data = ha_get(st['attributes']['entity_picture'], raw=True)
            except Exception:
                return self.send_error(404)
            return self.send_bytes(data, 'image/jpeg', 'max-age=300')
        if path.startswith('/api/'):
            return self.send_json({'error': 'not part of this Home Deck'}, 404)
        return super().do_GET()

    # ---------- POST ----------
    def do_POST(self):
        try:
            m = re.fullmatch(r'/api/layout/(\w+)', self.path)
            if m and m.group(1) in C.LAYOUT_PAGES:
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
            req = json.loads(self.body() or b'{}')
            if self.path == '/api/home/do':
                try:
                    home.home_do(req)
                except ValueError as e:
                    return self.send_json({'error': str(e)}, 400)
                return self.send_json({'ok': True})
            if self.path == '/api/settings':
                s, sec = load(SETTINGS, {}), load(SECRETS, {})
                for k in ('wallpaper', 'dim', 'blur', 'temps', 'accent', 'deck_mode'):
                    if k in req:
                        s[k] = req[k]
                if req.get('ha_token') is not None:
                    sec['ha_token'] = req['ha_token'].strip() or None
                if 'delete_wall' in req:
                    name = os.path.basename(req['delete_wall'])
                    if re.fullmatch(r'wall-\d+\.(jpg|png|webp|gif)', name) and os.path.exists(os.path.join(WALLS, name)):
                        os.remove(os.path.join(WALLS, name))
                save(SETTINGS, s)
                save(SECRETS, sec, private=True)
                status.refresh_soon('ha')
                discover._cache['at'] = 0
                return self.send_json({'ok': True})
            if self.path == '/api/media':
                svc = {'play_pause': 'media_play_pause', 'next': 'media_next_track', 'previous': 'media_previous_track'}.get(req.get('action'))
                sp = discover.spotify(ha_states() or [])
                if not svc or not sp:
                    return self.send_json({'error': 'unknown action' if not svc else 'no Spotify player in Home Assistant'}, 400)
                ha_call('media_player', svc, {'entity_id': sp})
                status.refresh_soon('ha')
                return self.send_json({'ok': True})
            return self.send_json({'error': 'not part of this Home Deck'}, 404)
        except Exception as e:
            return self.send_json({'error': str(e)[:200]}, 500)
