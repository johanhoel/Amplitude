"""camwatch logo: an eye whose iris is a camera aperture, plus the red recording dot.

Writes app/static/logo.svg (app icon tile), logo-mark.svg (no tile, for headers), logo-wordmark.svg (README),
and SVGs for the PNG icons into <temp>/camwatch-icon-render. Render each PNG with Edge (Windows), e.g.
  msedge --headless=new --disable-gpu --hide-scrollbars --default-background-color=00000000 --window-size=192,192
         --screenshot=<repo>/app/static/icon-192.png file:///<temp>/camwatch-icon-render/icon-192.png.svg
for icon-192.png (192), icon-512.png (512), icon-maskable-512.png (512) and apple-touch-icon.png (180).
"""
import math
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "app" / "static"
C = 256  # centre of the 512 canvas (x)
CY = 272  # eye centre (y): a little low, leaves room for the recording dot


def aperture(cx, cy, r_in, r_out, blades=6, twist=38):
    """Aperture blades: each blade edge runs from the pupil polygon to the iris edge, twisted like a real iris."""
    lines = []
    for i in range(blades):
        a = math.radians(i * 360 / blades - 90)
        b = math.radians(i * 360 / blades - 90 + twist)
        x1, y1 = cx + r_in * math.cos(a), cy + r_in * math.sin(a)
        x2, y2 = cx + r_out * math.cos(b), cy + r_out * math.sin(b)
        lines.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}"/>')
    pupil = " ".join(f"{cx + r_in * math.cos(math.radians(i * 60 - 90)):.1f},{cy + r_in * math.sin(math.radians(i * 60 - 90)):.1f}"
                     for i in range(blades))
    return pupil, "".join(lines)


def mark(bg=True, size=512, pad=0):
    """The icon. bg=False: no tile (for headers on a dark page)."""
    pupil, blades = aperture(C, CY, 46, 108)
    eye = "M 40 272 C 132 124, 380 124, 472 272 C 380 420, 132 420, 40 272 Z"
    tile = ('<rect x="0" y="0" width="512" height="512" rx="116" fill="url(#bg)"/>'
            '<rect x="6" y="6" width="500" height="500" rx="110" fill="none" stroke="#ffffff" stroke-opacity=".06" stroke-width="2"/>'
            if bg else "")
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="{'0 0 512 512' if bg else '20 52 480 384'}" width="{size}" height="{size if bg else round(size * 384 / 480)}" role="img" aria-label="camwatch">
<defs>
  <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#1b2631"/><stop offset="1" stop-color="#0b1015"/></linearGradient>
  <linearGradient id="lid" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#7dd3fc"/><stop offset="1" stop-color="#0ea5e9"/></linearGradient>
  <radialGradient id="iris" cx=".42" cy=".38" r=".75"><stop offset="0" stop-color="#7dd3fc"/><stop offset=".55" stop-color="#0ea5e9"/><stop offset="1" stop-color="#075985"/></radialGradient>
  <radialGradient id="rec" cx=".35" cy=".35" r=".7"><stop offset="0" stop-color="#fca5a5"/><stop offset=".45" stop-color="#ef4444"/><stop offset="1" stop-color="#b91c1c"/></radialGradient>
  <filter id="glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="9"/></filter>
  <clipPath id="eyeclip"><path d="{eye}"/></clipPath>
</defs>
{tile}
<g clip-path="url(#eyeclip)">
  <rect x="0" y="0" width="512" height="512" fill="#06121b"/>
  <circle cx="{C}" cy="{CY}" r="122" fill="#38bdf8" opacity=".22" filter="url(#glow)"/>
  <circle cx="{C}" cy="{CY}" r="108" fill="url(#iris)"/>
  <circle cx="{C}" cy="{CY}" r="108" fill="none" stroke="#0c4a6e" stroke-width="7"/>
  <g stroke="#0c4a6e" stroke-width="8" stroke-linecap="round" opacity=".85">{blades}</g>
  <polygon points="{pupil}" fill="#05090d" stroke="#0c4a6e" stroke-width="5" stroke-linejoin="round"/>
  <ellipse cx="220" cy="230" rx="24" ry="15" fill="#ffffff" opacity=".9" transform="rotate(-28 220 230)"/>
  <circle cx="290" cy="312" r="7" fill="#ffffff" opacity=".55"/>
</g>
<path d="{eye}" fill="none" stroke="url(#lid)" stroke-width="26" stroke-linejoin="round"/>
<circle cx="410" cy="96" r="44" fill="#ef4444" opacity=".35" filter="url(#glow)"/>
<circle cx="410" cy="96" r="30" fill="url(#rec)"/>
</svg>
'''


def wordmark():
    """Icon + name, for the README and wide places."""
    icon = mark(size=120).split("\n", 1)[1].rsplit("</svg>", 1)[0]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1500 512" width="750" height="256" role="img" aria-label="camwatch">
<svg x="0" y="0" width="512" height="512" viewBox="0 0 512 512">{icon}</svg>
<text x="572" y="318" font-family="Inter, 'Segoe UI', 'Helvetica Neue', Arial, sans-serif" font-size="196" font-weight="800" letter-spacing="-6"
  fill="#eef2f6">cam<tspan fill="#38bdf8">watch</tspan></text>
</svg>
'''


OUT.mkdir(parents=True, exist_ok=True)
(OUT / "logo.svg").write_text(mark(), encoding="utf-8")
(OUT / "logo-mark.svg").write_text(mark(bg=False), encoding="utf-8")
(OUT / "logo-wordmark.svg").write_text(wordmark(), encoding="utf-8")
print("written:", [p.name for p in OUT.glob("logo*.svg")])


def full_bleed(size):
    """Square tile without rounded corners, eye inside the 80% safe zone (Android maskable, iOS home screen)."""
    inner = mark(bg=False, size=round(size * 0.78))
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" width="{size}" height="{size}">
<defs><linearGradient id="fb" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#1b2631"/><stop offset="1" stop-color="#0b1015"/></linearGradient></defs>
<rect width="{size}" height="{size}" fill="url(#fb)"/>
<g transform="translate({size * 0.11:.1f} {size * 0.19:.1f})">{inner}</g>
</svg>
'''


RENDER = Path(__import__("tempfile").gettempdir()) / "camwatch-icon-render"
RENDER.mkdir(exist_ok=True)
for name, svg, size in [("icon-192.png", mark(size=192), 192), ("icon-512.png", mark(size=512), 512),
                        ("icon-maskable-512.png", full_bleed(512), 512), ("apple-touch-icon.png", full_bleed(180), 180)]:
    (RENDER / (name + ".svg")).write_text(svg, encoding="utf-8")
print("render svgs ready")
