/* "‹ Start" link back to the landing page (/start), placed the way each panel already navigates:
   - pages with the round panel switcher (#sw, top right): a pill just left of it
   - pages with a header <nav> (ops, living): first item of that nav, so it takes the page's own nav style
   - the Deck (index): a chip in front of the status chips
   - anything else (remote, network map): a small floating pill, above the tab bar when there is one */
(() => {
  if (location.pathname.replace(/\/$/, '') === '/start') return;
  const label = '‹ Start';
  const pill = 'display:inline-flex;align-items:center;gap:6px;padding:0 16px;border-radius:999px;font:600 13.5px -apple-system,BlinkMacSystemFont,"SF Pro Display","Segoe UI",Inter,Roboto,sans-serif;'
    + 'color:#f4f5fb;text-decoration:none;background:rgba(20,22,34,.62);border:1px solid rgba(255,255,255,.14);'
    + 'backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);box-shadow:0 6px 22px rgba(0,0,0,.35);z-index:30;';
  const link = (css) => { const a = document.createElement('a'); a.href = '/start'; a.textContent = label; a.className = 'start-link';
    a.setAttribute('aria-label', 'Back to Start: all panels'); if (css) a.style.cssText = css; return a; };

  const sw = document.getElementById('sw');
  if (sw) {
    const r = getComputedStyle(sw);
    const a = link(pill + `position:fixed;top:${r.top};right:calc(${r.right} + ${sw.offsetWidth || 46}px + 10px);height:${sw.offsetHeight || 46}px;`);
    document.body.appendChild(a);
    return;
  }
  const nav = [...document.querySelectorAll('header nav, nav')].find(n => !n.id && !n.closest('#swp') && n.querySelector('a'));
  if (nav) { nav.insertBefore(link(), nav.firstChild); return; }
  const chips = document.querySelector('.chips');
  if (chips) { const a = link(); a.className = 'chip start-link'; a.style.cssText = 'text-decoration:none;color:inherit'; chips.insertBefore(a, chips.firstChild); return; }
  const tabs = document.getElementById('tabs');
  const bottom = tabs ? `calc(${tabs.offsetHeight}px + 12px)` : 'calc(env(safe-area-inset-bottom) + 16px)';
  document.body.appendChild(link(pill + `position:fixed;left:calc(env(safe-area-inset-left) + 14px);bottom:${bottom};height:40px;`));
})();
