/* Home Deck admin keypad - window.deckPin.open({ onOk, next }) shows it over the page.
 * Talks to /api/pin/status|setup|verify (server-side check, hashed PIN, lockout after repeated wrong PINs).
 * First use (no PIN set): "Choose an admin PIN" twice. Keys fire on release only and a moving finger cancels the key,
 * so a PIN is never typed by accident; digits and Backspace/Enter work on a keyboard too.
 */
(() => {
  if (window.deckPin) return;
  const css = document.createElement('style');
  css.textContent = `
  #dkpin { position: fixed; inset: 0; z-index: 120; display: none; align-items: center; justify-content: center; background: rgba(5,8,12,.86);
    -webkit-backdrop-filter: blur(10px); backdrop-filter: blur(10px); padding: calc(env(safe-area-inset-top) + 12px) 16px calc(env(safe-area-inset-bottom) + 12px);
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", Inter, Roboto, sans-serif; color: #eef2f6; }
  #dkpin.open { display: flex; }
  #dkpin .box { width: min(380px, 100%); text-align: center; }
  #dkpin h2 { margin: 0 0 4px; font-size: 24px; font-weight: 750; } #dkpin p { margin: 0 0 18px; color: #8b98a8; font-size: 15px; min-height: 20px; }
  #dkpin p.bad { color: #fca5a5; }
  #dkpin .dots { display: flex; justify-content: center; gap: 14px; height: 22px; margin-bottom: 26px; }
  #dkpin .dots i { width: 16px; height: 16px; border-radius: 50%; border: 2px solid #4b5563; } #dkpin .dots i.f { background: #38bdf8; border-color: #38bdf8; }
  #dkpin .box.shake { animation: dkshake .4s; } @keyframes dkshake { 20%, 60% { transform: translateX(-10px); } 40%, 80% { transform: translateX(10px); } }
  #dkpin .keys { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; justify-items: center; }
  #dkpin .keys button { width: 80px; height: 80px; border-radius: 50%; border: 1px solid #2a333d; background: #1a2027; color: #eef2f6; font-family: inherit; font-size: 32px; font-weight: 400;
    cursor: pointer; touch-action: manipulation; -webkit-user-select: none; user-select: none; transition: background .1s, transform .08s; }
  #dkpin .keys button.down { background: #2a3440; transform: scale(.95); } #dkpin .keys button.fn { font-size: 24px; font-weight: 600; color: #8b98a8; }
  #dkpin .keys button:focus { outline: none; } #dkpin .keys button:focus-visible { outline: 3px solid #38bdf8; outline-offset: 3px; }
  #dkpin.locked .keys button { opacity: .3; pointer-events: none; }
  #dkpin .keys button.ok { background: #0c4a6e; border-color: #38bdf8; color: #e0f2fe; font-size: 19px; font-weight: 750; } #dkpin .keys button:disabled { opacity: .35; }
  #dkpin .rem { display: flex; align-items: center; justify-content: center; gap: 10px; margin: 24px 0 6px; min-height: 48px; font-size: 15px; cursor: pointer; color: #cbd5e1; }
  /* The browser's own checkbox is a white square: on this page it is the
     brightest thing on screen, brighter than the OK key. Drawn here instead,
     in the same shapes as the keypad, with the press feedback every other
     control has. */
  #dkpin .rem input { appearance: none; -webkit-appearance: none; margin: 0; position: relative;
    width: 22px; height: 22px; border-radius: 7px; border: 1.5px solid #2a333d; background: #141922;
    cursor: pointer; transition: background 140ms cubic-bezier(0.23, 1, 0.32, 1),
      border-color 140ms cubic-bezier(0.23, 1, 0.32, 1), transform 140ms cubic-bezier(0.23, 1, 0.32, 1); }
  #dkpin .rem input:checked { background: #38bdf8; border-color: #38bdf8; }
  #dkpin .rem input:checked::after { content: ''; position: absolute; left: 7px; top: 3px;
    width: 5px; height: 10px; border: solid #07080f; border-width: 0 2.5px 2.5px 0; transform: rotate(45deg); }
  #dkpin .rem input:active { transform: scale(0.94); }
  #dkpin .rem input:focus-visible { outline: 3px solid #38bdf8; outline-offset: 3px; }
  @media (prefers-reduced-motion: reduce) {
    #dkpin .rem input { transition-duration: .01ms; }
    #dkpin .rem input:active { transform: none; }
  }
  #dkpin .cancel { margin-top: 8px; min-height: 48px; padding: 0 24px; border-radius: 999px; border: 1px solid #2a333d; background: none; color: #8b98a8; font-family: inherit; font-size: 15px; font-weight: 600; cursor: pointer; }`;
  document.head.appendChild(css);
  const el = document.createElement('div'); el.id = 'dkpin'; el.setAttribute('role', 'dialog'); el.setAttribute('aria-label', 'Admin PIN');
  el.innerHTML = `<div class="box"><h2 id="dkpt">Admin PIN</h2><p id="dkpm"></p><div class="dots" id="dkpd" aria-hidden="true"></div>
    <div class="keys">${[1, 2, 3, 4, 5, 6, 7, 8, 9].map(n => `<button data-k="${n}">${n}</button>`).join('')}<button class="fn" data-k="del" aria-label="Delete">⌫</button><button data-k="0">0</button><button class="ok" data-k="ok">OK</button></div>
    <label class="rem"><input type="checkbox" id="dkpr"> Remember this device for 30 days</label><button class="cancel" id="dkpc">Cancel</button></div>`;
  document.body.appendChild(el);
  const $ = s => el.querySelector(s);
  let pin = '', mode = 'verify', first = '', minLen = 4, cb = null, tick = null;
  const msg = (t, bad) => { $('#dkpm').textContent = t; $('#dkpm').classList.toggle('bad', !!bad); };
  const dots = () => { $('#dkpd').innerHTML = Array.from({ length: Math.max(minLen, pin.length) }, (_, i) => `<i class="${i < pin.length ? 'f' : ''}"></i>`).join(''); $('[data-k="ok"]').disabled = pin.length < minLen; };
  const shake = () => { const b = $('.box'); b.classList.remove('shake'); void b.offsetWidth; b.classList.add('shake'); navigator.vibrate?.([40, 40, 40]); };
  const post = (u, b) => fetch(u, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(b), credentials: 'same-origin' }).then(async r => ({ code: r.status, j: await r.json().catch(() => ({})) }));
  function lockout(s) {
    clearInterval(tick); let left = s; el.classList.add('locked');
    const run = () => { msg(`Too many wrong PINs. Try again in ${Math.floor(left / 60)}:${String(left % 60).padStart(2, '0')}`, true); if (--left < 0) { clearInterval(tick); tick = null; el.classList.remove('locked'); msg('Enter the admin PIN'); } };
    run(); tick = setInterval(run, 1000);
  }
  async function open(opts = {}) {
    cb = opts.onOk || null; pin = ''; first = ''; clearInterval(tick); tick = null; el.classList.remove('locked');
    let st = {}; try { st = await (await fetch('/api/pin/status', { cache: 'no-store', credentials: 'same-origin' })).json(); } catch {}
    if (st.admin && !opts.force) { cb?.(); return; }
    minLen = st.min_len || 4; mode = st.set === false ? 'setup1' : 'verify';
    $('#dkpt').textContent = mode === 'verify' ? 'Admin PIN' : 'Choose an admin PIN';
    msg(mode === 'verify' ? 'Enter the admin PIN' : `First use: choose ${minLen}–8 digits. You will enter it twice.`);
    if (st.locked_s) lockout(st.locked_s);
    dots(); el.classList.add('open'); $('[data-k="5"]').focus({ preventScroll: true });
  }
  const close = () => { el.classList.remove('open', 'locked'); pin = ''; clearInterval(tick); tick = null; };
  async function submit() {
    if (pin.length < minLen) return;
    const remember = $('#dkpr').checked;
    if (mode === 'setup1') { first = pin; pin = ''; mode = 'setup2'; msg('Enter the same PIN again'); return dots(); }
    if (mode === 'setup2') {
      if (pin !== first) { shake(); pin = ''; first = ''; mode = 'setup1'; msg("The two PINs didn't match. Choose a PIN again.", true); return dots(); }
      const r = await post('/api/pin/setup', { pin, remember });
      if (r.code === 200) { close(); cb?.(); return; }
      shake(); pin = ''; mode = 'verify'; msg(r.j.error || 'Could not set the PIN', true); return dots();
    }
    const r = await post('/api/pin/verify', { pin, remember });
    pin = ''; dots();
    if (r.code === 200) { close(); cb?.(); return; }
    shake();
    if (r.code === 429 || r.j.wait_s) return lockout(r.j.wait_s);
    msg(r.j.tries_left != null ? `Wrong PIN · ${r.j.tries_left} ${r.j.tries_left === 1 ? 'try' : 'tries'} left` : (r.j.error || 'Wrong PIN'), true);
  }
  const key = k => { if (tick && mode === 'verify' && /Too many/.test($('#dkpm').textContent)) return;
    if (k === 'del') pin = pin.slice(0, -1); else if (k === 'ok') return submit(); else if (pin.length < 8) pin += k; dots(); };
  // release-only keys; a moving finger cancels
  el.querySelectorAll('.keys button').forEach(b => { let st = null;
    b.addEventListener('pointerdown', e => { st = { x: e.clientX, y: e.clientY }; b.classList.add('down'); });
    b.addEventListener('pointermove', e => { if (st && Math.hypot(e.clientX - st.x, e.clientY - st.y) > 12) { st = null; b.classList.remove('down'); } });
    b.addEventListener('pointerup', () => { b.classList.remove('down'); if (st && !b.disabled) key(b.dataset.k); st = null; });
    b.addEventListener('pointercancel', () => { st = null; b.classList.remove('down'); });
    b.addEventListener('click', e => { if (e.detail === 0 && !b.disabled) key(b.dataset.k); });   // keyboard activation (Enter/Space on a focused key)
  });
  document.addEventListener('keydown', e => { if (!el.classList.contains('open')) return;
    if (/^\d$/.test(e.key)) { e.preventDefault(); key(e.key); } else if (e.key === 'Backspace') { e.preventDefault(); key('del'); }
    else if (e.key === 'Enter') { e.preventDefault(); key('ok'); } else if (e.key === 'Escape') close(); });
  $('#dkpc').addEventListener('click', () => { close(); window.dispatchEvent(new Event('deckpin-cancel')); });
  window.deckPin = { open, close, logout: () => post('/api/pin/logout', {}), status: () => fetch('/api/pin/status', { cache: 'no-store', credentials: 'same-origin' }).then(r => r.json()) };
})();
