/* Edit mode for Home Deck pages (Admin, Start, Family info): a top bar (Done / Cancel / Undo last save / Reset),
   an edit sheet with fields, and saving to /api/layout/<page> (the server keeps every previous save).
   Pages own their layout model; this file only provides the UI pieces and storage calls. */
window.Edit = (() => {
  const css = document.createElement('style');
  css.textContent = `
  #ebar { position: fixed; left: 0; right: 0; top: 0; z-index: 80; display: flex; gap: 8px; align-items: center; flex-wrap: wrap;
    padding: calc(env(safe-area-inset-top) + 8px) calc(env(safe-area-inset-right) + 12px) 8px calc(env(safe-area-inset-left) + 12px);
    background: rgba(20,16,36,.94); -webkit-backdrop-filter: blur(14px); backdrop-filter: blur(14px); border-bottom: 1px solid rgba(56,189,248,.5);
    font: 14px -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Roboto, sans-serif; color: #f6f4fb; }
  #ebar b { flex: 1; min-width: 120px; font-size: 15px; } #ebar small { display: block; font-weight: 400; color: rgba(246,244,251,.6); font-size: 12px; }
  #ebar button, .esheet button { font: inherit; font-weight: 650; min-height: 40px; padding: 0 14px; border-radius: 999px; border: 1px solid rgba(255,255,255,.14);
    background: rgba(255,255,255,.08); color: inherit; cursor: pointer; }
  #ebar button.go, .esheet button.go { background: #38bdf8; border-color: transparent; }
  .esheet button.bad { color: #fecdd3; border-color: rgba(251,113,133,.45); }
  body.editing { padding-top: 64px; }
  @media (max-width: 600px) { #ebar button { min-height: 36px; padding: 0 12px; font-size: 14px; } #ebar b { min-width: 0; font-size: 14px; } #ebar small { display: none; } }
  .esheet .row button { padding: 0 13px; } .esheet h3 + .row { margin-top: 0; flex-direction: column; align-items: stretch; } .esheet h3 + .row .sp { display: none; }
  body.editing [data-edit] { outline: 1.5px dashed rgba(56,189,248,.7); outline-offset: 2px; cursor: pointer; }
  body.editing [data-edit]:hover { outline-color: #7dd3fc; }
  .eadd { display: block; width: 100%; margin-top: 8px; min-height: 46px; border-radius: 16px; border: 1.5px dashed rgba(56,189,248,.6); background: rgba(56,189,248,.08);
    color: #bae6fd; font: 600 14px -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, sans-serif; cursor: pointer; }
  .ehidden { opacity: .38; }
  #eback { position: fixed; inset: 0; z-index: 90; background: rgba(4,3,10,.6); display: flex; align-items: flex-end; justify-content: center; }
  .esheet { width: 100%; max-width: 560px; max-height: 88vh; overflow-y: auto; background: #17142a; color: #f6f4fb; border-radius: 24px 24px 0 0;
    border: 1px solid rgba(255,255,255,.1); padding: 18px 18px calc(env(safe-area-inset-bottom) + 18px); font: 15px -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Roboto, sans-serif; }
  @media (min-width: 700px) { #eback { align-items: center; } .esheet { border-radius: 24px; } }
  .esheet h3 { margin: 0 0 14px; font-size: 19px; }
  .esheet label { display: block; margin-bottom: 12px; font-size: 12.5px; color: rgba(246,244,251,.65); font-weight: 600; }
  .esheet input[type=text], .esheet textarea, .esheet select { display: block; width: 100%; margin-top: 5px; padding: 11px 12px; border-radius: 12px; font: 16px inherit;
    font-family: inherit; color: #fff; background: rgba(255,255,255,.07); border: 1px solid rgba(255,255,255,.14); outline: none; -webkit-appearance: none; appearance: none; }
  .esheet textarea { min-height: 70px; resize: vertical; }
  .esheet input:focus, .esheet textarea:focus, .esheet select:focus { border-color: #38bdf8; }
  .esheet .tog { display: flex; align-items: center; gap: 10px; font-size: 15px; color: #f6f4fb; font-weight: 500; }
  .esheet .tog input { width: 22px; height: 22px; accent-color: #38bdf8; }
  .esheet .row { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 16px; }
  .esheet .row .sp { flex: 1; }
  .esheet .hint { font-size: 12px; color: rgba(246,244,251,.5); margin-top: 4px; font-weight: 400; }
  .esheet .opts { display: grid; gap: 6px; margin-top: 6px; } .esheet .opts button { text-align: left; font-weight: 500; border-radius: 12px; }
  #etoast { position: fixed; left: 50%; bottom: calc(env(safe-area-inset-bottom) + 18px); transform: translateX(-50%); z-index: 95; padding: 11px 18px; border-radius: 999px;
    background: #1d1a2b; border: 1px solid rgba(255,255,255,.12); color: #fff; font: 600 14px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; opacity: 0; transition: opacity .2s; pointer-events: none; }
  #etoast.show { opacity: 1; }`;
  document.head.appendChild(css);
  const esc = t => String(t ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  async function call(page, body) {
    const r = await fetch('/api/layout/' + page, { method: body ? 'POST' : 'GET', cache: 'no-store',
      headers: { 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined });
    const j = await r.json(); if (!r.ok || j.error) throw new Error(j.error || 'HTTP ' + r.status);
    return body ? j.layout : j;
  }
  function toast(t) { let el = document.getElementById('etoast'); if (!el) { el = document.createElement('div'); el.id = 'etoast'; document.body.appendChild(el); }
    el.textContent = t; el.classList.add('show'); clearTimeout(toast.t); toast.t = setTimeout(() => el.classList.remove('show'), 2400); }

  /* sheet({title, fields: [{key, label, type: text|textarea|select|toggle|search, value, options, hint, search(q) -> [{value, label}]}],
           buttons: [{id, label, tone}]}) -> Promise<{action, values} | null> */
  function sheet({ title, fields = [], buttons = [] }) {
    return new Promise(done => {
      const back = document.createElement('div'); back.id = 'eback';
      const f = fields.map((x, i) => {
        if (x.type === 'toggle') return `<label class="tog"><input type="checkbox" data-k="${i}" ${x.value ? 'checked' : ''}>${esc(x.label)}</label>`;
        const inner = x.type === 'textarea' ? `<textarea data-k="${i}">${esc(x.value)}</textarea>`
          : x.type === 'select' ? `<select data-k="${i}">${x.options.map(([v, l]) => `<option value="${esc(v)}" ${String(v) === String(x.value) ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select>`
          : `<input type="text" data-k="${i}" value="${esc(x.value)}" autocomplete="off" autocapitalize="${x.type === 'url' ? 'off' : 'sentences'}" spellcheck="${x.type === 'url' ? 'false' : 'true'}"
              ${x.type === 'url' ? 'inputmode="url"' : ''}>${x.type === 'search' ? `<div class="opts" data-opts="${i}"></div>` : ''}`;
        return `<label>${esc(x.label)}${inner}${x.hint ? `<div class="hint">${esc(x.hint)}</div>` : ''}</label>`;
      }).join('');
      back.innerHTML = `<div class="esheet" role="dialog"><h3>${esc(title)}</h3>${f}<div class="row">${buttons.filter(b => b.tone === 'bad' || b.side).map(b =>
        `<button data-a="${b.id}" class="${b.tone || ''}">${esc(b.label)}</button>`).join('')}<span class="sp"></span><button data-a="cancel">Cancel</button>${buttons.filter(b => b.tone !== 'bad' && !b.side).map(b =>
        `<button data-a="${b.id}" class="${b.tone || 'go'}">${esc(b.label)}</button>`).join('')}</div></div>`;
      document.body.appendChild(back);
      const picked = {};
      fields.forEach((x, i) => { if (x.type !== 'search') return;      // live search, e.g. bus stops
        const inp = back.querySelector(`input[data-k="${i}"]`), box = back.querySelector(`[data-opts="${i}"]`); let t;
        inp.addEventListener('input', () => { clearTimeout(t); t = setTimeout(async () => {
          const res = await x.search(inp.value.trim()).catch(() => []);
          box.innerHTML = res.map((o, j) => `<button data-o="${j}">${esc(o.label)}</button>`).join('');
          box.querySelectorAll('button').forEach(b => b.addEventListener('click', e => { e.preventDefault(); const o = res[+b.dataset.o];
            picked[i] = o.value; inp.value = o.label; box.innerHTML = ''; }));
        }, 300); });
      });
      const close = action => { const values = {};
        fields.forEach((x, i) => { const el = back.querySelector(`[data-k="${i}"]`);
          values[x.key] = x.type === 'toggle' ? el.checked : x.type === 'search' ? (picked[i] ?? x.picked ?? null) : el.value.trim(); });
        back.remove(); done(action === 'cancel' ? null : { action, values }); };
      back.addEventListener('click', e => { if (e.target === back) close('cancel'); const b = e.target.closest('button[data-a]'); if (b) close(b.dataset.a); });
      back.addEventListener('keydown', e => { if (e.key === 'Escape') close('cancel'); if (e.key === 'Enter' && e.target.tagName === 'INPUT' && e.target.type === 'text' && !e.target.closest('label').querySelector('.opts')) {
        const go = back.querySelector('.row button.go'); if (go) { e.preventDefault(); close(go.dataset.a); } } });
      setTimeout(() => back.querySelector('input[type=text], textarea')?.focus(), 50);
    });
  }

  /* start({page, title, get(), set(layout), render(), extra: [{label, run}]}): shows the bar, Done saves get() */
  function start(o) {
    if (document.getElementById('ebar')) return;
    const before = JSON.stringify(o.get());
    const bar = document.createElement('div'); bar.id = 'ebar';
    bar.innerHTML = `<b>Editing ${esc(o.title)}<small>Tap a dashed item to change it</small></b>
      <button data-a="more">More…</button><button data-a="cancel">Cancel</button><button data-a="done" class="go">Done</button>`;
    document.body.appendChild(bar); document.body.classList.add('editing'); o.render();
    const pad = () => { document.body.style.paddingTop = bar.offsetHeight + 'px'; };
    pad(); addEventListener('resize', pad);
    const stop = () => { bar.remove(); removeEventListener('resize', pad); document.body.style.paddingTop = ''; document.body.classList.remove('editing'); o.render(); };
    bar.addEventListener('click', async e => {
      let a = e.target.closest('button[data-a]')?.dataset.a; if (!a) return;
      if (a === 'more') {
        const r = await sheet({ title: 'More', buttons: [...(o.extra || []).map((x, i) => ({ id: 'x' + i, label: x.label, side: true })),
          { id: 'undo', label: 'Undo last save', side: true }, { id: 'reset', label: 'Reset to original', tone: 'bad' }] });
        if (!r) return;
        if (r.action[0] === 'x') return o.extra[+r.action.slice(1)].run();
        a = r.action;
      }
      try {
        if (a === 'cancel') { o.set(JSON.parse(before)); stop(); }
        else if (a === 'done') { const saved = await call(o.page, { layout: o.get() }); o.set(saved); stop(); toast('Saved'); }
        else if (a === 'undo') { if (!confirm('Go back to the version before the last save?')) return; o.set(await call(o.page, { revert: true })); stop(); toast('Previous version restored'); }
        else if (a === 'reset') { if (!confirm('Reset this page to its original layout? (The current one is kept as a backup.)')) return; o.set(await call(o.page, { reset: true })); stop(); toast('Back to the original layout'); }
      } catch (err) { toast('Could not save: ' + err.message); }
    });
  }
  const move = (arr, i, d) => { const j = i + d; if (j < 0 || j >= arr.length) return; [arr[i], arr[j]] = [arr[j], arr[i]]; };
  return { load: page => call(page).catch(() => ({})), sheet, start, toast, move, esc };
})();
