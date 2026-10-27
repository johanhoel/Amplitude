"""Genelec Smart IP speakers (volume, mute, power; password in secrets.json) and Dante source switching (netaudio).
Speakers and sources: [audio] in homedeck.toml."""
import base64, json, subprocess, urllib.request

from .config import C
from .store import secret


def gen_req(ip, method, path, body=None):
    pw = secret('genelec_password')
    if not pw:
        return None
    auth = base64.b64encode(f'admin:{pw}'.encode()).decode()
    req = urllib.request.Request(f'http://{ip}:9000/public/v1/{path}', method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={'Authorization': 'Basic ' + auth, 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=3) as r:
        data = r.read()
        return json.loads(data) if data else {}


def genelec_summary():
    if not secret('genelec_password'):
        return {'configured': False}
    out = {'configured': True, 'speakers': []}
    for ip in C.GENELECS:
        spk = {'ip': ip, 'ok': True}
        try:
            p = gen_req(ip, 'GET', 'device/pwr') or {}
            spk['power'] = p.get('state')
        except Exception as e:
            spk.update(ok=False, error='pwr: ' + str(e)[:70])
        try:
            v = gen_req(ip, 'GET', 'audio/volume') or {}
            spk.update(level=v.get('level'), mute=v.get('mute'))
        except Exception as e:
            spk['vol_error'] = str(e)[:70]   # 503 while the speaker sleeps (ISS / standby)
        out['speakers'].append(spk)
    first = next((s for s in out['speakers'] if s.get('ok') and s.get('level') is not None), None)
    out['level'] = first['level'] if first else None
    out['mute'] = first['mute'] if first else None
    out['power'] = next((x['power'] for x in out['speakers'] if x.get('power')), None)
    # every reachable speaker refuses the password -> the card asks for it again
    reach = [x for x in out['speakers'] if 'timed out' not in x.get('error', '') and 'No route' not in x.get('vol_error', '')]
    out['auth_failed'] = bool(reach) and all('401' in x.get('error', '') for x in reach)
    return out


def genelec_do(action, value):
    """POST /api/genelec: one speaker off/asleep must not block the others. -> (done ips, errors)"""
    body = {'volume': lambda: {'level': max(-130.0, min(0.0, float(value)))},
            'mute': lambda: {'mute': bool(value)}}.get(action)
    done, errors = [], []
    for ip in C.GENELECS:
        try:
            if action == 'power':
                gen_req(ip, 'PUT', 'device/pwr', {'state': 'ACTIVE' if value else 'STANDBY'})
            elif body:
                gen_req(ip, 'PUT', 'audio/volume', body())
            done.append(ip)
        except Exception as e:
            errors.append(f"{ip.rsplit('.', 1)[1]}: {str(e)[:60]}")
    return done, errors


def dante_summary():
    try:
        r = subprocess.run([C.NETAUDIO, '--output', 'json', 'subscription', 'list'],
                           capture_output=True, text=True, timeout=45)
        subs = json.loads(r.stdout)
    except Exception as e:
        return {'ok': False, 'error': str(e)[:80]}
    front = [s for s in subs if s.get('rx_device') in C.FRONT_PAIR]
    tx = {s.get('tx_device') for s in front}
    source = next((k for k, (dev, _) in C.SOURCES.items() if tx == {dev}), 'mixed' if tx else 'none')
    live = sum(1 for s in front if (s.get('status') or {}).get('state') in ('connected', 'ok', 'subscribed')
               or (s.get('status') or {}).get('severity') == 'ok')
    devices = sorted({s.get('rx_device') for s in subs})
    return {'ok': True, 'source': source, 'front_live': live, 'front_total': len(front), 'devices': devices,
            'routes': [{'rx': f"{s['rx_device']}:{s['rx_channel']}", 'tx': f"{s.get('tx_device')}:{s.get('tx_channel')}",
                        'state': (s.get('status') or {}).get('label')} for s in subs]}


def dante_set_source(src):
    dev, chans = C.SOURCES[src]
    for rx in C.FRONT_PAIR:
        for i, ch in enumerate(chans, start=1):
            subprocess.run([C.NETAUDIO, 'subscription', 'add', '--tx', f'{ch}@{dev}', '--rx', f'{i}@{rx}'],
                           capture_output=True, text=True, timeout=45, check=True)
