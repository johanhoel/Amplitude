/* Wall kit: live data + accident-proof presses for the Wall panels (design 3). Same patterns as the design prototypes,
 * but these buttons really act on the house.
 *   Wall.data(cb)            live /api/home/state, /api/status, /api/bus, /api/weather (every 8 s, paused in the background) -> cb(D)
 *   Wall.press(el, fn)       fires on release only; cancelled if the finger moves > 10 px or after 700 ms; double taps ignored
 *   Wall.arm(el, fn)         first tap arms (red, "Tap again to confirm", 3 s), the second tap runs
 *   Wall.act(url, body, ok)  POST an action; toast ok / the error; resolves true when it worked
 *   Wall.light(l)            a light's on/off, including a press that is still on its way (optimistic for 8 s)
 *   Wall.toggle(l, render)   toggle a light now, with Undo
 *   Wall.undo(text, fn) / Wall.toast(text)
 * Never redraws under a finger: a redraw replaces the button being pressed and would swallow the tap.
 */
window.Wall = (() => {
  const D = {}, subs = [];
  async function get(k, url) { try { const r = await fetch(url, { cache: 'no-store' }); const j = await r.json(); if (!j.error) D[k] = j; } catch {} }
  let touching = false, pending = false;
  addEventListener('pointerdown', () => touching = true, true);
  ['pointerup', 'pointercancel'].forEach(ev => addEventListener(ev, () => { touching = false; if (pending) { pending = false; setTimeout(() => subs.forEach(f => f(D)), 60); } }, true));
  const emit = () => { if (touching) { pending = true; return; } subs.forEach(f => f(D)); };
  async function poll() {
    if (document.visibilityState !== 'visible') return;
    await Promise.all([get('home', '/api/home/state'), get('status', '/api/status'), get('bus', '/api/bus'), get('wx', '/api/weather')]);
    emit();
  }
  const refresh = (ms = 900) => setTimeout(async () => { await get('home', '/api/home/state'); emit(); }, ms);
  const data = cb => { subs.push(cb); if (subs.length === 1) { poll(); setInterval(poll, 8000); document.addEventListener('visibilitychange', poll); } else if (Object.keys(D).length) cb(D); };

  // ---- toast + undo ----
  const css = document.createElement('style');
  css.textContent = `.wtoast{position:fixed;left:50%;bottom:calc(env(safe-area-inset-bottom) + var(--toast-bottom, 110px));transform:translateX(-50%) translateY(20px);opacity:0;z-index:90;display:flex;gap:14px;align-items:center;
    padding:12px 12px 12px 18px;border-radius:16px;background:#243040;color:#fff;font:600 15px var(--font,system-ui);box-shadow:0 12px 40px rgba(0,0,0,.45);
    transition:opacity .2s,transform .2s;pointer-events:none;max-width:calc(100% - 28px)}
    .wtoast.show{opacity:1;transform:translateX(-50%);pointer-events:auto} .wtoast.bad{background:#4a1212}
    .wtoast button{min-height:44px;padding:0 16px;border-radius:12px;border:0;background:rgba(255,255,255,.16);color:inherit;font:700 15px var(--font,system-ui);cursor:pointer}`;
  document.head.appendChild(css);
  const t = document.createElement('div'); t.className = 'wtoast'; t.setAttribute('role', 'status'); document.body.appendChild(t);
  let tt;
  function toast(text, bad) { clearTimeout(tt); t.innerHTML = ''; t.append(text); t.classList.toggle('bad', !!bad); t.classList.add('show'); tt = setTimeout(() => t.classList.remove('show'), bad ? 4500 : 2600); }
  function undo(text, fn) {
    clearTimeout(tt); t.innerHTML = ''; t.classList.remove('bad'); const s = document.createElement('span'); s.textContent = text; const b = document.createElement('button'); b.textContent = 'Undo';
    b.onclick = () => { t.classList.remove('show'); fn?.(); }; t.append(s, b); t.classList.add('show'); tt = setTimeout(() => t.classList.remove('show'), 6000);
  }

  // ---- press: release-only, movement-cancelled, no double fire ----
  const fired = {};                                   // survives redraws, so a redraw never resets the double-tap guard
  const keyOf = el => el.dataset.id || el.dataset.t || el.dataset.go || el.dataset.r || el.textContent.trim().slice(0, 40);
  function press(el, fn) {
    let st = null;
    el.addEventListener('pointerdown', e => { if (e.button > 0) return; st = { x: e.clientX, y: e.clientY, t: Date.now() }; el.classList.add('kdown'); });
    el.addEventListener('pointermove', e => { if (st && Math.hypot(e.clientX - st.x, e.clientY - st.y) > 10) { st = null; el.classList.remove('kdown'); } });
    el.addEventListener('pointerup', e => { el.classList.remove('kdown'); if (!st) return; const k = keyOf(el), ok = Date.now() - st.t < 700 && Date.now() - (fired[k] || 0) > 450; st = null; if (ok) { fired[k] = Date.now(); fn(e); } });
    el.addEventListener('pointercancel', () => { st = null; el.classList.remove('kdown'); });
    el.addEventListener('click', e => { if (el.tagName === 'A') e.preventDefault(); if (e.detail === 0) fn(e); });   // keyboard Enter / Space
  }
  // ---- arm, then confirm ----
  function arm(el, fn) {
    let tm = null;
    press(el, () => {
      const l = el.querySelector('.klabel');
      if (el.classList.contains('karmed')) { clearTimeout(tm); el.classList.remove('karmed'); if (l) l.textContent = el.dataset.label; fn(); return; }
      el.classList.add('karmed'); el.dataset.label = el.dataset.label || l?.textContent || '';
      if (l) l.textContent = 'Tap again to confirm';
      tm = setTimeout(() => { el.classList.remove('karmed'); if (l) l.textContent = el.dataset.label; }, 3000);
    });
  }
  // ---- actions ----
  async function act(url, body, ok) {
    try {
      const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}), credentials: 'same-origin' });
      const j = await r.json().catch(() => ({}));
      if (r.status === 401 && j.admin) { toast('That needs the admin PIN', true); return false; }
      if (!r.ok || j.error) { toast('✗ ' + (j.error || 'Did not work (' + r.status + ')'), true); return false; }
      if (ok) toast(ok);
      refresh(); return true;
    } catch (e) { toast('✗ No answer from Home Deck', true); return false; }
  }
  // lights: show a press at once, and keep showing it until the house agrees (or 8 s pass)
  const over = {};
  const light = l => { const o = over[l.id]; if (o && Date.now() < o.until && o.on !== l.on) return o.on; if (o) delete over[l.id]; return l.on; };
  function toggle(l, render) {
    const was = light(l); over[l.id] = { on: !was, until: Date.now() + 8000 }; render();
    act('/api/home/do', { do: 'toggle', entity: l.id }).then(okd => {
      if (!okd) { delete over[l.id]; render(); return; }
      undo(`${l.name === 'All' ? 'Room lights' : l.name} ${!was ? 'on' : 'off'}`, () => { over[l.id] = { on: was, until: Date.now() + 8000 }; render(); act('/api/home/do', { do: 'toggle', entity: l.id }); });
    });
  }
  // ---- helpers ----
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const hm = d => new Date(d).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });
  const WX = { 'sunny': '☀️', 'clear-night': '🌙', 'partlycloudy': '⛅', 'cloudy': '☁️', 'rainy': '🌧️', 'pouring': '🌧️', 'lightning': '🌩️', 'lightning-rainy': '⛈️',
    'snowy': '❄️', 'snowy-rainy': '🌨️', 'hail': '🌨️', 'fog': '🌫️', 'windy': '💨', 'windy-variant': '💨', 'exceptional': '⚠️' };
  const WXT = { 'sunny': 'Sunny', 'clear-night': 'Clear', 'partlycloudy': 'Partly cloudy', 'cloudy': 'Cloudy', 'rainy': 'Rain', 'pouring': 'Heavy rain', 'lightning': 'Thunder',
    'lightning-rainy': 'Thunder and rain', 'snowy': 'Snow', 'snowy-rainy': 'Sleet', 'hail': 'Hail', 'fog': 'Fog', 'windy': 'Windy', 'windy-variant': 'Windy' };
  function nextBus(bus) {
    const d = (bus?.departures || []).map(x => ({ ...x, t: [x.next, x.then].find(y => y?.time && new Date(y.time) > Date.now() - 30000) })).filter(x => x.t)
      .sort((a, b) => new Date(a.t.time) - new Date(b.t.time))[0];
    return d ? { line: d.line.shortName, to: d.to, at: hm(d.t.time), min: Math.max(0, Math.floor((new Date(d.t.time) - Date.now()) / 60000)) } : { none: true };
  }
  function summary(D) {
    const H = D.home || {}, rooms = H.rooms || [];
    const playing = (H.players || []).concat(H.appletv ? [H.appletv] : []).find(p => p.state === 'playing');
    return { H, rooms, people: H.people || [], door: H.door?.state, playing, bus: nextBus(D.bus), wx: D.wx?.now || H.wx, today: D.wx?.daily?.[0], status: D.status || {},
      lightsOn: rooms.reduce((a, r) => a + r.lights.filter(light).length, 0) };
  }
  // refresh for home-screen apps (pull-to-refresh + ↻)
  { const sc = document.createElement('script'); sc.src = '/refresh.js'; document.body.appendChild(sc); }
  return { data, press, arm, act, light, toggle, undo, toast, esc, hm, WX, WXT, summary, refresh };
})();
