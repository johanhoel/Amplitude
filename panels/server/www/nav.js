/* Home Deck smart navigation - include with <script src="/nav.js" defer></script> (never on family-only pages).
 *
 * PAGE LIST: the PANELS array right below is the only place pages are listed (friend edition: swap it there).
 *   ring: true  -> part of the swipe ring (Pulse -> Today -> Rooms -> Control -> Atlas -> Pulse).
 * What it adds:
 *   - a small orb at the bottom: current panel + its ring neighbours; tap it (or ⌘K / Ctrl+K / "/") for the launcher
 *   - launcher: search (title, description, keywords), Recent (this device), Related (page's <meta name="nav-related">), all panels
 *   - ring navigation: swipe in from the left/right screen edge, or ← / → on a keyboard (not while typing)
 *   - <meta name="nav-related" content="/media,/security"> on a page lists its related panels
 *   - camera popup (cam.js, loaded from here): the camera button in the orb or "Camera live" in the launcher; auto-popup on camera events
 */
(() => {
  const PANELS = [
    { p: '/pulse', t: 'Pulse', d: 'The whole house at a glance', g: 'Ring', i: '◉', ring: true, k: 'home overview glance dashboard' },
    { p: '/today', t: 'Today', d: 'The day as a live timeline', g: 'Ring', i: '◷', ring: true, k: 'timeline events story day presence camera' },
    { p: '/rooms', t: 'Rooms', d: 'Lights and media, room by room', g: 'Ring', i: '<i class="icon icon-grid" aria-hidden="true"></i>', ring: true, k: 'lights floor plan rooms dim' },
    { p: '/control', t: 'Control', d: 'Every toggle and slider', g: 'Ring', i: '⊞', ring: true, k: 'control center toggles speakers volume lock pc' },
    { p: '/atlas', t: 'Atlas', d: 'Every endpoint and service, live', g: 'Ring', i: '<i class="icon icon-sparkle" aria-hidden="true"></i>', ring: true, k: 'api endpoints services map health status' },
    { p: '/start', t: 'Start', d: 'All panels and consoles', g: 'Everyday', i: '<i class="icon icon-home" aria-hidden="true"></i>', k: 'landing news links' },
    { p: '/', t: 'Deck', d: 'Wall panel', g: 'Everyday', i: '▣', k: 'stream deck genelec spotify wall' },
    { p: '/living', t: 'Home', d: 'Lights by room, music, door', g: 'Everyday', i: '☼', k: 'living lights music' },
    { p: '/media', t: 'Media', d: 'Music, speakers, Apple TV', g: 'Everyday', i: '<i class="icon icon-music" aria-hidden="true"></i>', k: 'spotify apple tv sonos genelec' },
    { p: '/remote', t: 'Remote', d: 'Phone remote', g: 'Everyday', i: '⌁', k: 'phone remote pc' },
    { p: '/family', t: 'Family', d: "Who's home today", g: 'Everyday', i: '☺', k: 'people presence timeline' },
    { p: '/familyinfo', t: 'Family info', d: 'Buses, weather, last one home', g: 'Everyday', i: '⇄', k: 'bus weather vasttrafik' },
    { p: '/security', t: 'Security', d: 'Camera and visits', g: 'Everyday', i: '<i class="icon icon-target" aria-hidden="true"></i>', k: 'camera visits door' },
    { p: '/desktop', t: 'Desktop', d: 'Wide-screen overview', g: 'Everyday', i: '▭', k: 'desktop wide' },
    { p: '/ambient', t: 'Ambient', d: 'Night clock', g: 'Everyday', i: '<i class="icon icon-moon" aria-hidden="true"></i>', k: 'clock night bedside' },
    { p: '/admin', t: 'Admin', d: 'Health, tasks, every console', g: 'Lab & network', i: '<i class="icon icon-gear" aria-hidden="true"></i>', k: 'admin consoles tasks' },
    { p: '/localai', t: 'Local AI', d: 'Models on the PC: load, open, chat', g: 'Lab & network', i: '✳', k: 'llm ollama ai models chat gpu opencode video' },
    { p: '/ops', t: 'Lab', d: 'Nodes, guests, commands', g: 'Lab & network', i: '<i class="icon icon-database" aria-hidden="true"></i>', k: 'proxmox guests lab' },
    { p: '/net', t: 'Network', d: 'Internet, DNS, devices', g: 'Lab & network', i: '<i class="icon icon-hexagon" aria-hidden="true"></i>', k: 'network dns devices internet' },
    { p: '/network.html', t: 'Network map', d: 'Document: map and flows', g: 'Lab & network', i: '<i class="icon icon-frame" aria-hidden="true"></i>', k: 'map document' },
  ];
  const here = location.pathname.replace(/\.html$/, '').replace(/\/$/, '') || '/';
  const norm = p => p.replace(/\.html$/, '') || '/';
  const cur = PANELS.find(x => norm(x.p) === here || (here === '/' && x.p === '/'));
  const ring = PANELS.filter(x => x.ring);
  const ri = ring.findIndex(x => x === cur);
  const prev = ri >= 0 ? ring[(ri + ring.length - 1) % ring.length] : null, next = ri >= 0 ? ring[(ri + 1) % ring.length] : null;
  const store = { get(k, d) { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } }, set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} } };
  if (cur) store.set('navRecent', [cur.p, ...store.get('navRecent', []).filter(p => p !== cur.p)].slice(0, 6));
  const related = (document.querySelector('meta[name="nav-related"]')?.content || '').split(',').map(s => s.trim()).filter(Boolean);
  const esc = t => String(t).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  const css = document.createElement('style');
  css.textContent = `
  #nvorb { position: fixed; left: 50%; bottom: calc(env(safe-area-inset-bottom) + 16px); transform: translateX(-50%); z-index: 60; display: flex; align-items: center; gap: 4px;
    padding: 5px; border-radius: 999px; background: rgba(18,16,32,.78); border: 1px solid rgba(255,255,255,.12); -webkit-backdrop-filter: blur(18px) saturate(160%);
    backdrop-filter: blur(18px) saturate(160%); box-shadow: 0 12px 40px rgba(0,0,0,.45); font: 600 14px -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, sans-serif; color: #f3f4fb; }
  #nvorb a, #nvorb button { display: grid; place-items: center; height: 40px; min-width: 40px; border-radius: 999px; color: inherit; text-decoration: none; background: none; border: 0; font: inherit; cursor: pointer; }
  #nvorb .side { color: rgba(243,244,251,.6); font-size: 17px; } #nvorb .side:active { background: rgba(255,255,255,.08); color: #fff; }
  @media (hover: hover) and (pointer: fine) { #nvorb .side:hover { background: rgba(255,255,255,.08); color: #fff; } }
  #nvorb .mid { padding: 0 16px 0 12px; gap: 8px; display: flex; align-items: center; background: rgba(255,255,255,.08); }
  #nvorb .mid i { font-style: normal; font-size: 15px; opacity: .85; } #nvorb .mid kbd { font: 600 10.5px inherit; padding: 2px 6px; border-radius: 6px; background: rgba(255,255,255,.1); color: rgba(243,244,251,.6); }
  #nvorb .dots { display: flex; gap: 4px; padding: 0 6px; } #nvorb .dots span { width: 5px; height: 5px; border-radius: 50%; background: rgba(255,255,255,.22); } #nvorb .dots span.on { background: #7dd3fc; width: 14px; border-radius: 3px; }
  @media (hover: none) { #nvorb .mid kbd { display: none; } }
  @media (max-height: 460px) { #nvorb { bottom: calc(env(safe-area-inset-bottom) + 8px); padding: 3px; } #nvorb a, #nvorb button { height: 32px; min-width: 32px; } #nvorb .dots { display: none; } }
  #nvl { position: fixed; inset: 0; z-index: 90; display: none; align-items: flex-start; justify-content: center; background: rgba(4,3,10,.62);
    -webkit-backdrop-filter: blur(6px); backdrop-filter: blur(6px); padding: calc(env(safe-area-inset-top) + 8vh) 14px 20px; }
  #nvl.open { display: flex; }
  #nvl .box { width: 100%; max-width: 640px; max-height: 80vh; display: flex; flex-direction: column; border-radius: 22px; background: #14122a; border: 1px solid rgba(255,255,255,.12);
    box-shadow: 0 30px 80px rgba(0,0,0,.6); overflow: hidden; font: 15px -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, sans-serif; color: #f3f4fb; }
  #nvl input { width: 100%; padding: 18px 20px; font: 17px inherit; background: none; border: 0; border-bottom: 1px solid rgba(255,255,255,.09); color: #fff; outline: none; }
  #nvl .list { overflow-y: auto; padding: 8px; -webkit-overflow-scrolling: touch; }
  #nvl h4 { margin: 10px 12px 4px; font-size: 11px; letter-spacing: .14em; text-transform: uppercase; color: rgba(243,244,251,.45); font-weight: 700; }
  #nvl a { display: grid; grid-template-columns: 34px 1fr auto; gap: 10px; align-items: center; padding: 10px 12px; border-radius: 12px; color: inherit; text-decoration: none; }
  #nvl a .ic { width: 34px; height: 34px; border-radius: 10px; display: grid; place-items: center; background: rgba(255,255,255,.07); font-size: 16px; }
  #nvl a b { font-weight: 650; } #nvl a small { display: block; color: rgba(243,244,251,.55); font-size: 12.5px; margin-top: 1px; }
  #nvl a .here { font-size: 11px; color: #7dd3fc; font-weight: 700; }
  #nvl a.sel { background: rgba(56,189,248,.22); }
  @media (hover: hover) and (pointer: fine) { #nvl a:hover { background: rgba(56,189,248,.22); } }
  #nvl .hint { padding: 9px 16px; border-top: 1px solid rgba(255,255,255,.07); color: rgba(243,244,251,.4); font-size: 12px; display: flex; gap: 14px; flex-wrap: wrap; }
  #nvoff { position: fixed; left: 50%; top: calc(env(safe-area-inset-top) + 10px); transform: translateX(-50%); z-index: 80; display: none; max-width: calc(100% - 24px);
    padding: 10px 16px; border-radius: 14px; background: rgba(120,53,15,.92); border: 1px solid rgba(251,191,36,.5); color: #fef3c7;
    font: 600 13.5px -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, sans-serif; box-shadow: 0 10px 30px rgba(0,0,0,.4); text-align: center; }
  #nvoff.show { display: block; }
  #nvedge { position: fixed; top: 50%; z-index: 59; width: 46px; height: 46px; margin-top: -23px; border-radius: 50%; display: grid; place-items: center; font-size: 20px;
    background: rgba(56,189,248,.9); color: #fff; opacity: 0; pointer-events: none; transition: opacity .12s; }`;
  document.head.appendChild(css);

  // ---------- orb ----------
  const orb = document.createElement('nav'); orb.id = 'nvorb'; orb.setAttribute('aria-label', 'Panels');
  orb.innerHTML = (prev ? `<a class="side" href="${prev.p}" aria-label="Previous panel: ${esc(prev.t)}" title="${esc(prev.t)} (←)">‹</a>` : '')
    + `<button class="mid" id="nvopen" aria-label="All panels">${cur ? cur.i : '<i class="icon icon-list" aria-hidden="true"></i>'}${cur ? esc(cur.t) : 'Panels'}<kbd>⌘K</kbd></button>`
    + (ri >= 0 ? `<span class="dots" aria-hidden="true">${ring.map(x => `<span class="${x === cur ? 'on' : ''}"></span>`).join('')}</span>` : '')
    + (next ? `<a class="side" href="${next.p}" aria-label="Next panel: ${esc(next.t)}" title="${esc(next.t)} (→)">›</a>` : '')
    + `<button class="side" id="nvcambtn" aria-label="Front camera live" title="Camera live (C)"><i class="icon icon-camera" aria-hidden="true"></i></button>`;
  document.body.appendChild(orb);
  [prev, next].forEach(x => { if (x) { const l = document.createElement('link'); l.rel = 'prefetch'; l.href = x.p; document.head.appendChild(l); } });

  // ---------- launcher ----------
  const L = document.createElement('div'); L.id = 'nvl'; L.setAttribute('role', 'dialog'); L.setAttribute('aria-label', 'Go to panel');
  L.innerHTML = `<div class="box"><input id="nvq" type="search" placeholder="Go to panel…" autocomplete="off" autocorrect="off" autocapitalize="off" spellcheck="false" enterkeyhint="go">
    <div class="list" id="nvlist"></div><div class="hint"><span>↑↓ choose</span><span>Enter open</span><span>← → ring panels</span><span>Esc close</span></div></div>`;
  document.body.appendChild(L);
  let sel = 0, shown = [];
  const CAMITEM = { p: '#camera', t: 'Camera live', d: 'Front camera over this panel', i: '<i class="icon icon-camera" aria-hidden="true"></i>', k: 'camera live stream video door' };
  const RELOADITEM = { p: '#reload', t: 'Reload this panel', d: 'Fresh data and the newest version', i: '↻', k: 'reload refresh update' };
  const item = x => `<a href="${x.p}" data-p="${x.p}"><span class="ic">${esc(x.i)}</span><span><b>${esc(x.t)}</b><small>${esc(x.d)}</small></span>${x === cur ? '<span class="here">HERE</span>' : ''}</a>`;
  function render() {
    const q = document.getElementById('nvq').value.trim().toLowerCase();
    let html = '';
    if (q) {
      const words = q.split(/\s+/);
      shown = [RELOADITEM, CAMITEM, ...PANELS].map(x => ({ x, s: words.every(w => (x.t + ' ' + x.d + ' ' + x.k + ' ' + x.p).toLowerCase().includes(w)) ? (x.t.toLowerCase().startsWith(q) ? 2 : 1) : 0 }))
        .filter(o => o.s).sort((a, b) => b.s - a.s).map(o => o.x);
      html = shown.length ? shown.map(item).join('') : '<h4>No panel matches</h4>';
    } else {
      const recent = store.get('navRecent', []).map(p => PANELS.find(x => x.p === p)).filter(x => x && x !== cur).slice(0, 4);
      const rel = related.map(p => PANELS.find(x => x.p === p)).filter(Boolean);
      const groups = [...new Set(PANELS.map(x => x.g))];
      const sections = [['Live', [RELOADITEM, CAMITEM]], ['Related', rel], ['Recent', recent], ...groups.map(g => [g, PANELS.filter(x => x.g === g)])].filter(([, a]) => a.length);
      shown = sections.flatMap(([, a]) => a);
      html = sections.map(([h, a]) => `<h4>${esc(h)}</h4>` + a.map(item).join('')).join('');
    }
    document.getElementById('nvlist').innerHTML = html;
    sel = Math.min(sel, Math.max(0, shown.length - 1)); paint();
  }
  function paint() { document.querySelectorAll('#nvlist a').forEach((a, i) => a.classList.toggle('sel', i === sel)); document.querySelectorAll('#nvlist a')[sel]?.scrollIntoView({ block: 'nearest' }); }
  const open = () => { L.classList.add('open'); document.getElementById('nvq').value = ''; sel = 0; render(); setTimeout(() => document.getElementById('nvq').focus(), 30); };
  const close = () => L.classList.remove('open');
  document.getElementById('nvopen').addEventListener('click', open);
  L.addEventListener('click', e => { if (e.target === L) close(); const a = e.target.closest('a[href="#camera"]'); if (a) { e.preventDefault(); close(); window.deckCam?.open(); }
    if (e.target.closest('a[href="#reload"]')) { e.preventDefault(); location.reload(); } });
  document.getElementById('nvq').addEventListener('input', () => { sel = 0; render(); });
  document.getElementById('nvq').addEventListener('keydown', e => {
    if (e.key === 'ArrowDown') { e.preventDefault(); sel = Math.min(sel + 1, shown.length - 1); paint(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); sel = Math.max(sel - 1, 0); paint(); }
    else if (e.key === 'Enter') { const a = document.querySelectorAll('#nvlist a')[sel]; if (a) a.getAttribute('href') === '#camera' ? (close(), window.deckCam?.open()) : a.getAttribute('href') === '#reload' ? location.reload() : location.href = a.href; }
    else if (e.key === 'Escape') close();
  });
  const typing = () => /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName) || document.activeElement?.isContentEditable;
  document.addEventListener('keydown', e => {
    if ((e.key.toLowerCase() === 'k' && (e.metaKey || e.ctrlKey)) || (e.key === '/' && !typing() && !L.classList.contains('open'))) { e.preventDefault(); L.classList.contains('open') ? close() : open(); return; }
    if (L.classList.contains('open') || typing() || e.metaKey || e.ctrlKey || e.altKey) return;
    if (window.deckCam?.isOpen()) return;              // cam.js handles C / Esc itself
    if (e.key === 'ArrowLeft' && prev) location.href = prev.p;
    if (e.key === 'ArrowRight' && next) location.href = next.p;
  });

  document.getElementById('nvcambtn').addEventListener('click', () => window.deckCam?.open());
  // home-screen app: a ↻ in the pill (pull-to-refresh comes from refresh.js, loaded by cam.js)
  if (navigator.standalone === true || matchMedia('(display-mode: standalone)').matches || /[?&]standalone=1/.test(location.search)) {
    const rb = document.createElement('button'); rb.className = 'side'; rb.textContent = '↻'; rb.title = 'Reload this panel'; rb.setAttribute('aria-label', 'Reload this panel');
    rb.addEventListener('click', () => location.reload()); orb.appendChild(rb); }
  if (!window.deckCam) { const sc = document.createElement('script'); sc.src = '/cam.js'; sc.defer = true; document.body.appendChild(sc); }

  // ---------- connection watch: after 2 failed health checks a banner explains why nothing updates ----------
  const off = document.createElement('div'); off.id = 'nvoff'; off.setAttribute('role', 'status'); document.body.appendChild(off);
  let fails = 0;
  async function health() {
    if (document.visibilityState !== 'visible') return;
    try { const r = await fetch('/api/health', { cache: 'no-store' }); if (!r.ok) throw 0; fails = 0; off.classList.remove('show'); window.deckOnline = true; }
    catch { fails++; if (fails >= 2) { window.deckOnline = false; off.textContent = "Can't reach the Home Deck: showing the last known data, retrying…"; off.classList.add('show'); } }
  }
  health(); setInterval(health, 10000);

  // ---------- edge swipe between ring panels ----------
  if (prev || next) {
    const hint = document.createElement('div'); hint.id = 'nvedge'; document.body.appendChild(hint);
    let sx = null, sy = 0, dir = 0;
    addEventListener('touchstart', e => {
      const t = e.touches[0]; sx = null; if (e.touches.length !== 1) return;
      if (t.clientX < 26 && prev) dir = -1; else if (t.clientX > innerWidth - 26 && next) dir = 1; else return;
      sx = t.clientX; sy = t.clientY;
    }, { passive: true });
    addEventListener('touchmove', e => {
      if (sx === null) return; const t = e.touches[0], dx = t.clientX - sx, dy = Math.abs(t.clientY - sy);
      if (dy > 60) { sx = null; hint.style.opacity = 0; return; }
      const pull = dir < 0 ? dx : -dx, k = Math.max(0, Math.min(1, pull / 90));
      hint.textContent = dir < 0 ? '‹' : '›'; hint.style[dir < 0 ? 'left' : 'right'] = (8 + k * 20) + 'px'; hint.style[dir < 0 ? 'right' : 'left'] = 'auto'; hint.style.opacity = k;
    }, { passive: true });
    addEventListener('touchend', e => {
      if (sx === null) return; const dx = e.changedTouches[0].clientX - sx; hint.style.opacity = 0;
      if ((dir < 0 && dx > 80) || (dir > 0 && dx < -80)) location.href = (dir < 0 ? prev : next).p;
      sx = null;
    });
  }
})();
