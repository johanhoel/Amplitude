"""SVT headlines for the Start page. Feeds: [news] in homedeck.toml (only https://www.svt.se/ article links pass)."""
import email.utils, re, threading, time, urllib.request
import xml.etree.ElementTree as ET

from .config import C

_news = {}
_news_lock = threading.Lock()


def news(feed):
    with _news_lock:
        c = _news.get(feed)
        if c and time.time() - c['at'] < 300:
            return c['data']
        try:
            req = urllib.request.Request(C.NEWS_FEEDS[feed], headers={'User-Agent': 'home-deck'})
            with urllib.request.urlopen(req, timeout=8) as r:
                root = ET.fromstring(r.read(2 * 1024 * 1024))
            items = []
            for it in root.iter('item'):
                link = (it.findtext('link') or '').strip()
                if not link.startswith('https://www.svt.se/'):           # only real SVT article links reach the page
                    continue
                m = re.search(r'/nyheter/(?:lokalt/)?([a-z-]+)/', link)
                try:
                    at = email.utils.parsedate_to_datetime(it.findtext('pubDate')).timestamp()
                except Exception:
                    at = None
                items.append({'title': (it.findtext('title') or '').strip(), 'link': link, 'at': at,
                              'desc': re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', it.findtext('description') or '')).strip()[:240],
                              'section': m.group(1) if m else None})
            data = {'feed': feed, 'items': items[:C.NEWS_MAX], 'fetched': time.time()}
            _news[feed] = {'at': time.time(), 'data': data}
        except Exception as e:
            if not c:
                raise
            data = {**c['data'], 'stale': str(e)[:100]}
            _news[feed] = {'at': time.time() - 240, 'data': data}           # retry in a minute
        return data
