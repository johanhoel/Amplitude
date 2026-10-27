"""Find what is on the home network, for the first-run setup.

Nothing here changes anything on the network: it only asks.
  - TCP connect to a short list of well-known ports on every address of the local /24 (Home Assistant, Pi-hole,
    Proxmox, Prometheus, cameras, Sonos, Google Cast, AirPlay, the lab panel, the camera feed, the PC listener)
  - mDNS (Bonjour) browse for the usual service types, SSDP (UPnP) search, WS-Discovery probe (ONVIF cameras)
  - the kernel's neighbour table for MAC addresses, the IEEE list for the maker, reverse DNS for names
Then each open port is asked one harmless question (a GET of a status page) to tell what it really is.
scan(progress) -> {'subnet', 'took_s', 'devices': [...], 'found': {role: [...]}}
"""
import concurrent.futures as cf, http.client, ipaddress, json, re, socket, ssl, subprocess, time, uuid
import xml.etree.ElementTree as ET

PORTS = (53, 80, 443, 554, 1400, 3000, 5000, 7000, 8006, 8007, 8008, 8080, 8091, 8123, 8765, 8790, 8971, 9090, 10443)
MDNS_TYPES = ('_home-assistant._tcp.local.', '_googlecast._tcp.local.', '_sonos._tcp.local.', '_airplay._tcp.local.',
              '_raop._tcp.local.', '_spotify-connect._tcp.local.', '_netaudio-arc._udp.local.', '_hap._tcp.local.',
              '_rtsp._tcp.local.', '_ipp._tcp.local.', '_smb._tcp.local.', '_ssh._tcp.local.', '_workstation._tcp.local.',
              '_companion-link._tcp.local.', '_apple-mobdev2._tcp.local.')
PHONE_MAKERS = re.compile(r'apple|samsung|google|oneplus|xiaomi|huawei|motorola|sony mobile|oppo|vivo|nothing tech|fairphone', re.I)
PHONE_NAMES = re.compile(r'iphone|android|galaxy|pixel|phone|fold|oneplus|redmi', re.I)
_NOVERIFY = ssl._create_unverified_context()          # home devices use self-signed certificates; we only read status pages


def local_subnet():
    """-> (own ip, the /24 to scan). A bigger network is narrowed to the /24 around this machine."""
    out = subprocess.run(['ip', '-4', '-o', 'addr'], capture_output=True, text=True).stdout
    for line in out.splitlines():
        dev, cidr = line.split()[1], line.split()[3]
        if dev == 'lo' or dev.startswith(('docker', 'br-', 'veth', 'virbr', 'tailscale', 'wg', 'tun')):
            continue
        iface = ipaddress.ip_interface(cidr)
        if iface.ip.is_private:
            net = iface.network if iface.network.prefixlen >= 24 else ipaddress.ip_network(f'{iface.ip}/24', strict=False)
            return str(iface.ip), net
    raise RuntimeError('no private IPv4 address on this machine')


def _open(ip, port, timeout=0.4):
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except OSError:
        return False


def _http(ip, port, path, tls=None, timeout=2.5, method='GET'):
    """-> (status, headers, body text up to 64 kB) or None. tls=None tries plain then TLS."""
    for use_tls in ((False, True) if tls is None else (tls,)):
        try:
            c = (http.client.HTTPSConnection(ip, port, timeout=timeout, context=_NOVERIFY) if use_tls
                 else http.client.HTTPConnection(ip, port, timeout=timeout))
            c.request(method, path, headers={'User-Agent': 'HomeDeck-setup'})
            r = c.getresponse()
            body = r.read(65536).decode('utf-8', 'replace')
            c.close()
            return r.status, {k.lower(): v for k, v in r.getheaders()}, body, use_tls
        except (OSError, http.client.HTTPException, ssl.SSLError):
            continue
    return None


def _title(body):
    m = re.search(r'<title[^>]*>([^<]{1,80})', body or '', re.I)
    return m.group(1).strip() if m else ''


def identify(ip, port):
    """One harmless question per open port -> (role, label, extra) or None (role None = a plain web page)."""
    if port == 8123:
        r = _http(ip, 8123, '/manifest.json')
        if r and 'home assistant' in r[2].lower():
            return 'homeassistant', 'Home Assistant', {'url': f"{'https' if r[3] else 'http'}://{ip}:8123"}
    if port == 80:
        r = _http(ip, 80, '/admin/', tls=False)
        if r and 'pi-hole' in r[2].lower():
            return 'pihole', 'Pi-hole', {}
        r = r or _http(ip, 80, '/', tls=False)
        return (None, _title(r[2]) or 'web page', {}) if r else None
    if port in (8006, 8007):
        r = _http(ip, port, '/', tls=True)
        if r and 'proxmox' in r[2].lower():
            return ('proxmox' if port == 8006 else 'pbs'), ('Proxmox VE' if port == 8006 else 'Proxmox Backup Server'), {}
    if port == 9090:
        r = _http(ip, 9090, '/-/healthy', tls=False)
        if r and r[0] == 200 and 'prometheus' in r[2].lower():
            return 'prometheus', 'Prometheus', {'url': f'http://{ip}:9090'}
    if port == 3000:
        r = _http(ip, 3000, '/api/health', tls=False)
        if r and '"database"' in r[2]:
            return 'grafana', 'Grafana', {}
    if port == 8790:
        r = _http(ip, 8790, '/health', tls=False)
        if r and r[0] == 200:
            return 'labpanel', 'Lab panel', {'url': f'http://{ip}:8790'}
    if port == 8091:
        r = _http(ip, 8091, '/days', tls=False)
        if r and r[0] == 200 and r[2].lstrip()[:1] in '[{':
            return 'camfeed', 'Camera feed', {'url': f'http://{ip}:8091'}
    if port == 8765:
        return 'pc', 'PC listener (deck-listener)', {'hostport': f'{ip}:8765'}
    if port == 1400:
        r = _http(ip, 1400, '/xml/device_description.xml', tls=False)
        if r and 'sonos' in r[2].lower():
            room = re.search(r'<roomName>([^<]+)', r[2])
            return 'sonos', 'Sonos' + (f' · {room.group(1)}' if room else ''), {}
    if port == 8008:
        r = _http(ip, 8008, '/setup/eureka_info?params=name', tls=False)
        if r and r[0] == 200:
            try:
                return 'cast', 'Google Cast · ' + json.loads(r[2]).get('name', ''), {}
            except ValueError:
                return 'cast', 'Google Cast', {}
    if port == 554:
        return 'camera', 'Camera (RTSP)', {}
    if port == 10443:
        r = _http(ip, 10443, '/', tls=True)
        if r and 'scrypted' in r[2].lower():
            return 'nvr', 'Scrypted', {}
    if port in (5000, 8971):
        r = _http(ip, port, '/api/version', tls=port == 8971)
        if r and r[0] == 200 and re.fullmatch(r'[\d.]+[-\w]*', r[2].strip().strip('"')):
            return 'nvr', 'Frigate', {}
    if port == 7000:
        return 'airplay', 'AirPlay', {}
    return None


def _neighbours():
    """ip -> mac from the kernel's table (filled by the connects above)."""
    out = subprocess.run(['ip', '-4', 'neigh'], capture_output=True, text=True).stdout
    return {m.group(1): m.group(2).lower() for m in re.finditer(r'^(\S+) dev \S+ lladdr (\S+) (?!FAILED)', out, re.M)}


_OUI = None


def vendor(mac):
    """Maker from the IEEE list (Debian package ieee-data); '' when unknown. A private (random) address has none."""
    global _OUI
    if not mac or int(mac[1], 16) & 2:
        return ''
    if _OUI is None:
        _OUI = {}
        for path in ('/usr/share/ieee-data/oui.txt', '/var/lib/ieee-data/oui.txt'):
            try:
                with open(path, encoding='utf-8', errors='replace') as f:
                    for line in f:
                        m = re.match(r'([0-9A-F]{2})-([0-9A-F]{2})-([0-9A-F]{2})\s+\(hex\)\s+(.+)', line)
                        if m:
                            _OUI[':'.join(m.group(1, 2, 3)).lower()] = m.group(4).strip()
                break
            except OSError:
                continue
    return _OUI.get(mac[:8], '')


def _rdns(ip):
    try:
        return socket.gethostbyaddr(ip)[0].split('.')[0]
    except OSError:
        return ''


def mdns(seconds=4.0):
    """ip -> [{type, name, props}] via zeroconf (in the panel's venv); empty if the library is missing."""
    try:
        from zeroconf import ServiceBrowser, Zeroconf
    except ImportError:
        return {}
    hits, zc = {}, Zeroconf()

    class L:
        def add_service(self, z, t, name):
            info = z.get_service_info(t, name, timeout=1500)
            if not info:
                return
            props = {k.decode(errors='replace'): (v or b'').decode(errors='replace') for k, v in (info.properties or {}).items()}
            for ip in info.parsed_addresses():
                if ':' not in ip:
                    hits.setdefault(ip, []).append({'type': t.split('.')[0], 'name': name.split('.')[0], 'props': props})

        update_service = add_service

        def remove_service(self, *a):
            pass

    try:
        browsers = [ServiceBrowser(zc, t, L()) for t in MDNS_TYPES]
        time.sleep(seconds)
        for b in browsers:
            b.cancel()
    finally:
        zc.close()
    return hits


def ssdp(seconds=3.0):
    """ip -> {server, location} from a UPnP search."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    s.settimeout(0.5)
    msg = 'M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: "ssdp:discover"\r\nMX: 2\r\nST: ssdp:all\r\n\r\n'
    hits, end = {}, time.time() + seconds
    try:
        s.sendto(msg.encode(), ('239.255.255.250', 1900))
        while time.time() < end:
            try:
                data, (ip, _) = s.recvfrom(4096)
            except socket.timeout:
                continue
            h = dict(re.findall(r'^([A-Za-z-]+):\s*(.*?)\r?$', data.decode(errors='replace'), re.M))
            h = {k.lower(): v for k, v in h.items()}
            hits.setdefault(ip, {'server': h.get('server', ''), 'location': h.get('location', '')})
    finally:
        s.close()
    return hits


def onvif(seconds=3.0):
    """IPs that answer a WS-Discovery probe for network video devices (ONVIF cameras)."""
    probe = ('<?xml version="1.0" encoding="UTF-8"?><e:Envelope xmlns:e="http://www.w3.org/2003/05/soap-envelope" '
             'xmlns:w="http://schemas.xmlsoap.org/ws/2004/08/addressing" xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery" '
             'xmlns:dn="http://www.onvif.org/ver10/network/wsdl"><e:Header><w:MessageID>uuid:' + str(uuid.uuid4()) +
             '</w:MessageID><w:To e:mustUnderstand="true">urn:schemas-xmlsoap-org:ws:2005:04:discovery</w:To>'
             '<w:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</w:Action></e:Header><e:Body><d:Probe>'
             '<d:Types>dn:NetworkVideoTransmitter</d:Types></d:Probe></e:Body></e:Envelope>')
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(0.5)
    ips, end = set(), time.time() + seconds
    try:
        s.sendto(probe.encode(), ('239.255.255.250', 3702))
        while time.time() < end:
            try:
                data, (ip, _) = s.recvfrom(16384)
                if b'ProbeMatch' in data:
                    ips.add(ip)
            except socket.timeout:
                continue
    finally:
        s.close()
    return ips


def _upnp_name(location):
    m = re.match(r'https?://([^/:]+)(?::(\d+))?(/.*)?', location or '')
    if not m:
        return ''
    r = _http(m.group(1), int(m.group(2) or 80), m.group(3) or '/', tls=location.startswith('https'), timeout=2)
    if not r:
        return ''
    try:
        root = ET.fromstring(r[2])
    except ET.ParseError:
        return ''
    get = lambda tag: next((e.text for e in root.iter() if e.tag.endswith(tag) and e.text), '')
    return ' '.join(x for x in (get('friendlyName'), get('modelName')) if x)[:80]


def scan(progress=lambda pct, text: None):
    t0 = time.time()
    me, net = local_subnet()
    hosts = [str(h) for h in net.hosts()]
    progress(2, f'Looking around {net} ...')
    with cf.ThreadPoolExecutor(3) as side:                              # the multicast searches run while the ports are tried
        f_mdns, f_ssdp, f_onvif = side.submit(mdns), side.submit(ssdp), side.submit(onvif)
        open_ports, jobs = {}, [(h, p) for h in hosts for p in PORTS]
        with cf.ThreadPoolExecutor(160) as ex:
            futs = {ex.submit(_open, h, p): (h, p) for h, p in jobs}
            for i, f in enumerate(cf.as_completed(futs)):
                if f.result():
                    h, p = futs[f]
                    open_ports.setdefault(h, []).append(p)
                if i % 400 == 0:
                    progress(5 + int(55 * i / len(jobs)), f'Knocking on doors: {len(open_ports)} devices answered so far')
        mdns_hits, ssdp_hits, onvif_ips = f_mdns.result(), f_ssdp.result(), f_onvif.result()
    neigh = _neighbours()
    ips = sorted(set(open_ports) | set(neigh) | set(mdns_hits) | set(ssdp_hits) | onvif_ips,
                 key=lambda ip: ipaddress.ip_address(ip))
    ips = [ip for ip in ips if ipaddress.ip_address(ip) in net]
    progress(62, f'Asking {len(ips)} devices what they are ...')
    with cf.ThreadPoolExecutor(64) as ex:
        idents = {(ip, p): ex.submit(identify, ip, p) for ip in open_ports for p in open_ports[ip]}
        names = {ip: ex.submit(_rdns, ip) for ip in ips}
        upnp = {ip: ex.submit(_upnp_name, h['location']) for ip, h in ssdp_hits.items() if h.get('location')}
        idents = {k: v.result() for k, v in idents.items()}
        names = {k: v.result() for k, v in names.items()}
        upnp = {k: v.result() for k, v in upnp.items()}
    progress(90, 'Sorting what was found ...')
    devices, found = [], {}

    def add(role, item):                                           # one entry per device and role
        if not any(x['ip'] == item['ip'] and x['label'] == item['label'] for x in found.get(role, [])):
            found.setdefault(role, []).append(item)

    for ip in ips:
        mac = neigh.get(ip, '')
        d = {'ip': ip, 'mac': mac, 'maker': vendor(mac), 'private_mac': bool(mac) and bool(int(mac[1], 16) & 2),
             'name': names.get(ip, ''), 'ports': sorted(open_ports.get(ip, [])), 'what': [], 'self': ip == me}
        for p in d['ports']:
            r = idents.get((ip, p))
            if r and r[0]:
                d['what'].append(r[1])
                add(r[0], {'ip': ip, 'label': r[1], **r[2]})
        for hit in mdns_hits.get(ip, []):
            t, nm, pr = hit['type'], hit['name'], hit['props']
            if t == '_home-assistant' and not any(x['ip'] == ip for x in found.get('homeassistant', [])):
                url = pr.get('internal_url') or pr.get('base_url') or f'http://{ip}:8123'
                add('homeassistant', {'ip': ip, 'label': 'Home Assistant · ' + pr.get('location_name', nm), 'url': url})
            elif t == '_googlecast':
                lab = 'Google Cast · ' + (pr.get('fn') or nm)
                if not any(x['ip'] == ip for x in found.get('cast', [])):
                    add('cast', {'ip': ip, 'label': lab})
                d['name'] = d['name'] or pr.get('fn', '')
            elif t == '_netaudio-arc':
                add('dante', {'ip': ip, 'label': 'Dante · ' + nm, 'dante_name': nm})
                d['what'].append('Dante · ' + nm)
            elif t == '_airplay':
                model = pr.get('model', '')
                if model.lower().startswith('appletv'):
                    add('appletv', {'ip': ip, 'label': f'Apple TV · {nm}', 'model': model})
                    d['what'].append('Apple TV')
                elif not any(x['ip'] == ip for x in found.get('airplay', [])):
                    add('airplay', {'ip': ip, 'label': f'AirPlay · {nm}'})
            elif t == '_sonos' and not any(x['ip'] == ip for x in found.get('sonos', [])):
                add('sonos', {'ip': ip, 'label': 'Sonos · ' + nm.split('@')[-1]})
            elif t in ('_apple-mobdev2', '_companion-link'):
                d['phone_hint'] = True
            d['name'] = d['name'] or nm
            if t not in ('_workstation', '_ssh'):
                d['what'].append(t.strip('_').split('.')[0])
        if ip in onvif_ips and not any(x['ip'] == ip for x in found.get('camera', [])):
            add('camera', {'ip': ip, 'label': 'Camera (ONVIF)'})
            d['what'].append('Camera (ONVIF)')
        if ip in upnp and upnp[ip]:
            d['what'].append(upnp[ip])
        d['what'] = list(dict.fromkeys(d['what']))
        maybe_phone = (not d['ports'] or d['ports'] == [7000]) and (
            d.get('phone_hint') or PHONE_NAMES.search(d['name']) or (d['private_mac'] and not d['what'])
            or (PHONE_MAKERS.search(d['maker']) and not d['what']))
        if maybe_phone and mac and not d['self']:
            d['phone'] = True
            add('phone', {'ip': ip, 'mac': mac, 'label': d['name'] or d['maker'] or 'private address', 'private_mac': d['private_mac']})
        devices.append(d)
    gw = subprocess.run(['ip', '-4', 'route', 'show', 'default'], capture_output=True, text=True).stdout.split()
    if 'via' in gw:
        add('router', {'ip': gw[gw.index('via') + 1], 'label': 'Router (default gateway)'})
    progress(100, f'Done: {len(devices)} devices')
    return {'subnet': str(net), 'me': me, 'took_s': round(time.time() - t0, 1), 'devices': devices, 'found': found}


if __name__ == '__main__':                                              # python3 discover.py  -> what this network has
    r = scan(lambda p, t: print(f'{p:3d}%  {t}', flush=True))
    for role, items in sorted(r['found'].items()):
        print(f'{role:14s}', ', '.join(f"{x['ip']} {x['label']}" for x in items))
    print(f"{len(r['devices'])} devices in {r['took_s']} s")
