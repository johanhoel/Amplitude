"""Who is home, from the home Wi-Fi: both Pi-holes see every phone's DNS lookups.

Every 30 s (15 s during a camera burst) the Pi-holes' network tables give each family phone's last DNS query.
Quiet phones get a wake-up probe (UDP to mDNS, then watch the ARP entry). The result goes to Home Assistant as
device_tracker.<person>_home_wifi: a template device tracker fed by a per-person webhook (secrets.json
'presence_webhooks'; device_tracker.see is deprecated in HA 2027.5). Phones and timers: [presence] in homedeck.toml.
A front-camera event (camwatch) starts a burst of fast scans, so arrivals/departures show within a minute.
"""
import datetime, json, subprocess, socket, threading, time, urllib.request

from .config import C
from .store import NOCHECK, phones, secret


def ha_presence(person, home):
    """Tell Home Assistant: POST {"home": true|false} to the person's template device tracker webhook
    (device_tracker.<person>_home_wifi, defined in HA's configuration.yaml). No webhook for a person -> nothing sent."""
    wid = (secret('presence_webhooks') or {}).get(person)
    if not wid:
        return False
    req = urllib.request.Request(f'{C.HA}/api/webhook/{wid}', data=json.dumps({'home': bool(home)}).encode(), method='POST',
                                 headers={'Content-Type': 'application/json'})
    urllib.request.urlopen(req, context=NOCHECK, timeout=6).read()
    return True

presence = {}                                         # person -> {'home', 'last', 'sent', 'probe_ok', 'fails'}
cam_burst = {'until': 0, 'stem': None, 'at': 0, 'before': {}}
presence_wake = threading.Event()
last_seen_map = {}                                    # MAC -> last DNS query (latest presence scan)
unassigned_arrivals = []                              # [{mac, ip, at, stem}] phones not in PHONES that came back with a camera event
ip_person = {}                                        # LAN address -> person, from the family phones' Wi-Fi addresses


def arp_probe(ips, mac, wait=9):
    """Wake a (sleeping) phone with a UDP packet to mDNS port 5353, then watch the kernel's ARP entry: a phone
    on the Wi-Fi answers ARP even when locked (entry turns REACHABLE with its MAC), a phone that left cannot."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    for ip in ips:
        for _ in range(2):
            try:
                sock.sendto(b'\x00' * 12, (ip, 5353))
            except OSError:
                pass
    sock.close()
    t0 = time.time()
    while time.time() - t0 < wait:
        time.sleep(1)
        for ip in ips:
            try:
                out = subprocess.run(['ip', '-j', 'neigh', 'show', ip], capture_output=True, text=True, timeout=3).stdout
                for n in json.loads(out or '[]'):
                    if 'REACHABLE' in n.get('state', []) and (n.get('lladdr') or '').lower() == mac:
                        return True
            except Exception:
                pass
    return False


def presence_loop():
    while True:
        ips = {}
        try:
            seen = {}
            for h in C.PIHOLES:
                try:
                    with urllib.request.urlopen(f'http://{h}/api/network/devices?max_devices=300', timeout=8) as r:
                        for d in json.load(r)['devices']:
                            m = d['hwaddr'].lower()
                            seen[m] = max(seen.get(m, 0), d.get('lastQuery') or 0)
                            for i in d.get('ips', []):
                                if i.get('ip', '').startswith('192.168.1.'):
                                    ips.setdefault(m, {})[i['ip']] = max(ips.get(m, {}).get(i['ip'], 0), i.get('lastSeen') or 0)
                except Exception:
                    pass
            ph = phones()
            # quiet phones get an ARP wake-up probe (in parallel, ~9 s)
            probes = {}
            for person, macs in ph.items():
                last = max((seen.get(m.lower(), 0) for m in macs), default=0)
                burst = time.time() < cam_burst['until']
                if seen and time.time() - last > (60 if burst else C.PROBE_AFTER):
                    for m in macs:
                        cand = sorted(ips.get(m.lower(), {}), key=lambda ip: -ips[m.lower()][ip])[:3]
                        if cand:
                            th = threading.Thread(target=lambda pr=person, c=cand, mm=m.lower(): probes.__setitem__(pr, probes.get(pr) or arp_probe(c, mm)))
                            th.start(); probes.setdefault('_threads', []).append(th)
            for th in probes.pop('_threads', []):
                th.join(15)
            if seen:
                for person, macs in ph.items():
                    last = max((seen.get(m.lower(), 0) for m in macs), default=0)
                    p = presence.setdefault(person, {'home': None, 'sent': 0, 'probe_ok': 0, 'fails': 0})
                    if person in probes:
                        if probes[person]:
                            p['probe_ok'], p['fails'] = time.time(), 0
                        else:
                            p['fails'] = p.get('fails', 0) + 1
                    last = max(last, p.get('probe_ok', 0))           # an answered probe counts as "seen now"
                    silent = time.time() - last
                    night = C.NIGHT[0] <= datetime.datetime.now(C.LOCAL_TZ).hour < C.NIGHT[1]   # this CT runs on UTC
                    home = silent < (C.NIGHT_LIMIT if night and p['home'] is not False else C.AWAY_AFTER.get(person, C.DEFAULT_AWAY_AFTER))
                    burst = time.time() < cam_burst['until']
                    # quiet and twice unreachable: left the Wi-Fi. Only for a phone that has answered a wake-up probe in the
                    # last probe_trust_s: some phones never answer while asleep, so a failed probe says nothing about them
                    # and they fall back to away_after_s (one flapped away/home all afternoon while its owner was home).
                    trusted = time.time() - p.get('probe_ok', 0) < C.PROBE_TRUST_S
                    if not night and trusted and silent > (C.CAM_LEAVE_SILENT if burst else C.PROBE_AFTER) and p.get('fails', 0) >= 2:
                        home = False
                    # camera leave rule ([presence] cam_leave_people): the phone was active around a front-camera event
                    # (from 3 min before to 2 min after), has been silent cam_leave_after_s since, and wake-ups get no answer:
                    # they walked out the door. Without it someone can leave in the morning and show home for half an hour.
                    ev = cam_burst['at']
                    if (person in C.CAM_LEAVE_PEOPLE and p['home'] and not night and ev and time.time() - ev < 3600
                            and ev - 180 <= last <= ev + 120 and silent >= C.CAM_LEAVE_AFTER and p.get('fails', 0) >= 2
                            and p.get('cam_left') != last):
                        p['cam_left'] = last
                        print(f"presence: {person} left with camera event {cam_burst['stem']} (silent {int(silent)} s since)", flush=True)
                    if p.get('cam_left') is not None:
                        if last > p['cam_left']:
                            p.pop('cam_left')                # the phone is active again: the normal rules decide
                        else:
                            home = False
                    if p['home'] is not None and home != p['home']:
                        print(f"presence: {person} {'home' if home else 'away'}"
                              f"{' (camera event ' + str(cam_burst['stem']) + ')' if burst else ''}", flush=True)
                    p['last'] = last
                    if home != p['home'] or time.time() - p['sent'] > 120:   # refresh often: HA persons follow the newest tracker
                        ha_presence(person, home)
                        p.update(home=home, sent=time.time())
            if seen:
                last_seen_map.clear(); last_seen_map.update(seen)
                note_unassigned(seen, ips, ph)
        except Exception as e:
            print('presence:', e, flush=True)
        try:
            fresh = {}
            for person, macs in phones().items():
                for m in macs:
                    for ip_, t in ips.get(m.lower(), {}).items():
                        if t >= fresh.get(ip_, (0, ''))[0]:
                            fresh[ip_] = (t, person)
            ip_person.clear(); ip_person.update({k: v[1] for k, v in fresh.items()})
        except Exception:
            pass
        presence_wake.wait(15 if time.time() < cam_burst['until'] else 30)
        presence_wake.clear()


def note_unassigned(seen, ips, ph):
    """During a camera burst: a phone-like device (private Wi-Fi address) that is not in PHONES, was quiet for an
    hour before the event and is active now -> someone arrived with a phone we don't know (new address / new phone)."""
    if time.time() > cam_burst['until']:
        return
    known = {m.lower() for macs in ph.values() for m in macs}
    for m, t in seen.items():
        private = len(m) == 17 and m[1] in '26ae'
        if not private or m in known or t < cam_burst['at'] - 30:
            continue
        if cam_burst['at'] - cam_burst['before'].get(m, 0) < 3600:
            continue                                  # it was already active before the camera event
        if any(u['mac'] == m and u['stem'] == cam_burst['stem'] for u in unassigned_arrivals):
            continue
        ip = max(ips.get(m, {}), key=lambda i: ips[m][i], default='')
        unassigned_arrivals.append({'mac': m, 'ip': ip, 'at': t, 'stem': cam_burst['stem']})
        del unassigned_arrivals[:-20]
        print(f'presence: unassigned phone {m} ({ip}) came back with camera event {cam_burst["stem"]}', flush=True)


def camera_trigger_loop():
    """Watch camwatch for a new event (its snapshot is written when the event starts) and start a scan burst."""
    last = None
    while True:
        try:
            with urllib.request.urlopen(f'{C.CAMFEED}/latest', timeout=4) as r:
                ev = json.load(r)
            stem = ev.get('stem')
            key = f"{ev.get('day', '')}/{stem}" if stem else ''   # day/stem sorts in time order
            if last is None:
                last = key                           # the event already there at startup does not count
            elif key > last:                         # only newer events (a deleted clip must not re-trigger)
                last = key
                cam_burst.update(until=time.time() + C.CAM_BURST_S, stem=stem, at=time.time(), before=dict(last_seen_map))
                print(f'presence: camera event {stem}: scanning the family phones for {C.CAM_BURST_S // 60} min', flush=True)
                presence_wake.set()
        except Exception:
            pass
        time.sleep(3)


def presence_summary():
    """GET /api/presence"""
    return {person: {'home': presence.get(person, {}).get('home'), 'devices': [m.lower() for m in macs],
                     'silent_s': round(time.time() - presence[person]['last']) if presence.get(person, {}).get('last') else None}
            for person, macs in phones().items()}


def presence_metrics():
    out = ['# HELP home_presence 1 = the person\'s phone is on the home Wi-Fi (Pi-hole DNS activity)', '# TYPE home_presence gauge']
    for person, p in presence.items():
        if p.get('home') is not None:
            out.append(f'home_presence{{person="{person}"}} {int(p["home"])}')
    out += ['# HELP home_presence_silent_seconds seconds since the phone\'s last DNS query', '# TYPE home_presence_silent_seconds gauge']
    out += [f'home_presence_silent_seconds{{person="{person}"}} {time.time() - p["last"]:.0f}' for person, p in presence.items() if p.get('last')]
    out += ['# HELP home_person_device phone (MAC, = pihole device label) that belongs to a person', '# TYPE home_person_device gauge']
    out += [f'home_person_device{{person="{person}",device="{m.lower()}"}} 1' for person, macs in phones().items() for m in macs]
    return ('\n'.join(out) + '\n').encode()
