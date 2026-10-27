/* Panel switcher for the older panels (the newer ones have it inline): adds a "More" entry that opens a list of every panel. */
(() => {
  const PANELS = [['/start', 'Start', 'all panels + consoles'], ['/', 'Deck', 'wall panel'], ['/living', 'Home', 'lights, music, door'], ['/family', 'Family', "who's home"], ['/familyinfo', 'Family info', 'buses'], ['/security', 'Security', 'camera, visits'],
    ['/media', 'Media', 'music, speakers, TV'], ['/net', 'Network', 'internet, devices'], ['/ops', 'Lab', 'Proxmox'], ['/ambient', 'Ambient', 'night clock'],
    ['/remote', 'Remote', 'phone'], ['/network.html', 'Network map', 'document']];
  const css = document.createElement('style');
  css.textContent = `#swp{position:fixed;inset:0;z-index:60;display:none;background:rgba(5,4,10,.86);padding:90px 22px}#swp.open{display:block}
    #swp nav{max-width:560px;margin:0 auto;display:grid!important;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px;background:none!important;border:0!important;padding:0!important}
    #swp a{display:block;padding:16px 18px;border-radius:999px;background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.1);color:#f4f4fb;text-decoration:none;font-weight:600;font-size:15px}
    #swp a small{display:block;color:rgba(244,244,251,.55);font-weight:400;font-size:12px}#swp a.on{background:#38bdf8;border-color:transparent}`;
  document.head.appendChild(css);
  const ov = document.createElement('div'); ov.id = 'swp';
  ov.innerHTML = '<nav>' + PANELS.map(([u, t, s]) => `<a href="${u}" class="${location.pathname.replace(/\/$/, '') === u ? 'on' : ''}">${t}<small>${s}</small></a>`).join('') + '</nav>';
  document.body.appendChild(ov);
  ov.addEventListener('click', e => { if (e.target === ov) ov.classList.remove('open'); });
  const host = document.querySelector('nav:not(#swp nav)');
  let more;
  if (host && host.id === 'tabs') {          // phone remote: a tab like the others
    more = document.createElement('button');
    more.innerHTML = '<svg viewBox="0 0 24 24"><circle cx="5" cy="5" r="1.6"/><circle cx="12" cy="5" r="1.6"/><circle cx="19" cy="5" r="1.6"/><circle cx="5" cy="12" r="1.6"/>'
      + '<circle cx="12" cy="12" r="1.6"/><circle cx="19" cy="12" r="1.6"/><circle cx="5" cy="19" r="1.6"/><circle cx="12" cy="19" r="1.6"/><circle cx="19" cy="19" r="1.6"/></svg>More';
  } else {
    more = document.createElement('a'); more.href = '#'; more.textContent = 'More';
  }
  more.className = 'more-panels';
  more.addEventListener('click', e => { e.preventDefault(); e.stopPropagation(); ov.classList.add('open'); });
  if (host) host.appendChild(more);
})();
