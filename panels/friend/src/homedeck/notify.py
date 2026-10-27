"""Home notices to ntfy (topic in secrets.json 'ntfy_topic', made by the installer; server: [notify] in homedeck.toml)."""
import urllib.request

from .config import C
from .store import secret


def ntfy(title, msg, tags='door', priority='4'):
    topic = secret('ntfy_topic')
    if not topic:
        return
    req = urllib.request.Request(f'{C.NTFY}/{topic}', data=msg.encode(), method='POST',
                                 headers={'Title': title.encode('utf-8').decode('latin-1', 'replace'), 'Tags': tags, 'Priority': priority})
    try:
        urllib.request.urlopen(req, timeout=8).read()
        print('ntfy:', title, flush=True)
    except Exception as e:
        print('ntfy failed:', e, flush=True)
