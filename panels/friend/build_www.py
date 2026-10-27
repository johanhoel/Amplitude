#!/usr/bin/env python3
"""Build the friend edition's www/ from the owner's current panel pages (pulled into homedeck-src/live/www).

Every change is an exact text replacement that must match once, so a later change to a source page makes this
script stop with a clear message instead of producing a half-converted page.
Usage: python3 build_www.py <live www dir> <output www dir>
"""
import os, re, shutil, sys

SRC, OUT = sys.argv[1], sys.argv[2]
PAGES = ['start', 'living', 'media', 'family', 'familyinfo', 'ambient', 'desktop']
COPY = ['edit.js', 'start.js', 'familyinfo-icon.png']
FRIEND_PANELS = ("[['/start', 'Start', 'all panels'], ['/living', 'Home', 'lights, music, door'], ['/media', 'Media', 'music, players'], "
                 "['/family', 'Family', \"who's home\"], ['/familyinfo', 'Family info', 'weather, buses'], ['/ambient', 'Ambient', 'night clock'], "
                 "['/desktop', 'Desktop', 'wallpaper']]")


def rep(text, old, new, page, count=1, regex=False):
    n = len(re.findall(old, text, re.S)) if regex else text.count(old)
    if n != count:
        raise SystemExit(f'{page}: expected {count} match(es) for {old[:70]!r}, found {n}')
    return re.sub(old, new, text, flags=re.S) if regex else text.replace(old, new)


def panels_list(text, page):
    return rep(text, r"const PANELS = \[\[.*?\]\];", 'const PANELS = ' + FRIEND_PANELS.replace('\\', '\\\\') + ';', page, regex=True)


def css(text, rules, page):
    return rep(text, '</style>', rules + '\n</style>', page)


def start(t):
    p = 'start'
    i, j = t.index('const GROUPS = ['), t.index('];\nconst esc =')
    t = t[:i] + """const GROUPS = [
  ['Everyday', 'the panels for the wall, the tablet, the phone and the computer', [
    ['living', '/living', 'Home', 'Lights by room, music, front door', 'home', '#fbbf24', 'feat'],
    ['media', '/media', 'Media', 'Music and media players', 'music', '#fb7185'],
    ['family', '/family', 'Family', "Who's home, today's timeline", 'people', '#34d399'],
    ['familyinfo', '/familyinfo', 'Family info', 'Weather, next buses, last one home', 'bus', '#22d3ee'],
    ['ambient', '/ambient', 'Ambient', 'Night clock for the bedside', 'moon', '#a78bfa'],
    ['desktop', '/desktop', 'Desktop', 'Computer wallpaper (Lively Wallpaper on Windows)', 'deck', '#6f8fe0'],
  ]],
  ['Settings', 'Home Assistant, editing and setup', [
    ['ha', '/ha', 'Home Assistant', 'Devices, automations, areas', 'ha', '#18bcf2', 'feat'],
    ['editor', '/editor', 'Panel editor', 'Edit the panels: code, live preview, history', 'keys', '#7c5cff'],
    ['editstart', '/start?edit', 'Edit this page', 'Move, rename, hide or add cards', 'grid', '#7c5cff'],
    ['setup', '/setup', 'Setup', 'Home Assistant token and what was found', 'box', '#6f8fe0'],
  ]],
""" + t[j:]
    t = rep(t, """<footer data-edit="foot" id="foot">LAN addresses: from outside the house, connect WireGuard first.<br>
    The Deck, Lab panel and Buttons web view share one Buttons surface: opening it on a second screen shows "Overtaken" on the first.</footer>""",
            """<footer data-edit="foot" id="foot">Home Deck · rooms, lights and people come from Home Assistant (put lights in areas there).<br>
    Add this page to the home screen of phones and tablets.</footer>""", p)
    # news only when switched on in homedeck.toml
    t = rep(t, '<script src="/edit.js"></script>', """<script src="/edit.js"></script>
<script>fetch('/api/info').then(r => r.json()).then(i => { if (!i.news) document.getElementById('news')?.remove();
  if (i.title) document.title = i.title; }).catch(() => {});</script>""", p)
    return t


def living(t):
    p = 'living'
    t = rep(t, '<nav><a href="/">Deck</a><a href="/living" class="on">Home</a><a href="/ops">Lab</a></nav>',
            '<nav><a href="/living" class="on">Home</a><a href="/media">Media</a><a href="/family">Family</a></nav>', p)
    # speakers (Genelec/Dante), motion alerts and charger belong to the original house: hidden, the scripts stay intact
    t = css(t, '#dial, #spk, #src, #power, #detect, #charger { display: none !important; }', p)
    return t


def media(t):
    p = 'media'
    t = panels_list(t, p)
    # the main player: any Spotify player in Home Assistant (no fixed account); no Apple TV remote here
    t = rep(t, "const SPOTIFY = 'media_player.spotify_alex', ATV = 'media_player.vardagsrum';",
            "const isSpot = id => (id || '').startsWith('media_player.spotify'), ATV = '';", p)
    t = rep(t, 'p.id === SPOTIFY', 'isSpot(p.id)', p, count=2)
    t = rep(t, 'p.id !== SPOTIFY', '!isSpot(p.id)', p, count=2)
    t = css(t, 'section.tv, section.spk, #tvapps, .cap.hide-friend { display: none !important; }', p)
    t = rep(t, '<div class="cap">Living room TV</div>', '<div class="cap hide-friend">Living room TV</div>', p)
    t = rep(t, '<div class="cap">Genelec speakers</div>', '<div class="cap hide-friend">Genelec speakers</div>', p)
    t = rep(t, '<div class="cap">Rooms</div>', '<div class="cap">Other players</div>', p)
    return t


def family(t):
    p = 'family'
    t = panels_list(t, p)
    t = rep(t, "const COL = { Alex: '#7c5cff', Robin: '#ff6fb5', Sam: '#34d399', Kim: '#fbbf24' };",
            "const PALETTE = ['#7c5cff', '#34d399', '#ff6fb5', '#fbbf24', '#22d3ee', '#f97316', '#a78bfa', '#fb7185'], COL = {};", p)
    t = css(t, '[hidden] { display: none !important; }', p)
    t = rep(t, "function render(d) {", "function render(d) {\n  d.people.forEach((p, i) => { COL[p.name] = COL[p.name] || PALETTE[i % PALETTE.length]; });", p)
    t = rep(t, """  <div class="cap">At the front door today</div>
  <section class="door" id="door"><span class="empty">Nobody recognised by the camera yet today.</span></section>
  <div class="cap">Online today</div>
  <section class="acts" id="acts"></section>""",
            """  <section class="door" id="door" hidden></section>
  <section class="acts" id="acts" hidden></section>""", p)
    return t


def familyinfo(t):
    p = 'familyinfo'
    t = rep(t, """  $('#deps').innerHTML = deps.length ? deps.map(d => {""",
            """  if (bus.configured === false) {          // no bus stop chosen yet
    $('#deps').innerHTML = '<span class="empty">No bus stop chosen yet. <a href="/familyinfo?edit" style="color:inherit">Edit this page</a> '
      + 'and tap the bus section to pick a Västtrafik stop (or hide the section).</span>';
    $('#arrs').innerHTML = ''; return;
  }
  $('#deps').innerHTML = deps.length ? deps.map(d => {""", p)
    return t


def ambient(t):
    t = panels_list(t, 'ambient')
    return css(t, '#alerts { display: none !important; }', 'ambient')   # camera alerts belong to the original house


def desktop(t):
    p = 'desktop'
    t = rep(t, 'URL http://192.168.1.52/desktop', 'URL http://THIS-SERVER/desktop', p)
    # no lab service or camera here: those two cards stay hidden; PC status is not known
    t = rep(t, '<section class="card"><h3><span>Front camera</span>', '<section class="card hide"><h3><span>Front camera</span>', p)
    t = rep(t, '<section class="card"><h3><span>Lab</span>', '<section class="card hide"><h3><span>Lab</span>', p)
    t = rep(t, '<span>PC <b id="pc">–</b></span>', '', p)
    t = rep(t, "  $('#pc').textContent = st.pc_online ? 'on' : 'off';\n", '', p)
    t = rep(t, "every(home, 30); every(camera, 30); every(lab, 60); every(bus, 60); every(weather, 600);",
            "every(home, 30); every(bus, 60); every(weather, 600);", p)
    t = rep(t, '  const b = await get(\'/api/bus\');\n', "  const b = await get('/api/bus');\n  if (b.configured === false) return $('#buscard').classList.add('hide');\n", p)
    return t


def panels_js(t):
    return panels_list(t.replace("  const PANELS = ", "const PANELS = ", 1), 'panels.js').replace("const PANELS = ", "  const PANELS = ", 1)


CONVERT = {'start': start, 'living': living, 'media': media, 'family': family, 'familyinfo': familyinfo, 'ambient': ambient, 'desktop': desktop}

os.makedirs(OUT, exist_ok=True)
for page in PAGES:
    with open(os.path.join(SRC, page + '.html'), encoding='utf-8') as f:
        t = f.read()
    t = CONVERT[page](t)
    t = re.sub(r'[ \t]*<script src="/(cam|nav)\.js"[^>]*></script>\n?', '', t)   # owner-only: live camera popup, ring-panel nav
    with open(os.path.join(OUT, page + '.html'), 'w', encoding='utf-8') as f:
        f.write(t)
for name in COPY:
    shutil.copy(os.path.join(SRC, name), os.path.join(OUT, name))
with open(os.path.join(SRC, 'panels.js'), encoding='utf-8') as f:
    pj = f.read()
with open(os.path.join(OUT, 'panels.js'), 'w', encoding='utf-8') as f:
    f.write(panels_js(pj))
for name in os.listdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'extra')):   # friend-only pages (setup)
    shutil.copy(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'extra', name), os.path.join(OUT, name))
print('built', len(PAGES), 'pages +', len(COPY) + 1, 'files + extra ->', OUT)
