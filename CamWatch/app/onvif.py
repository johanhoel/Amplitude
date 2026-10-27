"""Find cameras on the LAN and read their stream addresses over ONVIF (Settings -> Cameras -> Find).

WS-Discovery multicast doesn't get out of a Docker bridge network, so scan() sends the discovery probe to every
address of the subnet one by one (unicast replies do come back through the NAT; they carry maker and model) and
checks the RTSP ports at the same time, for cameras that don't answer discovery. streams() logs in (WS-Security
UsernameToken digest) and returns every media profile with its RTSP address, the camera login filled in.
Standard library only: a few SOAP calls don't need an ONVIF package.
"""
import base64
import datetime as dt
import hashlib
import ipaddress
import os
import re
import socket
import time
import urllib.error
import uuid
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from xml.sax.saxutils import escape

RTSP_PORTS = (554, 8554)
ONVIF_PORTS = (80, 8000, 8080, 2020, 8899, 888)
MAX_HOSTS = 1024
DEVICE_NS = "http://www.onvif.org/ver10/device/wsdl"
MEDIA_NS = "http://www.onvif.org/ver10/media/wsdl"
SCHEMA_NS = "http://www.onvif.org/ver10/schema"


class OnvifError(Exception):
    pass


def check_subnet(text):
    """A private network of at most MAX_HOSTS addresses -> ip_network, else ValueError with a reason."""
    net = ipaddress.ip_network(text.strip(), strict=False)
    if net.version != 4 or not net.is_private:
        raise ValueError("only private IPv4 networks (192.168.x.x, 10.x.x.x, 172.16-31.x.x) are scanned")
    if net.num_addresses > MAX_HOSTS:
        raise ValueError(f"at most {MAX_HOSTS} addresses (/22) at a time")
    return net


def _open(ip, port, timeout):
    try:
        with socket.create_connection((str(ip), port), timeout=timeout):
            return True
    except OSError:
        return False


PROBE = ('<?xml version="1.0" encoding="UTF-8"?><e:Envelope xmlns:e="http://www.w3.org/2003/05/soap-envelope" '
         'xmlns:w="http://schemas.xmlsoap.org/ws/2004/08/addressing" xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery" '
         'xmlns:dn="http://www.onvif.org/ver10/network/wsdl"><e:Header><w:MessageID>uuid:{id}</w:MessageID>'
         '<w:To e:mustUnderstand="true">urn:schemas-xmlsoap-org:ws:2005:04:discovery</w:To>'
         '<w:Action e:mustUnderstand="true">http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</w:Action></e:Header>'
         '<e:Body><d:Probe><d:Types>dn:NetworkVideoTransmitter</d:Types></d:Probe></e:Body></e:Envelope>')
DISCOVERY_PORT = 3702


def discover(hosts, wait=2.5):
    """ONVIF WS-Discovery probe sent to each host: {ip: {"maker", "model", "onvif_port"}} for the cameras that answer."""
    out = {}
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("", 0))
        sock.settimeout(0.2)
        probe = PROBE.format(id=uuid.uuid4()).encode()
        for ip in hosts:
            try:
                sock.sendto(probe, (str(ip), DISCOVERY_PORT))
            except OSError:
                pass
        end = time.time() + wait
        while time.time() < end:
            try:
                data, (ip, _) = sock.recvfrom(65535)
            except (socket.timeout, OSError):
                continue
            text = data.decode(errors="replace")
            scopes = urllib.parse.unquote(" ".join(re.findall(r"<[^>]*Scopes[^>]*>([^<]*)<", text)))
            xaddr = next((u for u in " ".join(re.findall(r"<[^>]*XAddrs[^>]*>([^<]*)<", text)).split()
                          if urllib.parse.urlsplit(u).hostname == ip), None)
            scope = lambda key: next(iter(re.findall(rf"onvif://www\.onvif\.org/{key}/(\S+)", scopes)), "").replace("_", " ")
            port = urllib.parse.urlsplit(xaddr).port or 80 if xaddr else None
            out[ip] = {"maker": scope("name"), "model": scope("hardware"), "onvif_port": port}
    return out


def scan(subnet, timeout=0.5):
    """[{"ip", "rtsp_port", "onvif_port", "maker", "model"}]: devices that answer ONVIF discovery or have an RTSP port."""
    net = check_subnet(subnet)
    hosts = list(net.hosts()) or [net.network_address]
    with ThreadPoolExecutor(128) as pool:
        discovered = pool.submit(discover, hosts)
        rtsp = dict(pool.map(lambda ip: (str(ip), next((p for p in RTSP_PORTS if _open(ip, p, timeout)), None)), hosts))
        found = discovered.result()
        ips = sorted({ip for ip, port in rtsp.items() if port} | set(found), key=lambda ip: ipaddress.ip_address(ip))
        missing = [ip for ip in ips if not (found.get(ip) or {}).get("onvif_port")]
        for ip, port in zip(missing, pool.map(_find_onvif, missing)):
            found.setdefault(ip, {"maker": "", "model": ""})["onvif_port"] = port
    return [{"ip": ip, "rtsp_port": rtsp.get(ip), **found.get(ip, {})} for ip in ips]


def _find_onvif(ip):
    for port in ONVIF_PORTS:
        if not _open(ip, port, 0.5):
            continue
        try:
            _call(ip, port, f'<GetSystemDateAndTime xmlns="{DEVICE_NS}"/>', timeout=3)
            return port
        except OnvifError:
            continue
    return None


# ---------- SOAP ----------

def _security(user, password, offset):
    nonce = os.urandom(16)
    created = (dt.datetime.now(dt.timezone.utc) + offset).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    digest = base64.b64encode(hashlib.sha1(nonce + created.encode() + password.encode()).digest()).decode()
    return (
        '<Security s:mustUnderstand="1" xmlns="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd">'
        f"<UsernameToken><Username>{escape(user)}</Username>"
        '<Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest">'
        f"{digest}</Password>"
        '<Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary">'
        f"{base64.b64encode(nonce).decode()}</Nonce>"
        f'<Created xmlns="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">{created}</Created>'
        "</UsernameToken></Security>")


def _call(ip, port, body, auth=None, url=None, timeout=6):
    header = _security(*auth) if auth else ""
    envelope = (f'<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"><s:Header>{header}</s:Header>'
                f"<s:Body>{body}</s:Body></s:Envelope>").encode()
    req = urllib.request.Request(url or f"http://{ip}:{port}/onvif/device_service", data=envelope, method="POST",
                                 headers={"Content-Type": "application/soap+xml; charset=utf-8"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
    except urllib.error.HTTPError as exc:
        data = exc.read()
        if b"NotAuthorized" in data or exc.code in (400, 401):
            raise OnvifError("the camera refused the user name or password") from None
        raise OnvifError(f"the camera answered HTTP {exc.code}") from None
    except (OSError, ValueError) as exc:
        raise OnvifError(f"no ONVIF answer from {ip}:{port} ({exc})") from None
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        raise OnvifError("the camera's answer is not ONVIF") from None
    if _find(root, "Fault") is not None:
        text = " ".join(t for t in (e.text for e in root.iter()) if t and t.strip())
        raise OnvifError("the camera refused the user name or password" if "NotAuthorized" in text
                         else f"ONVIF error: {text[:120]}")
    return root


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _find(elem, name):
    return next((e for e in elem.iter() if _local(e.tag) == name), None)


def _findall(elem, name):
    return [e for e in elem.iter() if _local(e.tag) == name]


def _text(elem, name):
    e = _find(elem, name) if elem is not None else None
    return (e.text or "").strip() if e is not None and e.text else ""


def _camera_clock_offset(ip, port):
    """WS-Security digests carry a timestamp; cameras with a wrong clock refuse ours unless we use theirs."""
    try:
        utc = _find(_call(ip, port, f'<GetSystemDateAndTime xmlns="{DEVICE_NS}"/>', timeout=4), "UTCDateTime")
        d, t = _find(utc, "Date"), _find(utc, "Time")
        cam = dt.datetime(int(_text(d, "Year")), int(_text(d, "Month")), int(_text(d, "Day")),
                          int(_text(t, "Hour")), int(_text(t, "Minute")), int(_text(t, "Second")), tzinfo=dt.timezone.utc)
        return cam - dt.datetime.now(dt.timezone.utc)
    except (OnvifError, TypeError, ValueError, AttributeError):
        return dt.timedelta(0)


def with_login(uri, user, password):
    """rtsp://host/path -> rtsp://user:password@host/path (special characters URL-encoded)."""
    parts = urllib.parse.urlsplit(uri)
    host = parts.netloc.rpartition("@")[2]
    login = urllib.parse.quote(user, safe="") + (":" + urllib.parse.quote(password, safe="") if password else "")
    return urllib.parse.urlunsplit(parts._replace(netloc=f"{login}@{host}" if user else host))


def streams(ip, port, user, password):
    """{"device": "maker model", "streams": [{"name", "width", "height", "encoding", "url"}]}, largest first."""
    ipaddress.ip_address(ip)
    auth = (user, password, _camera_clock_offset(ip, port))
    info = _call(ip, port, f'<GetDeviceInformation xmlns="{DEVICE_NS}"/>', auth)
    device = " ".join(filter(None, [_text(info, "Manufacturer"), _text(info, "Model")]))
    caps = _call(ip, port, f'<GetCapabilities xmlns="{DEVICE_NS}"><Category>Media</Category></GetCapabilities>', auth)
    media_url = _text(_find(caps, "Media"), "XAddr") or f"http://{ip}:{port}/onvif/device_service"
    # cameras behind NAT/port forwards report their own idea of the address: keep the path, use the address we reach
    media_url = re.sub(r"^https?://[^/]+", f"http://{ip}:{port}", media_url)
    profiles = _findall(_call(ip, port, f'<GetProfiles xmlns="{MEDIA_NS}"/>', auth, media_url), "Profiles")
    out = []
    for p in profiles:
        token = p.get("token")
        if not token:
            continue
        body = (f'<GetStreamUri xmlns="{MEDIA_NS}"><StreamSetup><Stream xmlns="{SCHEMA_NS}">RTP-Unicast</Stream>'
                f'<Transport xmlns="{SCHEMA_NS}"><Protocol>RTSP</Protocol></Transport></StreamSetup>'
                f"<ProfileToken>{escape(token)}</ProfileToken></GetStreamUri>")
        uri = _text(_call(ip, port, body, auth, media_url), "Uri")
        if not uri.lower().startswith("rtsp"):
            continue
        enc = _find(p, "VideoEncoderConfiguration")
        res = _find(enc, "Resolution") if enc is not None else None
        out.append({"name": _text(p, "Name") or token, "encoding": _text(enc, "Encoding"),
                    "width": int(_text(res, "Width") or 0), "height": int(_text(res, "Height") or 0),
                    "url": with_login(uri, user, password)})
    if not out:
        raise OnvifError("the camera reported no RTSP streams")
    out.sort(key=lambda s: -s["width"] * s["height"])
    return {"device": device, "streams": out}
