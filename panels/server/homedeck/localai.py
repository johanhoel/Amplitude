"""Local AI panel (/localai): the language models on the PC's RTX 5090 (Ollama), through deck-listener's /llm/* actions.

  state()            PC awake?, Ollama up?, GPU use, game running, each model (installed, loaded, VRAM, loaded until),
                     who loaded it (this panel, or probably the AI coordinator), and the action running now
  act(kind, ...)     load / unload a model, open OpenCode / Claude Code / video-use on the PC's screen. deck-listener
                     answers one request at a time and a first load takes up to a minute, so actions run in the
                     background here and state() reports them; the panel never waits on the PC
  chat(...)          Ollama /api/chat on the PC, streamed through Home Deck (Ollama has no login; it is never exposed
                     to phones directly, and the panel is behind the admin PIN)
The AI coordinator (.55) loads models only for the length of one request, so a loaded model this panel did not
load is most likely in use by the coordinator: the panel warns before unloading it.
"""
import json, re, threading, time, urllib.request

from .config import C

_job = {}                      # the action running now / the last one: {action, label, started, done, ok, result}
_ours = {}                     # model id -> when this panel loaded it
_last = {}                     # last good /llm/status (shown while the PC is busy with a load)
_lock = threading.Lock()
LONG = 180                     # a first load of a 27-30B model can take a minute


def _pc(path, timeout=6, post=False):
    req = urllib.request.Request(f'http://{C.PC[0]}:{C.PC[1]}{path}', data=b'' if post else None, method='POST' if post else 'GET')
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode(errors='replace')


def _busy():
    return bool(_job) and not _job.get('done')


def state():
    if _busy():                                     # the listener is busy with our load: show the last status
        return {'awake': True, 'busy': True, 'job': dict(_job), **_last}
    try:
        st = json.loads(_pc('/llm/status', 6))
    except Exception:
        try:
            _pc('/health', 3)
            return {'awake': True, 'error': 'the PC answers, but not /llm/status', 'job': dict(_job)}
        except Exception:
            return {'awake': False, 'job': dict(_job)}
    for m in st.get('models', []):
        m['by'] = 'panel' if m.get('loaded') and m['id'] in _ours else 'other' if m.get('loaded') else None
        if not m.get('loaded'):
            _ours.pop(m['id'], None)
    _last.clear(); _last.update(st)
    return {'awake': True, **st, 'job': dict(_job)}


def _known():
    ids = {m['id'] for m in _last.get('models', [])}
    return ids or {'qwen38', 'gemma4', 'coder', 'small'}


def act(kind, mid='', setup=''):
    """kind: load | unload | launch | video-use. Returns at once; the work runs in the background."""
    if kind in ('load', 'unload', 'launch') and mid not in _known():
        raise ValueError('unknown model')
    if kind == 'launch' and setup not in ('opencode', 'claude'):
        raise ValueError('unknown setup')
    path, label, timeout = {
        'load': (f'/llm/load/{mid}', f'loading {mid}', LONG),
        'unload': (f'/llm/unload/{mid}', f'unloading {mid}', 60),
        'launch': (f'/llm/launch/{setup}/{mid}', f'opening {"Claude Code" if setup == "claude" else "OpenCode"} with {mid}', 30),
        'video-use': ('/llm/launch/video-use', 'opening video-use', 30),
    }.get(kind, (None, None, None))
    if not path:
        raise ValueError('unknown action')
    with _lock:
        if _busy():
            raise ValueError('the PC is still busy: ' + _job['label'])
        _job.clear(); _job.update(action=kind, model=mid, label=label, started=time.time(), done=False)

    def run():
        try:
            res = _pc(path, timeout, post=True)
            if kind == 'load':
                _ours[mid] = time.time()
            elif kind == 'unload':
                _ours.pop(mid, None)
            _job.update(ok=True, result=res.strip()[:200])
        except Exception as e:
            _job.update(ok=False, result=('the PC did not answer' if 'timed out' in str(e) or 'refused' in str(e) else str(e))[:200])
        finally:
            _job.update(done=True, ended=time.time())
    threading.Thread(target=run, daemon=True).start()
    return {'ok': True, 'started': label}


def chat(handler, req):
    """Stream Ollama's /api/chat answer (NDJSON lines) straight to the browser."""
    names = {m['id']: m['model'] for m in _last.get('models', [])}
    model = names.get(req.get('model'))
    if not model:
        return handler.send_json({'error': 'pick a model'}, 400)
    msgs = [{'role': m['role'], 'content': str(m.get('content', ''))[:20000]} for m in (req.get('messages') or [])[-30:]
            if isinstance(m, dict) and m.get('role') in ('user', 'assistant', 'system')]
    if not msgs:
        return handler.send_json({'error': 'nothing to send'}, 400)
    body = json.dumps({'model': model, 'messages': msgs, 'stream': True, 'think': bool(req.get('think'))}).encode()
    try:
        r = urllib.request.urlopen(urllib.request.Request(C.OLLAMA + '/api/chat', data=body, headers={'Content-Type': 'application/json'}),
                                   timeout=300)
    except Exception as e:
        return handler.send_json({'error': 'the PC did not answer' if 'timed out' in str(e) or 'refused' in str(e) else str(e)[:200]}, 502)
    handler.send_response(200)
    handler.send_header('Content-Type', 'application/x-ndjson'); handler.send_header('Cache-Control', 'no-store')
    handler.send_header('Connection', 'close'); handler.end_headers()
    handler.close_connection = True
    with r:
        for line in r:
            try:
                handler.wfile.write(line); handler.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                return                                   # the phone pressed Stop or left: closing r stops Ollama too


def valid_id(s):
    return bool(re.fullmatch(r'[a-z0-9]{1,20}', s or ''))
