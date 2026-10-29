/* Home Deck refresh for panels saved to the home screen (no browser bar = no reload button). Loaded by cam.js and the design kit.
 *   - pull-to-refresh: from the very top of the page, pull down > 90 px and let go; ignored when the pull starts on a slider,
 *     a sideways strip, a text field or anything marked data-no-ptr (so it never fights a control)
 *   - ↻ button: a small button above the camera button in home-screen apps (window.deckRefresh.button() adds it elsewhere)
 *   - back after > 15 min in the background (phone locked, app switched): reload by itself, so the page is never stale
 */
(() => {
  if (window.deckRefresh) return;
  const standalone = navigator.standalone === true || matchMedia('(display-mode: standalone)').matches || /[?&]standalone=1/.test(location.search);
  const css = document.createElement('style');
  css.textContent = `
  #dkptr { position: fixed; left: 50%; top: calc(env(safe-area-inset-top) + 6px); z-index: 99; width: 42px; height: 42px; margin-left: -21px; border-radius: 50%;
    display: grid; place-items: center; background: rgba(20,18,36,.9); color: #fff; font: 700 20px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    box-shadow: 0 8px 24px rgba(0,0,0,.35); transform: translateY(-70px); opacity: 0; transition: opacity .15s; pointer-events: none; }
  #dkptr.ready { background: #38bdf8; } #dkptr.go { animation: dkspin .8s linear infinite; } @keyframes dkspin { to { rotate: 360deg; } }
  #dkreload { position: fixed; right: calc(env(safe-area-inset-right) + 16px); bottom: calc(env(safe-area-inset-bottom) + var(--dkr-bottom, 76px)); z-index: 58;
    width: 44px; height: 44px; border-radius: 50%; border: 1px solid rgba(255,255,255,.14); background: rgba(18,16,32,.8); color: #fff; font-size: 19px; cursor: pointer;
    -webkit-backdrop-filter: blur(14px); backdrop-filter: blur(14px); box-shadow: 0 10px 30px rgba(0,0,0,.4); display: grid; place-items: center; }
  #dkreload.inline { position: static; width: 40px; height: 40px; box-shadow: none; flex: none; }`;
  document.head.appendChild(css);
  const reload = () => { const i = document.getElementById('dkptr'); if (i) { i.style.opacity = 1; i.style.transform = 'translateY(0)'; i.classList.add('go'); } setTimeout(() => location.reload(), 120); };

  // ---- pull to refresh ----
  const ind = document.createElement('div'); ind.id = 'dkptr'; ind.textContent = '↻'; ind.setAttribute('aria-hidden', 'true'); document.body.appendChild(ind);
  let y0 = null, pull = 0;
  const atTop = () => (document.scrollingElement || document.documentElement).scrollTop <= 0;
  const blocked = t => !!t.closest?.('input, textarea, select, [contenteditable], [data-no-ptr], .kslide, .sl, #vol, .hours, .chips, .rooms, #nvl, #nvcam, dialog, [role=slider], input[type=range]');
  // move/end are also followed on the touched element itself: if the page redraws it, events no longer reach window
  const onMove = e => {
    if (y0 === null || e.__dk) return; e.__dk = 1; pull = e.touches[0].clientY - y0;
    if (pull <= 0 || !atTop()) { ind.style.opacity = 0; return; }
    const k = Math.min(1, pull / 90); ind.style.opacity = k; ind.style.transform = `translateY(${-70 + k * 70}px) rotate(${k * 270}deg)`; ind.classList.toggle('ready', pull >= 90);
  };
  const onEnd = e => { if (y0 === null || e.__dk) return; e.__dk = 1; y0 = null; if (pull >= 90 && atTop()) return reload();
    ind.style.opacity = 0; ind.style.transform = 'translateY(-70px)'; ind.classList.remove('ready'); };
  addEventListener('touchstart', e => { y0 = null; if (e.touches.length !== 1 || !atTop() || blocked(e.target)) return; y0 = e.touches[0].clientY; pull = 0;
    e.target.addEventListener('touchmove', onMove, { passive: true }); e.target.addEventListener('touchend', onEnd); e.target.addEventListener('touchcancel', onEnd); }, { passive: true });
  addEventListener('touchmove', onMove, { passive: true }); addEventListener('touchend', onEnd); addEventListener('touchcancel', onEnd);

  // ---- ↻ button (home-screen apps; pages can place it with deckRefresh.button(container)) ----
  function button(into) {
    if (document.getElementById('dkreload')) return;
    const b = document.createElement('button'); b.id = 'dkreload'; b.textContent = '↻'; b.title = 'Reload this panel'; b.setAttribute('aria-label', 'Reload this panel');
    b.addEventListener('click', reload);
    if (into) { b.classList.add('inline'); into.appendChild(b); } else document.body.appendChild(b);
  }
  // ---- stale after a long time in the background ----
  let hiddenAt = 0;
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden') hiddenAt = Date.now();
    else if (hiddenAt && Date.now() - hiddenAt > 15 * 60000) reload(); });
  addEventListener('pageshow', e => { if (e.persisted && hiddenAt && Date.now() - hiddenAt > 15 * 60000) reload(); });
  window.deckRefresh = { reload, button, standalone };
})();
