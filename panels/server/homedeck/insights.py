"""Data for the Family and Network panels: Prometheus (DNS history, presence history, router, speed test),
camwatch-feed (camera visits) and the Pi-holes' device tables. Names: [network] in homedeck.toml."""
import datetime, json, time, urllib.parse, urllib.request

from .config import C
from .presence import presence
from .store import phones, tcp_ms


def prom(q, t=None):
    qs = {'query': q} if t is None else {'query': q, 'time': t}
    with urllib.request.urlopen(f'{C.PROM}/api/v1/query?' + urllib.parse.urlencode(qs), timeout=15) as r:
        return json.load(r)['data']['result']


def prom_range(q, start, end, step):
    qs = {'query': q, 'start': start, 'end': end, 'step': step}
    with urllib.request.urlopen(f'{C.PROM}/api/v1/query_range?' + urllib.parse.urlencode(qs), timeout=20) as r:
        return json.load(r)['data']['result']


def camfeed(path, raw=False):
    with urllib.request.urlopen(C.CAMFEED + path, timeout=8) as r:
        return r.read() if raw else json.load(r)


_family = {'at': 0, 'data': None}


def family_state():
    """Per person: home now + since when, segments since local midnight, online activity today, last seen."""
    if time.time() - _family['at'] < 20 and _family['data']:
        return _family['data']
    now = time.time()
    midnight = datetime.datetime.now(C.LOCAL_TZ).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    start = min(midnight, now - 6 * 3600)
    series = {r['metric']['person']: r['values'] for r in prom_range('max by (person) (home_presence)', start, now, 120)}
    people = []
    for person, macs in phones().items():
        dev = '|'.join(m.lower() for m in macs)
        vals = [(float(t), v == '1') for t, v in series.get(person, [])]
        segs, cur = [], None
        for t, h in vals:
            if not cur or cur['home'] != h:
                if cur: cur['to'] = t
                cur = {'home': h, 'from': t, 'to': now}; segs.append(cur)
        p = presence.get(person, {})
        last_change = segs[-1]['from'] if segs else None
        act = prom(f'sum(sum_over_time(pihole:device:count1m{{device=~"{dev}"}}[{max(60, int(now - midnight))}s]))')
        fun = prom(f'sum(sum_over_time(pihole:device_category:count1m{{device=~"{dev}", blocked="false", '
                   f'category=~"Social media|Streaming \\\\(video/music\\\\)|Games"}}[{max(60, int(now - midnight))}s]))')
        # first hour after midnight: start must not be after now (Prometheus answers 400)
        hourly = prom_range(f'sum(sum_over_time(pihole:device:count1m{{device=~"{dev}"}}[1h])) or vector(0)', min(midnight + 3600, now), now, 3600)
        people.append({'name': person.capitalize(), 'home': p.get('home'), 'silent_s': round(now - p['last']) if p.get('last') else None,
                       'since': last_change if (segs and segs[0]['from'] < last_change) else None,
                       'segments': [{'home': sg['home'], 'from': sg['from'], 'to': sg['to']} for sg in segs],
                       'lookups_today': round(float(act[0]['value'][1])) if act else 0,
                       'fun_today': round(float(fun[0]['value'][1])) if fun else 0,
                       'hourly': [round(float(v)) for _, v in (hourly[0]['values'] if hourly else [])]})
    arrivals = []
    try:
        for v in camfeed('/visits?days=1&limit=120'):
            for pp in v['people']:
                arrivals.append({'name': pp['name'], 'at': v['start'], 'day': v['day'], 'stem': v['stem']})
    except Exception:
        pass
    data = {'now': now, 'midnight': midnight, 'start': start, 'people': people, 'camera': arrivals[:20]}
    _family.update(at=time.time(), data=data)
    return data


_net = {'at': 0, 'data': None}


def net_state():
    if time.time() - _net['at'] < 15 and _net['data']:
        return _net['data']
    now = time.time()
    def series(q, minutes=60, step=60):
        r = prom_range(q, now - minutes * 60, now, step)
        return [[float(t), float(v)] for t, v in r[0]['values']] if r else []
    one = lambda q: (lambda r: float(r[0]['value'][1]) if r else None)(prom(q))
    wan_in = series('rate(ifHCInOctets{job="router",ifName="eth0"}[2m]) * 8', 120, 60)
    wan_out = series('rate(ifHCOutOctets{job="router",ifName="eth0"}[2m]) * 8', 120, 60)
    dns = series('sum(pihole:queries:count1m) or vector(0)', 120, 60)
    blocked = series('sum(pihole:device:count1m{status=~"GRAVITY.*|REGEX.*|DENYLIST.*|EXTERNAL_BLOCKED.*|SPECIAL_DOMAIN"}) or vector(0)', 120, 60)
    top_blocked = [{'domain': r['metric'].get('base_domain'), 'n': round(float(r['value'][1]))}
                   for r in prom('topk(6, sum by (base_domain) (sum_over_time(pihole:device_domain:count1m{blocked="true"}[1h])))')]
    top_blocked.sort(key=lambda x: -x['n'])
    devs = {}
    for h in C.PIHOLES:
        try:
            with urllib.request.urlopen(f'http://{h}/api/network/devices?max_devices=400', timeout=8) as r:
                for d in json.load(r)['devices']:
                    m = d['hwaddr'].lower()
                    if ':' not in m: continue
                    x = devs.setdefault(m, {'mac': m, 'last': 0, 'first': d.get('firstSeen') or 0, 'name': '', 'vendor': d.get('macVendor') or '', 'ip': ''})
                    x['last'] = max(x['last'], d.get('lastQuery') or 0)
                    x['first'] = min(x['first'] or 9e12, d.get('firstSeen') or 9e12)
                    for i in d.get('ips', []):
                        if i.get('name') and not x['name']: x['name'] = i['name'].replace('.lan', '')
                        if i.get('ip', '').startswith('192.168.1.') and (i.get('lastSeen') or 0) >= x.get('ip_seen', 0):
                            x['ip'], x['ip_seen'] = i['ip'], i.get('lastSeen') or 0     # the address it used most recently
        except Exception:
            pass
    owner = {m.lower(): p.capitalize() for p, macs in phones().items() for m in macs}
    # Proxmox guests/nodes + router: real up/down from Prometheus (labels as in [network.names])
    up_by_label = {}
    alias = {'pihole': 'Pi-hole', 'pihole2': 'Pi-hole 2', 'pbs': 'PBS', 'haos13.2': 'Home Assistant'}
    try:
        for r in prom('max by (name) (pve_up * on (id) group_left (name) pve_guest_info) or max by (name) (label_replace(pve_up{id=~"node/.*"}, "name", "$1", "id", "node/(.*)"))'):
            n = r['metric'].get('name', ''); up_by_label[alias.get(n, n)] = r['value'][1] == '1'
        up_by_label['Router PR460X'] = one('max(up{job="router"})') == 1
        up_by_label['gotify'] = one('max(probe_success{service="Gotify"})') == 1
    except Exception:
        pass
    lst = []
    for x in devs.values():
        if now - x['last'] > 7 * 86400 or x['mac'] == '00:00:00:00:00:00': continue
        octet = x['ip'].rsplit('.', 1)[-1] if x['ip'] else ''
        if not x['ip'] and not C.MAC_NAMES.get(x['mac']): continue                     # IPv6-only / nameless: noise
        if x['mac'].startswith('bc:24:11') and octet not in C.NET_NAMES: continue      # deleted Proxmox test guests
        kind, label = C.NET_NAMES.get(x['ip'].rsplit('.', 1)[-1], (None, None))
        x['label'] = label or C.MAC_NAMES.get(x['mac']) or x['name'] or (x['vendor'].split(',')[0].split(' ')[0] if x['vendor'] else 'Unknown device')
        x['kind'] = 'People' if x['mac'] in owner else kind or 'Computers & phones'
        x['owner'] = owner.get(x['mac'])
        x['online'] = now - x['last'] < 15 * 60
        if x['kind'] in ('Servers', 'Network'):                                         # quiet on DNS: use real up/down
            x['online'] = up_by_label.get(x['label'], x['online'])
        if x['kind'] == 'Network' and not x['online'] and x['ip']:                       # switches/APs: answer on their web port
            x['online'] = tcp_ms(x['ip'], 443, .6) is not None or tcp_ms(x['ip'], 80, .6) is not None
        x['new'] = now - x['first'] < 7 * 86400
        lst.append(x)
    have = {x['ip'].rsplit('.', 1)[-1] for x in lst if x['ip']}
    for octet, (kind, label) in C.NET_NAMES.items():                                     # infrastructure Pi-hole never sees
        if octet not in have and kind in ('Servers', 'Network'):
            lst.append({'mac': '', 'ip': f'192.168.1.{octet}', 'label': label, 'kind': kind, 'last': 0, 'first': 0, 'name': label,
                        'vendor': '', 'online': up_by_label.get(label, False), 'new': False, 'owner': None})
    lst.sort(key=lambda x: -x['last'])
    blocking = {}
    for h in C.PIHOLES:
        try:
            with urllib.request.urlopen(f'http://{h}/api/dns/blocking', timeout=4) as r:
                blocking[h] = json.load(r)
        except Exception:
            blocking[h] = None
    data = {'now': now, 'wan_in': wan_in, 'wan_out': wan_out, 'dns': dns, 'blocked': blocked, 'top_blocked': top_blocked,
            'speed': {'down': one('speedtest_download_bits_per_second'), 'up': one('speedtest_upload_bits_per_second'),
                      'ping': one('speedtest_ping_latency_seconds'), 'at': one('speedtest_last_run_timestamp_seconds')},
            'blocked_pct': one('pihole_ads_percentage_today'), 'queries_today': one('pihole_dns_queries_today'),
            'devices': lst, 'online': sum(1 for x in lst if x['online']), 'blocking': blocking,
            'services_up': one('sum(probe_success{job="services"})'), 'services_total': one('count(probe_success{job="services"})')}
    _net.update(at=time.time(), data=data)
    return data
