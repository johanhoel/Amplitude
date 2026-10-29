/* Design gallery toolkit: live data + accident-proof interaction patterns shared by the 5 design prototypes.
 * DEMO ONLY: no action is ever sent to the house; actions show what they would do.
 *   Kit.data(cb)            live /api/home/state, /api/status, /api/bus, /api/weather (polled) -> cb(D)
 *   Kit.press(el, fn)       fires on release only; cancelled if the finger moves > 10 px or after 700 ms; double taps ignored
 *   Kit.hold(el, ms, fn)    press-and-hold with a progress fill (el needs a child .kfill)
 *   Kit.slide(el, fn)       slide-to-confirm track (el = .kslide with .knob inside)
 *   Kit.arm(el, fn)         first tap arms (turns red, 3 s), second tap runs
 *   Kit.undo(text, undoFn)  toast with Undo (6 s)  ·  Kit.toast(text)
 */
window.Kit = (() => {
  const D = {}, subs = [];
  async function get(k, url) { try { const r = await fetch(url, { cache: 'no-store' }); const j = await r.json(); if (!j.error) D[k] = j; } catch {} }
  // never redraw under a finger: a redraw replaces the button being pressed and would swallow the tap
  let touching = false, pending = false;
  addEventListener('pointerdown', () => touching = true, true);
  ['pointerup', 'pointercancel'].forEach(ev => addEventListener(ev, () => { touching = false; if (pending) { pending = false; setTimeout(() => subs.forEach(f => f(D)), 60); } }, true));
  async function poll() {
    if (document.visibilityState !== 'visible') return;
    await Promise.all([get('home', '/api/home/state'), get('status', '/api/status'), get('bus', '/api/bus'), get('wx', '/api/weather')]);
    if (touching) { pending = true; return; }
    subs.forEach(f => f(D));
  }
  const data = cb => { subs.push(cb); if (subs.length === 1) { poll(); setInterval(poll, 8000); document.addEventListener('visibilitychange', poll); } else if (Object.keys(D).length) cb(D); };

  // ---- toast + undo ----
  const css = document.createElement('style');
  css.textContent = `.ktoast{position:fixed;left:50%;bottom:calc(env(safe-area-inset-bottom) + 96px);transform:translateX(-50%) translateY(20px);opacity:0;z-index:90;display:flex;gap:14px;align-items:center;
    padding:12px 12px 12px 18px;border-radius:16px;background:var(--toast-bg,#1d1b2e);color:var(--toast-ink,#fff);font:600 14px var(--font,system-ui);box-shadow:0 12px 40px rgba(0,0,0,.35);
    transition:opacity .2s,transform .2s;pointer-events:none;max-width:calc(100% - 28px)}
    .ktoast.show{opacity:1;transform:translateX(-50%);pointer-events:auto}
    .ktoast button{min-height:40px;padding:0 14px;border-radius:12px;border:0;background:rgba(255,255,255,.16);color:inherit;font:700 14px var(--font,system-ui);cursor:pointer}
    .kdemo{display:block;text-align:center;padding:calc(env(safe-area-inset-top) + 6px) 12px 6px;font:700 10.5px system-ui;letter-spacing:.12em;
    background:rgba(251,191,36,.92);color:#1c1300}`;
  document.head.appendChild(css);
  const t = document.createElement('div'); t.className = 'ktoast'; document.body.appendChild(t);
  const badge = document.createElement('div'); badge.className = 'kdemo'; badge.textContent = 'DESIGN DEMO · NOTHING IS SWITCHED'; document.body.prepend(badge);   // in the flow: never covers a heading
  let tt;
  function toast(text) { clearTimeout(tt); t.innerHTML = ''; t.append(text); t.classList.add('show'); tt = setTimeout(() => t.classList.remove('show'), 2600); }
  function undo(text, fn) {
    clearTimeout(tt); t.innerHTML = ''; const s = document.createElement('span'); s.textContent = text; const b = document.createElement('button'); b.textContent = 'Undo';
    b.onclick = () => { fn?.(); toast('Undone'); }; t.append(s, b); t.classList.add('show'); tt = setTimeout(() => t.classList.remove('show'), 6000);
  }

  // ---- press: release-only, movement-cancelled, no double fire ----
  const fired = {};                                   // per-button memory that survives re-renders (a redraw must not reset the double-tap guard)
  const keyOf = el => el.dataset.id || el.dataset.t || el.dataset.go || el.dataset.r || el.dataset.i || el.textContent.trim().slice(0, 40);
  function press(el, fn) {
    let st = null;
    el.addEventListener('pointerdown', e => { if (e.button > 0) return; st = { x: e.clientX, y: e.clientY, t: Date.now() }; el.classList.add('kdown'); });
    el.addEventListener('pointermove', e => { if (st && Math.hypot(e.clientX - st.x, e.clientY - st.y) > 10) { st = null; el.classList.remove('kdown'); } });
    const up = e => { el.classList.remove('kdown'); if (!st) return; const k = keyOf(el), ok = Date.now() - st.t < 700 && Date.now() - (fired[k] || 0) > 450; st = null; if (ok) { fired[k] = Date.now(); fn(e); } };
    el.addEventListener('pointerup', up); el.addEventListener('pointercancel', () => { st = null; el.classList.remove('kdown'); });
    el.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fn(e); } });
  }
  // ---- hold ----
  function hold(el, ms, fn) {
    let tm = null, st = null; const f = el.querySelector('.kfill');
    const reset = () => { clearTimeout(tm); tm = null; st = null; if (f) { f.style.transition = 'width .2s'; f.style.width = '0'; } el.classList.remove('kdown'); };
    el.addEventListener('pointerdown', e => { st = { x: e.clientX, y: e.clientY }; el.classList.add('kdown');
      if (f) { f.style.transition = `width ${ms}ms linear`; f.style.width = '100%'; }
      tm = setTimeout(() => { navigator.vibrate?.(25); reset(); fn(); }, ms); });
    el.addEventListener('pointermove', e => { if (st && Math.hypot(e.clientX - st.x, e.clientY - st.y) > 14) reset(); });
    ['pointerup', 'pointerleave', 'pointercancel'].forEach(ev => el.addEventListener(ev, () => { if (tm) { reset(); toast('Keep holding to confirm'); } }));
    el.addEventListener('contextmenu', e => e.preventDefault());
  }
  // ---- slide to confirm ----
  function slide(el, fn) {
    const k = el.querySelector('.knob'); let st = null;
    k.addEventListener('pointerdown', e => { st = { x: e.clientX, max: el.clientWidth - k.offsetWidth - 8 }; k.setPointerCapture(e.pointerId); k.style.transition = 'none'; });
    k.addEventListener('pointermove', e => { if (!st) return; const dx = Math.max(0, Math.min(st.max, e.clientX - st.x)); k.style.transform = `translateX(${dx}px)`; el.style.setProperty('--p', dx / st.max); });
    const end = e => { if (!st) return; const dx = Math.max(0, e.clientX - st.x), done = dx >= st.max * .92; st = null; k.style.transition = 'transform .25s';
      k.style.transform = 'translateX(0)'; el.style.setProperty('--p', 0); if (done) { navigator.vibrate?.(25); fn(); } };
    k.addEventListener('pointerup', end); k.addEventListener('pointercancel', end);
  }
  // ---- arm, then confirm ----
  function arm(el, fn) {
    let tm = null;
    press(el, () => {
      if (el.classList.contains('karmed')) { clearTimeout(tm); el.classList.remove('karmed'); fn(); return; }
      el.classList.add('karmed'); el.dataset.label = el.dataset.label || el.querySelector('.klabel')?.textContent || '';
      const l = el.querySelector('.klabel'); if (l) l.textContent = 'Tap again to confirm';
      tm = setTimeout(() => { el.classList.remove('karmed'); if (l) l.textContent = el.dataset.label; }, 3000);
    });
  }
  // ---- helpers used by every design ----
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const hm = d => new Date(d).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });
  const WX = { 'sunny': '<i class="icon icon-sun" aria-hidden="true"></i>', 'clear-night': '<i class="icon icon-moon" aria-hidden="true"></i>', 'partlycloudy': '<i class="icon icon-partly" aria-hidden="true"></i>', 'cloudy': '<i class="icon icon-cloud" aria-hidden="true"></i>', 'rainy': '<i class="icon icon-rain" aria-hidden="true"></i>', 'pouring': '<i class="icon icon-rain" aria-hidden="true"></i>', 'lightning': '<i class="icon icon-storm" aria-hidden="true"></i>', 'lightning-rainy': '<i class="icon icon-storm" aria-hidden="true"></i>',
    'snowy': '<i class="icon icon-snow" aria-hidden="true"></i>', 'snowy-rainy': '<i class="icon icon-snow" aria-hidden="true"></i>', 'hail': '<i class="icon icon-snow" aria-hidden="true"></i>', 'fog': '<i class="icon icon-fog" aria-hidden="true"></i>', 'windy': '<i class="icon icon-wind" aria-hidden="true"></i>', 'windy-variant': '<i class="icon icon-wind" aria-hidden="true"></i>' };
  function nextBus(bus) {
    const d = (bus?.departures || []).map(x => ({ ...x, t: [x.next, x.then].find(y => y?.time && new Date(y.time) > Date.now() - 30000) })).filter(x => x.t)
      .sort((a, b) => new Date(a.t.time) - new Date(b.t.time))[0];
    return d ? { line: d.line.shortName, to: d.to, at: hm(d.t.time), min: Math.max(0, Math.floor((new Date(d.t.time) - Date.now()) / 60000)), text: '' }
             : { none: true, text: 'No buses in the next hour' };
  }
  function summary(D) {
    const H = D.home || {}, rooms = H.rooms || [];
    const lit = rooms.filter(r => r.lights.some(l => l.on));
    const playing = (H.players || []).concat(H.appletv ? [H.appletv] : []).find(p => p.state === 'playing');
    return { H, rooms, lit, lightsOn: rooms.reduce((a, r) => a + r.lights.filter(l => l.on).length, 0), people: H.people || [], door: H.door?.state,
      playing, bus: nextBus(D.bus), wx: D.wx?.now || H.wx, hourly: D.wx?.hourly || [], status: D.status || {} };
  }
  // demo light state: a toggle sticks until undone, even when fresh data arrives
  const over = {};
  const isOn = l => (l.id in over ? over[l.id] : l.on);
  function flip(l, render) { const was = isOn(l); over[l.id] = !was; render();
    undo(`${l.name === 'All' ? 'Room lights' : l.name} ${!was ? 'on' : 'off'} (demo)`, () => { over[l.id] = was; render(); }); }
  // refresh for home-screen apps (pull-to-refresh + ↻)
  { const sc = document.createElement('script'); sc.src = '/refresh.js'; sc.onload = () => { if (window.deckRefresh?.standalone) window.deckRefresh.button(); }; document.body.appendChild(sc); }
  const busText = b => b?.none ? b.text : b ? (b.min < 1 ? 'Now' : b.min + ' min') : '–';
  return { data, press, hold, slide, arm, undo, toast, esc, hm, WX, summary, isOn, flip, busText };
})();
