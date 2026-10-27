"""Screenshots of the DanteStreamer (Virgil) control panel for the README.

The panel must answer on http://localhost:8480/. From another computer, open
an SSH tunnel first; the local port must be 8480 because Virgil checks it:
    ssh -L 8480:127.0.0.1:8480 <user>@<host>
Needs Playwright for Python and Google Chrome.
Usage: python tools/screenshots.py docs/screenshots
"""
import os
import sys

from playwright.sync_api import sync_playwright

URL = "http://localhost:8480/"
OUT = sys.argv[1]
os.makedirs(OUT, exist_ok=True)


def section(page, title):
    """The <section> (or .card row) whose heading is exactly `title`."""
    return page.locator("section", has=page.locator(f"h2:text-is('{title}'), h3:text-is('{title}')")).first


with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome")
    errors = []

    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(URL)
    page.wait_for_timeout(3000)  # status and meters poll

    # 1. Status: header plus the Clock / Format / Network / Apps cards
    cards_bottom = page.evaluate(
        "Math.max(...[...document.querySelectorAll('.card')].map(c => c.getBoundingClientRect().bottom))")
    page.screenshot(path=f"{OUT}/status.jpg", type="jpeg", quality=85,
                    clip={"x": 0, "y": 0, "width": 1280, "height": cards_bottom + 16})

    # 2. Meters: both meter sections together
    cap = section(page, "Network → capture").bounding_box()
    play = section(page, "Playback → network").bounding_box()
    page.screenshot(path=f"{OUT}/meters.jpg", type="jpeg", quality=85, full_page=True,
                    clip={"x": cap["x"] - 16, "y": cap["y"] - 16, "width": cap["width"] + 32,
                          "height": play["y"] + play["height"] - cap["y"] + 32})

    # The sticky header would cover sections that need scrolling into view
    page.add_style_tag(content="header { position: static !important; }")

    # 3. Diagnostics, 4. Routing
    page.locator("#diagnostics").screenshot(path=f"{OUT}/diagnostics.jpg", type="jpeg", quality=85)
    section(page, "Routing").screenshot(path=f"{OUT}/routing.jpg", type="jpeg", quality=85)

    # 5. Settings, with the channel names opened
    page.evaluate("[...document.querySelectorAll('details')].find(d => "
                  "d.querySelector('summary').textContent.trim() === 'Channel names').open = true")
    page.wait_for_timeout(300)
    page.locator("#settings").screenshot(path=f"{OUT}/settings.jpg", type="jpeg", quality=85)
    page.close()

    # 6. Phone: the top of the panel at phone size
    phone = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True)
    phone.on("pageerror", lambda e: errors.append(str(e)))
    phone.goto(URL)
    phone.wait_for_timeout(3000)
    phone.screenshot(path=f"{OUT}/phone-panel.jpg", type="jpeg", quality=85)

    browser.close()
    print("page errors:", errors or "none")
    for f in sorted(os.listdir(OUT)):
        print(f, os.path.getsize(os.path.join(OUT, f)) // 1024, "KB")
