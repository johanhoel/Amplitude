/* Home Deck modules: the building blocks for your own dashboards (/boards, /board/<name>).
 *
 * A module is one card on a board. Each one is a definition in MODULES below:
 *   name, icon, desc     shown in the "Add module" list
 *   size                 default size: s (1×1), m (2×1), t (1×2), l (2×2), w (whole row), W (whole row, 2 high),
 *                        c (corner: floats in the bottom corner on wallpaper boards, e.g. the desktop clock)
 *   need                 extra data it reads besides the house (home, status, bus, wx come with every board):
 *                        family, visits, news, presence, ops   (fetched only when a module on the board needs them)
 *   cfg(D)               its settings: [{key, label, type: text|select|toggle, options: [[value, label]], value}]
 *                        (D = the current data, so a setting can offer e.g. the rooms or players that exist)
 *   bare                 true = no card frame (spacer, heading, image); style(c) = extra CSS for the card (coloured panel)
 *   render(el, D, c, sz) draws the card into el. c = its settings, sz = its size. Buttons use Wall.press / Wall.arm,
 *                        so a press never fires by accident and risky ones (lock, vacuum) need a second tap.
 * Live data: Wall.data (every 8 s) + the extras below. A card is redrawn on every update, never under a finger.
 * To add a module: add an entry to MODULES; it appears in "Add module" on every board at once.
 */
window.Deck = (() => {
  const { esc, hm, WX, WXT } = Wall;
  const D = {};
  const subs = [];
  const emit = () => subs.forEach(f => f(D));

  // ---- extra data, polled only while a module on the page needs it ----
  const EXTRA = { family: ['/api/family', 60000], visits: ['/api/sec/visits', 30000], news: ['/api/news?f=vast', 600000],
                  presence: ['/api/presence', 30000], ops: ['/api/ops/snapshot', 60000],
                  watched: ['/api/watched', 60000] };
  const polling = {};
  function need(keys) {
    keys.forEach(k => {
      if (polling[k] || !EXTRA[k]) return;
      const [url, ms] = EXTRA[k];
      const get = async () => { if (document.visibilityState !== 'visible') return;
        try { const r = await fetch(url, { cache: 'no-store' }); if (r.ok) { D[k] = await r.json(); emit(); } } catch {} };
      polling[k] = setInterval(get, ms); get();
    });
  }
  Wall.data(w => { Object.assign(D, w); emit(); });
  const data = cb => { subs.push(cb); if (Object.keys(D).length) cb(D); };

  // ---- one clock for every card that shows the time ----
  setInterval(() => document.querySelectorAll('[data-clock]').forEach(el => {
    const d = new Date(), f = el.dataset.clock;
    el.textContent = f === 'date' || f === 'dategb' ? d.toLocaleDateString(f === 'dategb' ? 'en-GB' : [], { weekday: 'long', day: 'numeric', month: 'long' })
      : d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: f === 'sec' ? '2-digit' : undefined, hour12: false });
  }), 1000);

  // ---- small helpers for the cards ----
  const head = (icon, title, right = '') => `<div class="mh"><span class="mi">${icon}</span><span class="mt">${esc(title)}</span><span class="mr">${right}</span></div>`;
  const empty = t => `<div class="me">${esc(t)}</div>`;
  const big = (v, unit = '') => `<div class="mbig">${v}<small>${unit}</small></div>`;
  const btn = (attr, label, cls = '') => `<button class="mbtn ${cls}" ${attr}><span class="klabel">${esc(label)}</span></button>`;
  const roomsOf = D => (D.home?.rooms || []).map(r => [r.room, r.room]);
  const playersOf = D => (D.home?.players || []).map(p => [p.id, p.label]);
  const ago = t => { const s = (Date.now() - new Date(t)) / 1000; return s < 90 ? 'just now' : s < 3600 ? Math.round(s / 60) + ' min ago' : hm(t); };
  const agoS = s => s < 90 ? 'just now' : s < 5400 ? Math.round(s / 60) + ' min ago' : s < 172800 ? Math.round(s / 3600) + ' h ago' : Math.round(s / 86400) + ' d ago';
  const hide = (el, h) => { const m = el.closest('.mod'); if (m && !document.body.classList.contains('editing')) m.hidden = h; };
  const ACTIONS = {
    all_off: ['💡', 'All lights off', { do: 'all_off' }, false, 'All lights off'],
    lock: ['🔒', 'Lock front door', { do: 'lock' }, true, 'Locking…'],
    wake_pc: ['🖥️', 'Wake PC', { do: 'wake_pc' }, false, 'PC waking'],
    vac_start: ['🧹', 'Start vacuum', { do: 'vacuum', value: 'start' }, true, 'Vacuum started'],
    vac_home: ['🏠', 'Vacuum home', { do: 'vacuum', value: 'return_to_base' }, false, 'Vacuum going home'],
  };

  const MODULES = {
    clock: {
      name: 'Clock', icon: '🕒', desc: 'Time and date', size: 'm',
      cfg: () => [{ key: 'sec', label: 'Show seconds', type: 'toggle' }],
      render(el, D, c) {
        el.innerHTML = `<div class="mclock" data-clock="${c.sec ? 'sec' : 'min'}"></div><div class="msub" data-clock="date"></div>`;
      },
    },
    weather: {
      name: 'Weather', icon: '⛅', desc: 'Now, and the next hours on wider cards', size: 'm',
      render(el, D, c, sz) {
        const w = D.wx?.now; if (!w) return el.innerHTML = head('⛅', 'Weather') + empty('No weather yet');
        const hours = (D.wx.hourly || []).slice(1, sz === 's' || sz === 't' ? 1 : sz === 'm' ? 5 : 9);
        el.innerHTML = head(WX[w.condition] || '⛅', WXT[w.condition] || w.condition) + big(Math.round(w.temperature), '°')
          + `<div class="msub">Wind ${Math.round((w.wind_speed || 0) / 3.6)} m/s${w.humidity != null ? ' · ' + w.humidity + ' %' : ''}</div>`
          + (hours.length ? `<div class="mrow">${hours.map(h => `<div class="mhour"><small>${hm(h.datetime).slice(0, 2)}</small><span>${WX[h.condition] || ''}</span><b>${Math.round(h.temperature)}°</b></div>`).join('')}</div>` : '');
      },
    },
    people: {
      name: "Who's home", icon: '👪', desc: 'Everyone in the family, home or away', size: 'm',
      render(el, D) {
        const p = D.home?.people || [];
        el.innerHTML = head('👪', "Who's home", `${p.filter(x => x.home).length}/${p.length}`)
          + `<div class="mpeople">${p.map(x => `<span class="mp ${x.home ? 'on' : ''}"><i></i>${esc(x.name)}</span>`).join('') || empty('No people')}</div>`;
      },
    },
    room: {
      name: 'Room lights', icon: '💡', desc: 'Tap a light to switch it; one room per card', size: 'l',
      cfg: D => [{ key: 'room', label: 'Room', type: 'select', options: roomsOf(D) }],
      render(el, D, c) {
        const r = (D.home?.rooms || []).find(x => x.room === c.room) || (D.home?.rooms || [])[0];
        if (!r) return el.innerHTML = head('💡', c.room || 'Room') + empty('Room not found');
        const lights = r.lights.filter(l => !(l.name === 'All' && r.lights.length > 1));
        const on = lights.filter(Wall.light).length;
        el.innerHTML = head('💡', r.room, `${on}/${lights.length}`) + `<div class="mlights">${lights.map((l, i) =>
          `<button class="ml ${Wall.light(l) ? 'on' : ''}" data-i="${i}" data-id="${esc(l.id)}">${esc(l.name)}</button>`).join('')}</div>`;
        el.querySelectorAll('.ml').forEach(b => Wall.press(b, () => Wall.toggle(lights[+b.dataset.i], () => this.render(el, D, c))));
      },
    },
    lights: {
      name: 'Lights summary', icon: '🔆', desc: 'How many lights are on, with All off', size: 's',
      render(el, D) {
        const rooms = D.home?.rooms || [], on = rooms.reduce((a, r) => a + r.lights.filter(l => l.name !== 'All' && Wall.light(l)).length, 0);
        el.innerHTML = head('🔆', 'Lights') + big(on, ' on') + btn('data-t="alloff"', 'All off');
        Wall.arm(el.querySelector('.mbtn'), () => Wall.act('/api/home/do', { do: 'all_off' }, 'All lights off'));
      },
    },
    door: {
      name: 'Front door', icon: '🚪', desc: 'Lock state; Lock needs a second tap (unlocking stays in the lock app)', size: 's',
      render(el, D) {
        const st = D.home?.door?.state || 'unknown';
        el.innerHTML = head('🚪', 'Front door') + `<div class="mstate ${st === 'locked' ? 'ok' : st === 'unlocked' ? 'warn' : ''}">${esc(st)}</div>`
          + (st !== 'locked' ? btn('data-t="lock"', 'Lock') : '');
        const b = el.querySelector('.mbtn'); if (b) Wall.arm(b, () => Wall.act('/api/home/do', { do: 'lock' }, 'Locking…'));
      },
    },
    bus: {
      name: 'Buses', icon: '🚌', desc: 'Next departures from the stop chosen on Family info', size: 'm',
      cfg: () => [{ key: 'n', label: 'Departures', type: 'select', options: [['2', '2'], ['3', '3'], ['4', '4'], ['6', '6']], value: '3' },
                  { key: 'then', label: 'Also show the bus after', type: 'toggle', value: true }],
      render(el, D, c) {
        const then = d => { const t = d.then?.time && d.then.time !== d.t.time ? Math.max(0, Math.round((new Date(d.then.time) - Date.now()) / 60000)) : null;
          return t != null && c.then !== false ? `<small class="mthen">then ${t}</small>` : ''; };
        const deps = (D.bus?.departures || []).map(x => ({ ...x, t: [x.next, x.then].find(y => y?.time && new Date(y.time) > Date.now() - 30000) }))
          .filter(x => x.t).sort((a, b) => new Date(a.t.time) - new Date(b.t.time)).slice(0, +(c.n || 3));
        el.innerHTML = head('🚌', D.bus?.stop || 'Buses') + (deps.length ? `<div class="mlist">${deps.map(d => {
          const min = Math.max(0, Math.floor((new Date(d.t.time) - Date.now()) / 60000));
          return `<div><span class="mline" style="background:${esc(d.line.backgroundColor)};color:${esc(d.line.textColor)}">${esc(d.line.shortName)}</span>
            <span class="mgrow">${esc(d.to)}</span><b>${min < 1 ? 'now' : min + ' min'}${then(d)}</b></div>`; }).join('')}</div>` : empty('No departures'));
      },
    },
    media: {
      name: 'Media player', icon: '🎵', desc: 'Now playing with play/pause and skip', size: 'm',
      cfg: D => [{ key: 'player', label: 'Player', type: 'select', options: [['', 'Whatever is playing'], ...playersOf(D)] },
                  { key: 'hide_idle', label: 'Hide the card when nothing plays', type: 'toggle' }],
      render(el, D, c, sz) {
        const pl = D.home?.players || [];
        const p = c.player ? pl.find(x => x.id === c.player) : pl.find(x => x.state === 'playing' && x.title) || pl[0];
        hide(el, !!c.hide_idle && !(p && p.state === 'playing'));
        if (!p) return el.innerHTML = head('🎵', 'Media') + empty('No players');
        const art = p.art ? `<img class="mart" src="/api/art?e=${encodeURIComponent(p.id)}&k=${encodeURIComponent(p.art_key)}" alt="">` : '';
        el.innerHTML = head('🎵', p.label, esc(p.state)) + `<div class="mmedia">${sz === 's' ? '' : art}<div class="mgrow"><b>${esc(p.title || '—')}</b><div class="msub">${esc(p.artist || p.app || '')}</div></div></div>`
          + `<div class="mctl">${['media_previous_track', 'media_play_pause', 'media_next_track'].map((v, i) => `<button class="mbtn" data-t="${v}" data-v="${v}">${['⏮', p.state === 'playing' ? '⏸' : '▶', '⏭'][i]}</button>`).join('')}</div>`;
        el.querySelectorAll('.mctl .mbtn').forEach(b => Wall.press(b, () => Wall.act('/api/home/do', { do: 'mp', entity: p.id, value: b.dataset.v })));
      },
    },
    button: {
      name: 'Action button', icon: '🔘', desc: 'One tap for a house action (all off, lock, wake PC, vacuum)', size: 's',
      cfg: () => [{ key: 'action', label: 'Action', type: 'select', options: Object.entries(ACTIONS).map(([k, a]) => [k, a[0] + ' ' + a[1]]) },
                  { key: 'label', label: 'Label (optional)', type: 'text' }],
      render(el, D, c) {
        const a = ACTIONS[c.action] || ACTIONS.all_off;
        el.innerHTML = `<button class="mbig-btn" data-t="act-${esc(c.action)}"><span class="mbi">${a[0]}</span><span class="klabel">${esc(c.label || a[1])}</span></button>`;
        (a[3] ? Wall.arm : Wall.press)(el.querySelector('button'), () => Wall.act('/api/home/do', a[2], a[4]));
      },
    },
    vacuum: {
      name: 'Vacuum', icon: '🧹', desc: 'State and battery; start (second tap) or send home', size: 's',
      render(el, D) {
        const v = D.home?.vacuum || {};
        el.innerHTML = head('🧹', 'Vacuum', v.battery != null ? v.battery + ' %' : '') + `<div class="mstate">${esc(v.state || 'unknown')}</div>`
          + `<div class="mctl">${btn('data-t="vs"', 'Start')}${btn('data-t="vh"', 'Home')}</div>`;
        const [s, h] = el.querySelectorAll('.mbtn');
        Wall.arm(s, () => Wall.act('/api/home/do', { do: 'vacuum', value: 'start' }, 'Vacuum started'));
        Wall.press(h, () => Wall.act('/api/home/do', { do: 'vacuum', value: 'return_to_base' }, 'Vacuum going home'));
      },
    },
    camera: {
      name: 'Front camera', icon: '📷', desc: 'The latest visit at the front door: a big photo, or a small one with the details', size: 'l', need: ['visits'],
      cfg: () => [{ key: 'layout', label: 'Look', type: 'select', options: [['photo', 'Big photo'], ['row', 'Small photo + details (desktop)']], value: 'photo' }],
      render(el, D, c) {
        const v = (D.visits || []).find(x => !x.test && x.has_jpg);
        if (!v) return el.innerHTML = head('📷', 'Front camera') + empty('No visits yet');
        const names = (v.people || []).map(p => p.name || p), lab = v.labels || [];
        const who = names.length ? names.join(', ') : v.plates?.length ? 'Car ' + v.plates.map(p => p.plate || p).join(', ')
          : lab.length ? lab[0][0].toUpperCase() + lab[0].slice(1) + (lab.length > 1 ? ' + ' + lab.slice(1).join(', ') : '') : 'Motion';
        if (c.layout === 'row') {
          const t = new Date(v.start), dur = Math.max(1, Math.round((new Date(v.end) - t) / 1000));
          return el.innerHTML = head('📷', 'Front camera', ago(v.start)) + `<div class="mcamrow" onclick="location.href='/cameras'" style="cursor:pointer"><img src="/api/sec/thumb/${esc(v.day)}/${esc(v.stem)}.jpg?w=480" alt="">
            <div><div class="mwhat">${esc(who)}</div><div class="msub">${hm(t)} · ${dur} s${v.unknown ? ` · ${v.unknown} unknown face${v.unknown > 1 ? 's' : ''}` : ''}</div></div></div>`;
        }
        el.innerHTML = `<a href="/cameras" aria-label="All recordings"><img class="mcam" src="/api/sec/thumb/${esc(v.day)}/${esc(v.stem)}.jpg?w=640" alt="">`
          + `<div class="mcamcap"><b>${esc(who || 'Visit')}</b><span>${ago(v.start)}</span></div></a>`;
      },
    },
    temps: {
      name: 'Temperatures', icon: '🌡️', desc: 'Temperature sensors from Home Assistant', size: 'm',
      cfg: () => [{ key: 'filter', label: 'Only sensors whose name contains (optional)', type: 'text' }],
      render(el, D, c) {
        const f = (c.filter || '').toLowerCase();
        const t = (D.home?.temps || []).filter(x => !f || x.name.toLowerCase().includes(f)).slice(0, 6);
        el.innerHTML = head('🌡️', 'Temperatures', D.home?.outside != null ? `out ${Math.round(D.home.outside)}°` : '')
          + (t.length ? `<div class="mlist">${t.map(x => `<div><span class="mgrow">${esc(x.name.replace(/ ?temperature$/i, ''))}</span><b>${x.value.toFixed(1)}°</b></div>`).join('')}</div>` : empty('No sensors'));
      },
    },
    lab: {
      name: 'Lab status', icon: '🖧', desc: 'Internet, PC and Home Assistant at a glance', size: 's',
      render(el, D) {
        const s = D.status || {};
        const row = (ok, t, v) => `<div><i class="mdot ${ok ? 'ok' : 'bad'}"></i><span class="mgrow">${t}</span><b>${v}</b></div>`;
        el.innerHTML = head('🖧', 'Lab') + `<div class="mlist">${row(s.internet_ms != null, 'Internet', s.internet_ms != null ? s.internet_ms + ' ms' : 'down')}
          ${row(s.pc_online, 'PC', s.pc_online ? 'on' : 'off')}${row(s.ha?.configured, 'Home Assistant', s.ha?.configured ? 'ok' : '—')}</div>`;
      },
    },
    news: {
      name: 'News', icon: '📰', desc: 'Latest headlines (SVT Väst)', size: 'w', need: ['news'],
      cfg: () => [{ key: 'n', label: 'Headlines', type: 'select', options: [['3', '3'], ['5', '5'], ['8', '8']], value: '3' }],
      render(el, D, c) {
        const it = (D.news?.items || []).slice(0, +(c.n || 3));
        el.innerHTML = head('📰', 'News') + (it.length ? `<div class="mlist mnews">${it.map(x => `<a href="${esc(x.link)}" target="_blank" rel="noopener">${esc(x.title)}</a>`).join('')}</div>` : empty('No headlines'));
      },
    },
    family: {
      name: 'Arrivals today', icon: '🏠', desc: 'When each person came home or left today', size: 'm', need: ['family'],
      render(el, D) {
        const p = D.family?.people || [];
        el.innerHTML = head('🏠', 'Today') + (p.length ? `<div class="mlist">${p.map(x => `<div><i class="mdot ${x.home ? 'ok' : ''}"></i><span class="mgrow">${esc(x.name)}</span>
          <b>${x.since ? (x.home ? 'home ' : 'left ') + hm(x.since * 1000) : x.home ? 'home all day' : 'away'}</b></div>`).join('')}</div>` : empty('No data'));
      },
    },
    charger: {
      name: 'Car charger', icon: '🔌', desc: 'Charging power right now', size: 's',
      render(el, D) {
        const w = D.home?.charger_w;
        el.innerHTML = head('🔌', 'Charger') + (w != null ? big(Number(w).toFixed(1), ' ' + esc(D.home.charger_unit || 'kW')) + `<div class="msub">${w > 0 ? 'charging' : 'idle'}</div>` : empty('No charger'));
      },
    },
    deskclock: {
      name: 'Desktop clock', icon: '🕰️', desc: 'Big clock, date and weather with the next hours (the desktop wallpaper clock)', size: 'c',
      render(el, D) {
        const w = D.wx?.now || D.home?.wx, now = Date.now();
        const hours = (D.wx?.hourly || []).filter(h => new Date(h.datetime) > now).filter((_, i) => i % 3 === 0).slice(0, 5);
        el.innerHTML = `<div class="dclock" data-clock="min"></div><div class="ddate" data-clock="dategb"></div>`
          + (w ? `<div class="dwx"><div class="dt">${Math.round(w.temperature)}°</div><div class="dc">${esc(WXT[w.condition] || w.condition || '')}<br>wind ${Math.round((w.wind_speed || 0) / 3.6)} m/s</div>`
          + `<div class="dhours">${hours.map(h => `<div>${new Date(h.datetime).getHours()}:00<b>${Math.round(h.temperature)}°</b><i>${h.precipitation >= .2 ? h.precipitation.toFixed(1) + ' mm' : ''}</i></div>`).join('')}</div></div>` : '');
        const d = new Date(); el.querySelector('.dclock').textContent = hm(d);
        el.querySelector('.ddate').textContent = d.toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long' });
      },
    },
    home: {
      name: 'Home overview', icon: '🏡', desc: 'Everyone with how long they have been away, plus door, lights and PC', size: 'm', need: ['presence'],
      render(el, D) {
        const h = D.home || {}, pr = D.presence || {}, people = h.people || [], n = people.filter(p => p.home).length;
        const on = (h.rooms || []).reduce((a, r) => a + r.lights.filter(l => l.name !== 'All' && Wall.light(l)).length, 0), door = h.door?.state;
        el.innerHTML = head('🏡', 'Home', n ? n + ' home' : 'nobody home') + `<div class="mav">${people.map(p => { const q = pr[p.name.toLowerCase()] || {};
            const sub = p.home ? 'home' : q.silent_s != null ? 'away · ' + agoS(q.silent_s).replace(' ago', '') : 'away';
            return `<div class="${p.home ? 'on' : ''}"><span>${esc(p.name[0])}</span><b>${esc(p.name)}</b><small>${esc(sub)}</small></div>`; }).join('')}</div>`
          + `<div class="mhomeline"><span>Door <b class="${door === 'unlocked' ? 'warn' : ''}">${esc(door || '–')}</b></span><span>Lights <b>${on ? on + ' on' : 'all off'}</b></span>`
          + `<span>PC <b>${D.status?.pc_online ? 'on' : 'off'}</b></span></div>`;
      },
    },
    labfull: {
      name: 'Lab overview', icon: '🧪', desc: 'Problems, ping, speed, ads blocked, last backup and every Proxmox node', size: 'm', need: ['ops'],
      render(el, D) {
        const s = D.ops; if (!s) return el.innerHTML = head('🧪', 'Lab') + empty('Waiting for the lab…');
        const probs = s.problems || [], n = s.net || {}, d = s.dns || {}, b = s.backups || {}, g = s.guests || [];
        el.innerHTML = head('🧪', 'Lab', `${g.filter(x => x.status === 'running').length}/${g.length} guests running`)
          + `<div class="mlabhead"><i class="mdot ${probs.length ? 'bad' : 'ok'}"></i>${probs.length ? `${probs.length} problem${probs.length > 1 ? 's' : ''}: ${esc(probs.slice(0, 3).join(', '))}` : 'All good'}</div>`
          + `<div class="mstats"><div><b>${n.ping != null ? Math.round(n.ping * 1000) + ' ms' : '–'}</b>ping</div><div><b>${n.down ? Math.round(n.down / 1e6) : '–'}</b>Mbit/s down</div>`
          + `<div><b>${d.blocked_pct != null ? Math.round(d.blocked_pct) + '%' : '–'}</b>ads blocked</div><div><b>${b.newest ? agoS(Date.now() / 1000 - b.newest).replace(' ago', '') : '–'}</b>last backup</div></div>`
          + `<div class="mnodes">${(s.nodes || []).map(x => { const mem = x.maxmem ? 100 * x.mem / x.maxmem : 0, col = mem > 90 ? 'var(--bad)' : mem > 80 ? 'var(--warn)' : x.color || 'var(--accent)';
              return `<div><span>${esc(x.node)}</span><div class="mbar"><i style="width:${Math.min(100, mem).toFixed(0)}%;background:${esc(col)}"></i></div>`
                + `<span>${x.status === 'online' ? `CPU ${(100 * (x.cpu || 0)).toFixed(0)}% · RAM ${mem.toFixed(0)}%` : 'OFFLINE'}</span></div>`; }).join('')}</div>`;
      },
    },
    devices: {
      name: 'Device status', icon: '🟢', desc: 'Online / offline for devices you watch in Studio (servers, NAS, TV, printer…)', size: 'm', need: ['watched'],
      cfg: D => [{ key: 'only', label: 'Show', type: 'select', value: '', options: [['', 'All watched devices'], ['down', 'Only the ones that are offline'],
        ...(D.watched || []).map(w => [w.key, w.name])] }],
      render(el, D, c) {
        let w = D.watched || [];
        if (c.only === 'down') w = w.filter(x => x.online === false); else if (c.only) w = w.filter(x => x.key === c.only);
        const down = (D.watched || []).filter(x => x.online === false).length;
        el.innerHTML = head('🟢', 'Devices', down ? `${down} offline` : 'all online') + (w.length ? `<div class="mlist">${w.map(x => `<div><i class="mdot ${x.online ? 'ok' : x.online === false ? 'bad' : ''}"></i>
          <span class="mgrow">${esc(x.name)}</span><b>${x.online ? 'online' : x.online === false ? (x.down_since ? 'off ' + agoS(Date.now() / 1000 - x.down_since).replace(' ago', '') : 'offline') : '–'}</b></div>`).join('')}</div>`
          : empty(c.only === 'down' ? 'Everything is online' : 'Watch devices in Studio to see them here'));
      },
    },
    spacer: {
      name: 'Empty space', icon: '⬚', desc: 'An invisible box that only takes up room, to place other cards where you want them', size: 's', bare: true,
      render(el) { el.innerHTML = document.body.classList.contains('editing') ? '<div class="me">empty space</div>' : ''; },
    },
    heading: {
      name: 'Heading', icon: '🔤', desc: 'A title across the board, like "Downstairs" or "Lab"', size: 'w', bare: true,
      cfg: () => [{ key: 'text', label: 'Heading', type: 'text', value: 'Heading' }, { key: 'sub', label: 'Smaller line under it (optional)', type: 'text' },
                  { key: 'align', label: 'Align', type: 'select', options: [['left', 'Left'], ['center', 'Centre'], ['right', 'Right']], value: 'left' }],
      render(el, D, c) { el.innerHTML = `<div class="mhead" style="text-align:${esc(c.align || 'left')}"><b>${esc(c.text || 'Heading')}</b>${c.sub ? `<span>${esc(c.sub)}</span>` : ''}</div>`; },
    },
    panel: {
      name: 'Coloured box', icon: '🟦', desc: 'A box in your own colour with a title and text, for grouping or decoration', size: 'm',
      cfg: () => [{ key: 'title', label: 'Title (optional)', type: 'text' }, { key: 'text', label: 'Text (optional)', type: 'textarea' },
                  { key: 'color', label: 'Colour', type: 'select', value: '#1e3a5f', options: [['#1e3a5f', 'Blue'], ['#14532d', 'Green'], ['#7c2d12', 'Rust'], ['#581c87', 'Purple'],
                    ['#713f12', 'Amber'], ['#831843', 'Pink'], ['#334155', 'Slate'], ['#0b0e12', 'Black'], ['transparent', 'No colour (frame only)']] },
                  { key: 'custom', label: 'Or your own colour (#rrggbb, optional)', type: 'text' }],
      style: c => { const col = /^#[0-9a-f]{6}$/i.test(c.custom || '') ? c.custom : c.color || '#1e3a5f'; return `background:${col} !important;border-color:${col === 'transparent' ? 'var(--line)' : col} !important`; },
      render(el, D, c) { el.innerHTML = (c.title ? `<div class="mpt">${esc(c.title)}</div>` : '') + (c.text ? `<div class="mnote">${esc(c.text)}</div>` : ''); },
    },
    image: {
      name: 'Image', icon: '🖼️', desc: 'A picture: a logo, a photo or a floor plan (upload under More… → Upload an image)', size: 'l', bare: true,
      cfg: D => [{ key: 'src', label: 'Image', type: 'select', options: [['', '— pick an uploaded image —'], ...(D.walls || []).map(w => ['/wall/' + w, w])] },
                 { key: 'url', label: 'Or an image address (https://… or /…)', type: 'url' },
                 { key: 'fit', label: 'Fit', type: 'select', options: [['cover', 'Fill the box (may crop)'], ['contain', 'Whole picture']], value: 'cover' },
                 { key: 'caption', label: 'Caption (optional)', type: 'text' }],
      render(el, D, c) {
        const src = c.url || c.src;
        el.innerHTML = src ? `<img class="mimg" style="object-fit:${c.fit === 'contain' ? 'contain' : 'cover'}" src="${esc(src)}" alt="">${c.caption ? `<div class="mcamcap"><b>${esc(c.caption)}</b></div>` : ''}`
          : '<div class="me">No image chosen</div>';
      },
    },
    note: {
      name: 'Note', icon: '📝', desc: 'Your own text: a reminder, the Wi-Fi name, a shopping list…', size: 'm',
      cfg: () => [{ key: 'title', label: 'Title', type: 'text' }, { key: 'text', label: 'Text', type: 'textarea' }],
      render(el, D, c) { el.innerHTML = head('📝', c.title || 'Note') + `<div class="mnote">${esc(c.text || 'Edit the board to write here.')}</div>`; },
    },
    link: {
      name: 'Link', icon: '🔗', desc: 'A big button that opens another panel or page', size: 's',
      cfg: () => [{ key: 'label', label: 'Label', type: 'text' }, { key: 'url', label: 'Address (e.g. /living or https://…)', type: 'url' },
                  { key: 'icon', label: 'Icon (an emoji)', type: 'text' }],
      render(el, D, c) {
        el.innerHTML = `<a class="mbig-btn" href="${esc(c.url || '/start')}"><span class="mbi">${esc(c.icon || '🔗')}</span><span>${esc(c.label || c.url || 'Link')}</span></a>`;
      },
    },
  };

  const SIZES = { x: ['Custom (dragged)', 0, 0], s: ['Small', 1, 1], m: ['Wide', 2, 1], t: ['Tall', 1, 2], l: ['Large', 2, 2], w: ['Full row', 0, 1], W: ['Full row, tall', 0, 2],
                  c: ['Corner (wallpaper boards)', 2, 2] };
  return { MODULES, SIZES, data, need, D };
})();
