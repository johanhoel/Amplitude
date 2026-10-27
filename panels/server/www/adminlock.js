/* Home Deck "Log out" for admin pages. One press (on release; a moving finger cancels) ends the admin session on this
 * device (POST /api/pin/logout) and goes to /start; the next admin page asks for the PIN again.
 * Include on admin pages: <script src="/adminlock.js" defer></script>
 * Placement, so it never covers the page:
 *   - data-into="<selector>": inside that header element (the page's own toolbar)
 *   - otherwise next to the page's "‹ Start" link (start.js): in the same nav with the same style, or beside the floating pill
 *   - last resort: a small floating pill bottom-left
 */
(() => {
  if (document.getElementById('dklogout')) return;
  const me = document.currentScript;
  const css = document.createElement('style');
  css.textContent = `
  #dklogout:not(.innav) { display: inline-flex; align-items: center; gap: 7px; min-height: 44px; padding: 0 16px; border-radius: 999px; flex: none;
    border: 1px solid rgba(255,255,255,.16); background: rgba(18,20,26,.86); color: #eef2f6; cursor: pointer; text-decoration: none; white-space: nowrap;
    font: 650 14px -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Roboto, sans-serif;
    -webkit-user-select: none; user-select: none; touch-action: manipulation; }
  #dklogout.float { position: fixed; z-index: 57; -webkit-backdrop-filter: blur(12px); backdrop-filter: blur(12px); box-shadow: 0 6px 22px rgba(0,0,0,.35); }
  #dklogout.innav { display: inline-flex; align-items: center; justify-content: center; min-height: 44px; gap: 6px; cursor: pointer; white-space: nowrap; }
  #dklogout:not(.innav):hover { border-color: rgba(255,255,255,.3); } #dklogout.down { transform: scale(.96); }
  #dklogout:focus-visible { outline: 3px solid #38bdf8; outline-offset: 3px; }
  @media (max-width: 599px) { #dklogout.compact { width: 44px; height: 44px; min-height: 44px; padding: 0; justify-content: center; } #dklogout.compact span + span { display: none; } }
  nav .start-link { white-space: nowrap; } nav:has(> #dklogout) { align-items: center; }
  @media print { #dklogout { display: none; } }`;
  document.head.appendChild(css);

  const b = document.createElement('a'); b.id = 'dklogout'; b.href = '/start'; b.setAttribute('role', 'button');
  b.innerHTML = '<span aria-hidden="true">🔒</span><span>Log out</span>'; b.title = 'Lock admin on this device'; b.setAttribute('aria-label', 'Log out of admin on this device');
  let st = null, busy = false;
  const go = async () => {
    if (busy) return; busy = true; b.lastChild.textContent = 'Logging out…';
    try { await fetch('/api/pin/logout', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}', credentials: 'same-origin' }); } catch {}
    location.replace('/start');
  };
  b.addEventListener('click', e => { e.preventDefault(); if (e.detail === 0) go(); });          // keyboard (Enter); taps go through pointerup
  b.addEventListener('pointerdown', e => { st = { x: e.clientX, y: e.clientY }; b.classList.add('down'); });
  b.addEventListener('pointermove', e => { if (st && Math.hypot(e.clientX - st.x, e.clientY - st.y) > 10) { st = null; b.classList.remove('down'); } });
  b.addEventListener('pointerup', () => { b.classList.remove('down'); if (st) go(); st = null; });
  b.addEventListener('pointercancel', () => { st = null; b.classList.remove('down'); });

  const into = me?.dataset.into && document.querySelector(me.dataset.into);
  if (into) { b.classList.add('compact'); into.appendChild(b); return; }
  let tries = 0;
  (function place() {
    const s = document.querySelector('.start-link');
    if (!s && ++tries < 20) return setTimeout(place, 100);           // start.js adds the link when the page is ready
    if (s && getComputedStyle(s).position !== 'fixed') {              // in a nav / chip row: same look as its neighbours
      b.className = s.className.replace('start-link', '').trim() + ' innav compact'; s.after(b); return;
    }
    b.classList.add('float');
    if (s) {                                                          // beside the floating "‹ Start" pill, same height
      const r = s.getBoundingClientRect();
      if (r.left > innerWidth / 2) { b.classList.add('compact'); b.style.top = r.top + 'px'; b.style.right = (innerWidth - r.left + 10) + 'px'; }
      else { b.style.bottom = (innerHeight - r.bottom) + 'px'; b.style.left = (r.right + 10) + 'px'; }
    } else { b.style.left = 'calc(env(safe-area-inset-left) + 16px)'; b.style.bottom = 'calc(env(safe-area-inset-bottom) + 16px)'; }
    document.body.appendChild(b);
  })();
})();
