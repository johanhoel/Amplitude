"""Local AI panel (/localai): the language models on the PC's RTX 5090 (Ollama), through deck-listener's /llm/* actions.

  state()            PC awake?, Ollama up?, GPU use, game running, each model (installed, loaded, VRAM, loaded until),
                     who loaded it (this panel, or probably the AI coordinator), and the action running now
  act(kind, ...)     load / unload a model, open OpenCode / Claude Code / video-use on the PC's screen. deck-listener
                     answers one request at a time and a first load takes up to a minute, so actions run in the
                     background here and state() reports them; the panel never waits on the PC
  chats / chat_*     saved chats: each answer is a job here that keeps going when the page closes or the phone sleeps;
                     one answer at a time (one GPU), the rest wait; a cut-off answer keeps what arrived. Files in
                     $STATE/chats (private). Ollama has no login, so it is never exposed to phones; all of it needs the PIN
The AI coordinator (.55) loads models only for the length of one request, so a loaded model this panel did not
load is most likely in use by the coordinator: the panel warns before unloading it.
"""
import json, os, queue, re, threading, time, urllib.request

from .config import C, STATE
from .store import load, save

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


# ---------- saved chats: each answer is a job on Home Deck, not tied to the browser ----------
CHATS = os.path.join(STATE, 'chats')           # one private JSON file per chat (never in git, never logged)
_queue = queue.Queue()                         # one GPU: answers run one at a time, the rest wait
_stop = set()                                  # chat ids asked to stop
_clock = threading.Lock()
# The models are trained to use tools. Without this, qwen3.8 says "Let me explore the project setup" and stops.
SYSTEM = ("You are a chat assistant on a home panel. You have no tools: you cannot read files, run commands, "
          "browse the web or open LinkedIn. Never say you will look, explore or check something. "
          "Do the whole task in this one reply. When the user asks for code, write the complete code now. "
          "If you need facts you do not have, use clear placeholders and say which ones to replace.")


def _cpath(cid):
    return os.path.join(CHATS, cid + '.json')


def _cload(cid):
    if not re.fullmatch(r'c-\d{8}-\d{6}-[0-9a-f]{4}', cid or '') or not os.path.exists(_cpath(cid)):
        return None
    return load(_cpath(cid), None)


def _csave(c):
    os.makedirs(CHATS, mode=0o700, exist_ok=True)
    c['updated'] = time.time()
    save(_cpath(c['id']), c, private=True)


def chats():
    """The list: newest first, without the messages."""
    out = []
    if os.path.isdir(CHATS):
        for f in os.listdir(CHATS):
            if f.endswith('.json'):
                c = load(os.path.join(CHATS, f), None)
                if c:
                    out.append({k: c.get(k) for k in ('id', 'model', 'title', 'created', 'updated', 'status')} | {'n': len(c.get('messages', []))})
    return sorted(out, key=lambda c: c['updated'] or 0, reverse=True)


def chat_get(cid):
    return _cload(cid)


def chat_send(req):
    """Add a question to a chat (a new one when no id) and queue the answer. Returns the chat."""
    names = {m['id']: m['model'] for m in _last.get('models', [])} or {'qwen38': 'qwen3.8:27b', 'gemma4': 'gemma4:26b',
                                                                       'coder': 'qwen3-coder:30b', 'small': 'qwen3:4b-instruct-2507-q4_K_M'}
    text = str(req.get('text') or '').strip()[:20000]
    if not text:
        raise ValueError('nothing to send')
    with _clock:
        c = _cload(req.get('id')) if req.get('id') else None
        if c and c['status'] in ('answering', 'waiting'):
            raise ValueError('this chat is still answering')
        mid = req.get('model') if req.get('model') in names else (c or {}).get('model_id')
        if mid not in names:
            raise ValueError('pick a model')
        if not c:
            now = time.strftime('%Y%m%d-%H%M%S')
            c = {'id': f'c-{now}-{os.urandom(2).hex()}', 'created': time.time(), 'title': text.split('\n')[0][:80], 'messages': []}
        c.update(model_id=mid, model=names[mid], status='waiting', note='')
        c['messages'] += [{'role': 'user', 'content': text, 'at': time.time()},
                          {'role': 'assistant', 'content': '', 'at': time.time(), 'model': names[mid]}]
        _csave(c)
    _queue.put(c['id'])
    return c


def chat_stop(cid):
    c = _cload(cid)
    if not c:
        raise ValueError('unknown chat')
    _stop.add(cid)
    if c['status'] == 'waiting':                   # not started yet: just mark it
        c.update(status='stopped', note='stopped before it started'); _csave(c)


def chat_delete(cid):
    c = _cload(cid)
    if not c:
        raise ValueError('unknown chat')
    if c['status'] in ('answering', 'waiting'):
        raise ValueError('stop it first')
    os.remove(_cpath(cid))


def _answer(cid):
    c = _cload(cid)
    if not c or c['status'] != 'waiting' or cid in _stop:
        _stop.discard(cid)
        return
    c['status'] = 'answering'; _csave(c)
    msgs = [{'role': 'system', 'content': SYSTEM}] + [{'role': m['role'], 'content': m['content']} for m in c['messages'][:-1]][-40:]
    ans, done, last_save = c['messages'][-1], False, 0
    try:
        body = json.dumps({'model': c['model'], 'messages': msgs, 'stream': True, 'think': False,
                           'keep_alive': '30m'}).encode()             # same as the panel's Load, not Ollama's default
        req = urllib.request.Request(C.OLLAMA + '/api/chat', data=body, headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=300) as r:
            for line in r:
                if cid in _stop:
                    break
                if not line.strip():
                    continue
                j = json.loads(line)
                if j.get('error'):
                    raise RuntimeError(j['error'])
                ans['content'] += (j.get('message') or {}).get('content', '')
                done = bool(j.get('done'))
                if time.time() - last_save > 0.7:      # the page follows the saved file
                    _csave(c); last_save = time.time()
        if cid in _stop:
            c.update(status='stopped', note='stopped')
        elif done:
            c.update(status='done', note='')
        else:
            c.update(status='cut off', note='the answer ended early (model unloaded or the PC went to sleep)')
    except Exception as e:
        why = 'the PC did not answer (asleep?)' if 'timed out' in str(e) or 'refused' in str(e) or 'unreachable' in str(e) else str(e)[:160]
        c.update(status='cut off', note=why)
    finally:
        _stop.discard(cid)
        _csave(c)


def chat_worker():
    for c in chats():                              # after a restart: nothing is running any more
        if c['status'] in ('answering', 'waiting'):
            full = _cload(c['id']); full.update(status='cut off', note='Home Deck restarted while it was answering'); _csave(full)
    while True:
        _answer(_queue.get())


def valid_id(s):
    return bool(re.fullmatch(r'[a-z0-9]{1,20}', s or ''))
