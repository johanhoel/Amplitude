"""Smoke test: every page at phone and desktop size, no JavaScript errors. Screenshots -> tests/out/.
Run through tools/check.sh (needs tools/staging.sh running), or BASE=http://192.168.1.52 for the live server (read-only)."""
import os, sys
from playwright.sync_api import sync_playwright
BASE = os.environ.get('BASE', 'http://localhost:8099')
PAGES = ['/start', '/living', '/media', '/family', '/familyinfo', '/desktop', '/cameras', '/boards', '/board/demo', '/pair', '/app']
SIZES = {'phone': (390, 844), 'desktop': (1440, 900)}
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out')
os.makedirs(OUT, exist_ok=True)
bad = 0
with sync_playwright() as p:
    b = p.chromium.launch()
    for size, (w, h) in SIZES.items():
        for path in PAGES:
            pg = b.new_page(viewport={'width': w, 'height': h}); errs = []
            pg.on('pageerror', lambda e: errs.append(str(e)))
            r = pg.goto(BASE + path); pg.wait_for_timeout(2500)
            pg.screenshot(path=os.path.join(OUT, f'{size}{path.replace("/", "_")}.png'))
            ok = bool(r) and r.status < 400 and not errs
            bad += not ok
            print('OK  ' if ok else 'FAIL', size, path, r and r.status, errs[:2])
            pg.close()
    b.close()
sys.exit(1 if bad else 0)
