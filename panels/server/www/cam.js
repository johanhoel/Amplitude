/* Home Deck camera popup - <script src="/cam.js" defer></script> on any panel (nav.js loads it on the ring panels).
 * The front camera live over the current panel: MJPEG from /api/cam/<entity>/stream (the server ends it after 10 min),
 * a snapshot if the stream fails, full screen, Esc / tap outside to close (the stream stops then). A new camera event opens it
 * automatically for 60 s (per-device switch, localStorage navCamAuto). Without the nav pill it adds its own camera button.
 * data-links="0" on the script tag (family pages): no link to other panels inside the popup; data-bottom="84" lifts the camera button
 * above a page's own bottom bar; data-into="<selector>" puts it inside a header instead of floating.
 * Also loads /refresh.js (pull-to-refresh + ↻ for home-screen apps) so every page with cam.js gets it. Key: C opens it.
 */
(() => {
  if (window.deckCam) return;
  const me = document.currentScript || document.querySelector('script[src$="/cam.js"]');
  const LINKS = (me?.dataset.links ?? '1') !== '0';
  const store = { get(k, d) { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } }, set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} } };
  const css = document.createElement('style');
  css.textContent = `
  #nvcam { position: fixed; inset: 0; z-index: 95; display: none; align-items: center; justify-content: center; background: rgba(4,3,10,.7);
    -webkit-backdrop-filter: blur(8px); backdrop-filter: blur(8px); padding: calc(env(safe-area-inset-top) + 14px) 14px calc(env(safe-area-inset-bottom) + 14px); }
  #nvcam.open { display: flex; }
  #nvcam .win { position: relative; width: min(100%, 1100px); border-radius: 22px; overflow: hidden; background: #000; border: 1px solid rgba(255,255,255,.14);
    box-shadow: 0 30px 90px rgba(0,0,0,.7); font: 600 14px -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, sans-serif; color: #fff; }
  #nvcam img { display: block; width: 100%; aspect-ratio: 16/9; object-fit: contain; background: #000; }
  #nvcam .top { position: absolute; left: 0; right: 0; top: 0; display: flex; align-items: center; gap: 10px; padding: 12px 14px; background: linear-gradient(rgba(0,0,0,.7), transparent); }
  #nvcam .live { padding: 3px 9px; border-radius: 6px; background: #e11d48; font-size: 11px; letter-spacing: .08em; } #nvcam .live.wait { background: rgba(255,255,255,.2); }
  #nvcam .ttl { flex: 1; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-shadow: 0 1px 4px #000; }
  #nvcam .top button { width: 40px; height: 40px; border-radius: 50%; border: 0; background: rgba(0,0,0,.45); color: #fff; font-size: 17px; cursor: pointer; }
  #nvcam .bot { position: absolute; left: 0; right: 0; bottom: 0; display: flex; justify-content: space-between; align-items: center; gap: 10px; padding: 10px 14px;
    background: linear-gradient(transparent, rgba(0,0,0,.7)); font-size: 12.5px; font-weight: 500; }
  #nvcam .bot label { display: flex; gap: 7px; align-items: center; cursor: pointer; } #nvcam .bot input { width: 18px; height: 18px; accent-color: #7dd3fc; }
  #nvcam .bot a { color: #bae6fd; }
  #nvcam.alert .win { animation: nvpulse 1.2s ease 2; } @keyframes nvpulse { 50% { box-shadow: 0 0 0 6px rgba(225,29,72,.7), 0 30px 90px rgba(0,0,0,.7); } }
  #nvcamfab { position: fixed; right: calc(env(safe-area-inset-right) + 16px); bottom: calc(env(safe-area-inset-bottom) + var(--camfab-bottom, 16px)); z-index: 58;
    width: 48px; height: 48px; border-radius: 50%; border: 1px solid rgba(255,255,255,.14); background: rgba(18,16,32,.8); color: #fff; font-size: 20px; cursor: pointer;
    -webkit-backdrop-filter: blur(14px); backdrop-filter: blur(14px); box-shadow: 0 10px 30px rgba(0,0,0,.4); display: grid; place-items: center; }
  #nvcamfab:active { transform: scale(.94); }
  #nvcamfab.inline { position: static; width: 40px; height: 40px; font-size: 17px; box-shadow: none; flex: none; }`;
  document.head.appendChild(css);
  // ---------- camera popup (live MJPEG from /api/cam/<entity>/stream; ends after 10 min server-side) ----------
  const C = document.createElement('div'); C.id = 'nvcam'; C.setAttribute('role', 'dialog'); C.setAttribute('aria-label', 'Front camera live');
  C.innerHTML = `<div class="win"><img id="nvcamimg" alt="Front camera, live"><div class="top"><span class="live wait" id="nvcamlive">CONNECTING</span>
    <span class="ttl" id="nvcamttl">Front camera</span><button id="nvcamfs" aria-label="Full screen" title="Full screen">⤢</button><button id="nvcamx" aria-label="Close" title="Close (Esc)">✕</button></div>
    <div class="bot"><label><input type="checkbox" id="nvcamauto"> Pop up on camera events</label><span id="nvcamclock"></span>${LINKS ? '<a href="/security">Visits ›</a>' : ''}</div></div>`;
  document.body.appendChild(C);
  const img = C.querySelector('#nvcamimg');
  let camEntity = null, camTimer = null, camClock = null, camSnap = null;
  document.getElementById('nvcamauto').checked = store.get('navCamAuto', true);
  document.getElementById('nvcamauto').addEventListener('change', e => store.set('navCamAuto', e.target.checked));
  async function camOpen(reason) {
    if (!camEntity) { try { camEntity = (await (await fetch('/api/cams', { cache: 'no-store' })).json())[0]?.entity; } catch {} }
    if (!camEntity) { alert('No camera available right now.'); return; }
    C.classList.add('open'); C.classList.toggle('alert', !!reason);
    document.getElementById('nvcamttl').textContent = reason || 'Front camera';
    const live = document.getElementById('nvcamlive'); live.textContent = 'CONNECTING'; live.classList.add('wait');
    const t0 = performance.now();
    // stream failed: snapshots every 5 s (labelled as such), a new try at live every 30 s
    const snapMode = () => { live.textContent = 'NO SIGNAL'; live.classList.add('wait'); clearInterval(camSnap);
      const snap = () => { img.onload = () => { live.textContent = 'SNAPSHOT ' + new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }); live.classList.add('wait'); };
        img.onerror = null; img.src = `/api/cam/${camEntity}/snap?w=1280&t=${Date.now()}`; };
      snap(); let n = 0; camSnap = setInterval(() => { if (++n % 6) snap(); else startLive(); }, 5000); };
    const startLive = () => { img.onload = () => { clearInterval(camSnap); live.textContent = 'LIVE'; live.classList.remove('wait'); window.deckCamFirstFrameMs = Math.round(performance.now() - t0); };
      img.onerror = snapMode; img.src = `/api/cam/${camEntity}/stream?t=${Date.now()}`; };
    startLive();
    clearInterval(camClock); const tick = () => document.getElementById('nvcamclock').textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
    tick(); camClock = setInterval(tick, 1000);
    clearTimeout(camTimer); if (reason) camTimer = setTimeout(camClose, 60000);
    setTimeout(() => document.getElementById('nvcamx').focus({ preventScroll: true }), 30);   // keys (Esc) reach this page, not an embedded frame
  }
  function camClose() { C.classList.remove('open', 'alert'); clearInterval(camSnap); img.onload = img.onerror = null; img.removeAttribute('src'); clearInterval(camClock); clearTimeout(camTimer);
    if (document.fullscreenElement) document.exitFullscreen?.(); }
  document.getElementById('nvcamx').addEventListener('click', camClose);
  C.addEventListener('click', e => { if (e.target === C) camClose(); });
  document.getElementById('nvcamfs').addEventListener('click', () => { const w = C.querySelector('.win');
    if (document.fullscreenElement) document.exitFullscreen(); else if (w.requestFullscreen) w.requestFullscreen(); else if (img.webkitEnterFullscreen) img.webkitEnterFullscreen(); });
  document.addEventListener('visibilitychange', () => { if (document.visibilityState !== 'visible' && C.classList.contains('open')) camClose(); });
  // automatic popup: the server's "last camera event" changes the moment the front camera starts an event
  let lastEv;
  async function watchEvents() {
    if (document.visibilityState !== 'visible') return;
    try { const j = await (await fetch('/api/presence/unassigned', { cache: 'no-store' })).json();
      const ev = j.last_camera_event || null;
      if (lastEv !== undefined && ev && ev !== lastEv && store.get('navCamAuto', true) && !C.classList.contains('open')) camOpen('Motion at the front door · ' + new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false }));
      lastEv = ev; } catch {}
  }
  watchEvents(); setInterval(watchEvents, 4000);

  const typing = () => /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName) || document.activeElement?.isContentEditable;
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && C.classList.contains('open')) { e.stopPropagation(); return camClose(); }
    if (e.key.toLowerCase() === 'c' && !e.metaKey && !e.ctrlKey && !e.altKey && !typing() && !C.classList.contains('open')
        && !document.getElementById('nvl')?.classList.contains('open')) camOpen();
  }, true);
  window.deckCam = { open: camOpen, close: camClose, isOpen: () => C.classList.contains('open') };
  // own button unless the nav pill has one
  const addFab = () => { if (document.getElementById('nvcambtn') || document.getElementById('nvcamfab')) return;
    const b = document.createElement('button'); b.id = 'nvcamfab'; b.innerHTML = '<i class="icon icon-camera" aria-hidden="true"></i>'; b.setAttribute('aria-label', 'Front camera live'); b.title = 'Camera live (C)';
    const into = me?.dataset.into && document.querySelector(me.dataset.into);   // long card pages: a header button instead of a floating one
    if (into) { b.classList.add('inline'); b.addEventListener('click', () => camOpen()); into.appendChild(b); return; }
    if (me?.dataset.bottom) b.style.setProperty('--camfab-bottom', me.dataset.bottom + 'px');
    b.addEventListener('click', () => camOpen()); document.body.appendChild(b); };
  setTimeout(addFab, 0);
  // refresh (pull-to-refresh, ↻ in home-screen apps, reload after a long background) lives in refresh.js
  const placeReload = () => { const R = window.deckRefresh; if (!R || !R.standalone || document.getElementById('nvorb')) return;
    const into = me?.dataset.into && document.querySelector(me.dataset.into);
    if (!into) document.documentElement.style.setProperty('--dkr-bottom', ((+me?.dataset.bottom || 16) + 58) + 'px');
    R.button(into || null); };
  if (window.deckRefresh) setTimeout(placeReload, 0);
  else { const sc = document.createElement('script'); sc.src = '/refresh.js'; sc.onload = () => setTimeout(placeReload, 0); document.body.appendChild(sc); }
})();
