#!/usr/bin/env python3
"""The icon set: one definition, generated into a stylesheet for each server.

Why this exists: the panels used emoji as icons - 337 of them. An emoji is
drawn by whichever colour font the device happens to have, so the same page
showed Apple's glyphs on a phone, Segoe's on Windows, Noto's orange on Linux,
and empty boxes on a wall panel with no emoji font installed at all. That is
the single biggest reason the projects did not look like one product.

These are stroked line icons on a 24x24 grid, 1.7 units wide, round caps and
joins - the same drawing rules as CamWatch's mark, so the mark and the icons
look like one family. They are monochrome and inherit the surrounding text
colour, so a status colour applies to the icon as well as the word.

Delivered as CSS masks rather than inline SVG: the markup stays
<i class="icon icon-bulb"></i> wherever it appears, which is the same in a static
page and inside a JavaScript template string, and the icon follows font-size
and currentColor like a letter would.

Run design/sync-icons.py after changing anything here.
"""

# name -> path data on a 24x24 grid. Keep each to a few strokes: these are
# read at a glance on a wall panel, not studied.
ICONS = {
    # --- light and power ---
    "bluetooth": "M8 7.5 16 16.5 12 20V4l4 3.5L8 16.5",
    "updown":    "M7 9l3-3 3 3M10 6v12M14 15l3 3 3-3M17 18V6",
    "external":  "M14 4h6v6M20 4l-8.5 8.5M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5",
    "quote":     "M10 11H5.5A1.5 1.5 0 0 1 4 9.5v-2A1.5 1.5 0 0 1 5.5 6H8a2 2 0 0 1 2 2zm0 0c0 4-2 6-5 7M20 11h-4.5A1.5 1.5 0 0 1 14 9.5v-2A1.5 1.5 0 0 1 15.5 6H18a2 2 0 0 1 2 2zm0 0c0 4-2 6-5 7",
    "check":     "M4 12.5l5 5L20 6.5",
    "alert":     "M12 3.5 1.8 21h20.4zM12 10v5M12 18h.01",
    "bulb":      "M9 18h6M10 21h4M12 3a6 6 0 0 0-3.5 10.9c.3.2.5.6.5 1V16h6v-1.1c0-.4.2-.8.5-1A6 6 0 0 0 12 3z",
    "plug":      "M9 3v5M15 3v5M6 8h12v3a6 6 0 0 1-12 0zM12 17v4",
    "bolt":      "M13 2 4 14h7l-1 8 9-12h-7z",
    "brightness": "M12 7a5 5 0 1 0 0 10 5 5 0 0 0 0-10M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M19.1 4.9l-1.4 1.4M6.3 17.7l-1.4 1.4",
    "power":     "M12 3v9M7.8 6.3a8 8 0 1 0 8.4 0",

    # --- security ---
    "lock":      "M7 10V7a5 5 0 0 1 10 0v3M5 10h14v11H5zM12 14v3",
    "unlock":    "M7 10V7a5 5 0 0 1 9.6-2M5 10h14v11H5zM12 14v3",
    "key":       "M15 4a5 5 0 1 1-4.3 7.6L4 18.3V21h3l.8-.8v-2h2v-2h2l1.6-1.6A5 5 0 0 1 15 4zM16.5 8h.01",
    "shield":    "M12 3l8 3v6c0 5-3.4 8.7-8 10-4.6-1.3-8-5-8-10V6z",
    "door":      "M6 21V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v17M3 21h18M14.5 12.5h.01",

    # --- cameras and media ---
    "camera":    "M3 8h4l1.5-2.5h7L17 8h4v12H3zM12 17a4 4 0 1 0 0-8 4 4 0 0 0 0 8z",
    "video":     "M3 6h12v12H3zM15 10l6-3.5v11L15 14z",
    "film":      "M3 4h18v16H3zM7 4v16M17 4v16M3 9h4M3 15h4M17 9h4M17 15h4",
    "image":     "M3 4h18v16H3zM8.5 10a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3M3 16l5-4 4 3 3-2 6 5",
    "music":     "M9 18V5l11-2v13M9 18a3 3 0 1 1-6 0 3 3 0 0 1 6 0M20 16a3 3 0 1 1-6 0 3 3 0 0 1 6 0",
    "speaker":   "M4 9h4l5-4v14l-5-4H4zM16.5 9.5a4 4 0 0 1 0 5M19 7a7.5 7.5 0 0 1 0 10",
    "mute":      "M4 9h4l5-4v14l-5-4H4zM17 10l4 4M21 10l-4 4",
    "volume":    "M4 9h4l5-4v14l-5-4H4zM16.5 9.5a4 4 0 0 1 0 5",
    "mic":       "M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3zM5 11a7 7 0 0 0 14 0M12 18v3",
    "tv":        "M3 5h18v12H3zM8 21h8M12 17v4",
    "bell-off":  "M8 5.6A6 6 0 0 1 18 10v4l2 3H7M6 7a6 6 0 0 0-.3 2v5l-2 3h10M10 20a2 2 0 0 0 4 0M3 3l18 18",

    # --- devices ---
    "phone":     "M7 2h10v20H7zM10.5 19h3",
    "desktop":   "M3 4h18v12H3zM8 20h8M12 16v4",
    "laptop":    "M5 5h14v10H5zM2 18h20l-1.5-3H3.5z",
    "network":   "M9 3h6v4H9zM3 17h6v4H3zM15 17h6v4h-6zM12 7v4M6 17v-3h12v3",
    "wifi":      "M3 9a14 14 0 0 1 18 0M6.5 12.5a9 9 0 0 1 11 0M10 16a4 4 0 0 1 4 0M12 19.5h.01",
    "antenna":   "M12 11a2 2 0 1 0 0-4 2 2 0 0 0 0 4M12 11v10M7.5 4.5a7 7 0 0 0 0 10M16.5 4.5a7 7 0 0 1 0 10",
    "printer":   "M7 8V3h10v5M7 18H4V8h16v10h-3M7 14h10v7H7z",
    "window":    "M3 4h18v16H3zM3 9h18M12 9v11",
    "robot":     "M8 8h8a3 3 0 0 1 3 3v6H5v-6a3 3 0 0 1 3-3zM12 4v4M9.5 13h.01M14.5 13h.01M2 12v3M22 12v3",

    # --- weather ---
    "sun":       "M12 7a5 5 0 1 0 0 10 5 5 0 0 0 0-10M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M19.1 4.9l-1.4 1.4M6.3 17.7l-1.4 1.4",
    "cloud":     "M7 18a4 4 0 0 1 0-8 6 6 0 0 1 11.3 2A3.5 3.5 0 0 1 17.5 18z",
    "partly":    "M15 5a4 4 0 0 0-3.9 3.1M18 5.5V4M21 8h1.5M20.3 5.7l1-1M6.5 20a4 4 0 0 1 0-8 5.5 5.5 0 0 1 10.3 1.6A3.2 3.2 0 0 1 16.5 20z",
    "rain":      "M7 15a4 4 0 0 1 0-8 6 6 0 0 1 11.3 2A3.5 3.5 0 0 1 17.5 15M8 18l-1 3M12.5 18l-1 3M17 18l-1 3",
    "snow":      "M7 15a4 4 0 0 1 0-8 6 6 0 0 1 11.3 2A3.5 3.5 0 0 1 17.5 15M8 19h.01M12 21h.01M16 19h.01",
    "storm":     "M7 15a4 4 0 0 1 0-8 6 6 0 0 1 11.3 2A3.5 3.5 0 0 1 17.5 15M13 16l-3 4h4l-3 4",
    "fog":       "M7 13a4 4 0 0 1 0-8 6 6 0 0 1 11.3 2A3.5 3.5 0 0 1 17.5 13M4 17h16M6 21h12",
    "wind":      "M3 8h11a3 3 0 1 0-3-3M3 13h15a3 3 0 1 1-3 3M3 18h8",
    "moon":      "M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z",
    "sunrise":   "M12 3v5M8 6l4-3 4 3M4 15a8 8 0 0 1 16 0M2 19h20",
    "sunset":    "M12 8V3M8 5l4 3 4-3M4 15a8 8 0 0 1 16 0M2 19h20",
    "thermo":    "M14 14V5a2 2 0 1 0-4 0v9a4 4 0 1 0 4 0zM12 9v6",
    "drop":      "M12 3s6 6.6 6 10.5a6 6 0 0 1-12 0C6 9.6 12 3 12 3z",

    # --- home and places ---
    "home":      "M3 11l9-7 9 7M5.5 9.5V20h13V9.5M10 20v-6h4v6",
    "vacuum":    "M12 4a8 8 0 1 0 0 16 8 8 0 0 0 0-16M6.3 7.3a8 8 0 0 1 11.4 0M12 10.2a1.8 1.8 0 1 0 0 3.6 1.8 1.8 0 0 0 0-3.6",
    "trash":     "M4 7h16M10 4h4M6 7l1 14h10l1-14M10 11v6M14 11v6",
    "box":       "M3 7l9-4 9 4v10l-9 4-9-4zM3 7l9 4 9-4M12 11v10",
    "folder":    "M3 6h6l2 3h10v11H3z",
    "tag":       "M3 3h8l10 10-8 8L3 11zM7.5 7.5h.01",
    "map":       "M3 6l6-3 6 3 6-3v15l-6 3-6-3-6 3zM9 3v15M15 6v15",

    # --- people ---
    "person":    "M12 4a4 4 0 1 0 0 8 4 4 0 0 0 0-8M4 21a8 8 0 0 1 16 0",
    "people":    "M9 4a4 4 0 1 0 0 8 4 4 0 0 0 0-8M2 21a7 7 0 0 1 14 0M17 5a3.5 3.5 0 0 1 0 7M18 14.5a6 6 0 0 1 4 6.5",
    "sleep":     "M13 4h6l-6 7h6M4 14h5l-5 6h5",

    # --- data and tools ---
    "chart":     "M4 20V10M10 20V4M16 20v-7M22 20H2",
    "list":      "M8 6h13M8 12h13M8 18h13M3.5 6h.01M3.5 12h.01M3.5 18h.01",
    "note":      "M5 3h9l5 5v13H5zM14 3v5h5M9 13h6M9 17h4",
    "news":      "M3 5h14v15H3zM17 9h4v9a2 2 0 0 1-4 0zM6 9h8M6 13h8M6 17h5",
    "book":      "M4 4h7a2 2 0 0 1 2 2v14a2 2 0 0 0-2-2H4zM20 4h-7a2 2 0 0 0-2 2v14a2 2 0 0 1 2-2h7z",
    "search":    "M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14M16 16l5 5",
    "link":      "M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 1 0-5.7-5.7l-1.5 1.5M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 1 0 5.7 5.7l1.5-1.5",
    "puzzle":    "M4 9.5V5a1 1 0 0 1 1-1h4.2a2.2 2.2 0 0 1 4.4 0H18a1 1 0 0 1 1 1v4.2a2.2 2.2 0 0 1 0 4.4V19a1 1 0 0 1-1 1h-4.2a2.2 2.2 0 0 0-4.4 0H5a1 1 0 0 1-1-1v-4.2a2.2 2.2 0 0 0 0-4.4z",
    "flask":     "M9 3h6M10 3v6l-5.5 9A2 2 0 0 0 6.2 21h11.6a2 2 0 0 0 1.7-3L14 9V3M7.5 15h9",
    "wand":      "M4 20L16 8M18 3v4M16 5h4M18.5 13v3M17 14.5h3M6 3v3M4.5 4.5h3",
    "gamepad":   "M7 8h10a5 5 0 0 1 0 10H7a5 5 0 0 1 0-10M9 11v4M7 13h4M15.5 12h.01M17.5 14.5h.01",
    "clock":     "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18M12 7v5l3.5 2",
    "globe":     "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18M3 12h18M12 3a14 14 0 0 1 0 18 14 14 0 0 1 0-18",
    "type":      "M4 7V5h16v2M12 5v14M9 19h6",
    "fire":      "M12 21a6 6 0 0 0 6-6c0-4.2-3-6.7-6-12-3 5.3-6 7.8-6 12a6 6 0 0 0 6 6zM12 21a2.8 2.8 0 0 0 2.8-2.8c0-1.9-1.4-3-2.8-5.6-1.4 2.6-2.8 3.7-2.8 5.6A2.8 2.8 0 0 0 12 21z",
    "question":  "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18M9.5 9.5a2.5 2.5 0 1 1 3.3 2.4c-.5.2-.8.6-.8 1.1v.5M12 17h.01",
    "package":   "M3 7l9-4 9 4v10l-9 4-9-4zM3 7l9 4 9-4M12 11v10M7.5 5l9 4",

    # --- transport ---
    "bus":       "M6 3h12a2 2 0 0 1 2 2v10H4V5a2 2 0 0 1 2-2zM4 9h16M12 3v6M7 19.5a1.6 1.6 0 1 0 0-3.2 1.6 1.6 0 0 0 0 3.2M17 19.5a1.6 1.6 0 1 0 0-3.2 1.6 1.6 0 0 0 0 3.2",
    "car":       "M4.5 11.5 6.2 7A2 2 0 0 1 8.1 5.7h7.8A2 2 0 0 1 17.8 7l1.7 4.5M3 11.5h18V17H3zM6.8 20a1.6 1.6 0 1 0 0-3.2 1.6 1.6 0 0 0 0 3.2M17.2 20a1.6 1.6 0 1 0 0-3.2 1.6 1.6 0 0 0 0 3.2",

    # --- status marks (filled, so they read as a dot not an outline) ---
    "dot":       "M12 6a6 6 0 1 0 0 12 6 6 0 0 0 0-12",
    "star":      "M12 3l2.6 5.8 6.4.7-4.8 4.3 1.4 6.2L12 17l-5.6 3 1.4-6.2L3 9.5l6.4-.7z",
    "square":    "M4 4h16v16H4z",
    "toggle":    "M8 7h8a5 5 0 0 1 0 10H8A5 5 0 0 1 8 7M8 9.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5",
    "refresh":   "M20 7a9 9 0 1 0 1 7M20 3v5h-5",
    "download":  "M12 3v12M7.5 10.5 12 15l4.5-4.5M4 20h16",
    "upload":    "M12 21V9M7.5 13.5 12 9l4.5 4.5M4 4h16",
    "check-box": "M4 4h16v16H4zM8 12l3 3 5-6",
    # --- transport controls. These look like plain glyphs but U+23F8/23EE/23ED
    # carry the Emoji property, and iOS draws them in colour - and these pages
    # run on iPads. Drawn here instead so every platform agrees. ---
    "play":      "M8 5l11 7-11 7z",
    "pause":     "M9 5h3v14H9zM15 5h3v14h-3z",
    "prev":      "M18 5v14L8 12zM6 5h2v14H6z",
    "next":      "M6 5l10 7L6 19zM16 5h2v14h-2z",
    "left":      "M15 5l-7 7 7 7",
    "right":     "M9 5l7 7-7 7",
    "up":        "M5 15l7-7 7 7",
    "down":      "M5 9l7 7 7-7",

    # --- nav and misc icon slots that were dingbats ---
    "gear":      "M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6M19.4 14a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-2.7 1.1v.3a2 2 0 1 1-4 0v-.2a1.6 1.6 0 0 0-2.8-1.1l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1A1.6 1.6 0 0 0 3.5 13H3a2 2 0 1 1 0-4h.2A1.6 1.6 0 0 0 4.3 6.2l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1A1.6 1.6 0 0 0 10 2.3V2a2 2 0 1 1 4 0v.2a1.6 1.6 0 0 0 2.7 1.1l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0 1.1 2.7h.3a2 2 0 1 1 0 4h-.2a1.6 1.6 0 0 0-1.3 1.1z",
    "grid":      "M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z",
    "server":    "M4 4h16v6H4zM4 14h16v6H4zM7.5 7h.01M7.5 17h.01M11 7h5M11 17h5",
    "bell":      "M6 9a6 6 0 0 1 12 0v4l2 3H4l2-3zM10 20a2 2 0 0 0 4 0",
    "deck":      "M3 4h7v7H3zM14 4h7v4h-7zM14 11h7v9h-7zM3 14h7v6H3z",
    "database":  "M12 3c4.4 0 8 1.3 8 3s-3.6 3-8 3-8-1.3-8-3 3.6-3 8-3M4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3",
    "hexagon":   "M12 2.5l8 4.7v9.6l-8 4.7-8-4.7V7.2zM12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6",
    "sparkle":   "M12 2l2.2 6.3L20.5 10l-6.3 2.2L12 18.5l-2.2-6.3L3.5 10l6.3-1.7zM19 16l.9 2.4 2.4.9-2.4.9L19 22.6l-.9-2.4-2.4-.9 2.4-.9z",
    "frame":     "M3 8V3h5M16 3h5v5M21 16v5h-5M8 21H3v-5",
    "target":    "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8M12 11.5a.5.5 0 1 0 0 1 .5.5 0 0 0 0-1",
}

# Icons drawn as a solid shape rather than a stroke.
FILLED = {"dot", "star", "square", "play", "pause", "prev", "next"}

# Every pictographic emoji in the repo, mapped to the icon that replaces it.
# Several emoji share an icon on purpose: 🏠 and 🏡 are the same thing on a
# wall panel, and so are 🔈 and 🔊.
EMOJI = {
    "💡": "bulb", "🔌": "plug", "⚡": "bolt", "🔆": "brightness",
    "🔒": "lock", "🔐": "lock", "🔓": "unlock", "🔑": "key", "🛡": "shield", "🚪": "door",
    "📷": "camera", "📹": "video", "📵": "video", "🎞": "film", "🖼": "image",
    "🎵": "music", "🔊": "speaker", "🔈": "volume", "🔇": "mute", "🎙": "mic",
    "📺": "tv", "🔕": "bell-off",
    "📱": "phone", "📲": "phone", "💻": "laptop", "🖥": "desktop", "🖧": "network",
    "📶": "wifi", "📡": "antenna", "🖨": "printer", "🪟": "window", "🤖": "robot",
    "📟": "phone",
    "☔": "rain", "🌧": "rain", "🌨": "snow", "❄": "snow", "💨": "wind",
    "⛅": "partly", "🌩": "storm", "🌫": "fog", "🌀": "wind", "🌙": "moon",
    "🌇": "sunset", "🌅": "sunrise", "🌡": "thermo",
    "🏠": "home", "🏡": "home", "🧹": "vacuum", "🗑": "trash", "📦": "package",
    "📁": "folder", "🏷": "tag", "🗺": "map",
    "🧑": "person", "👤": "person", "🧍": "person", "👪": "people", "😴": "sleep",
    "😀": "person",
    "📊": "chart", "📋": "list", "📝": "note", "📰": "news", "📖": "book",
    "🔍": "search", "🔗": "link", "🧩": "puzzle", "🧪": "flask", "🪄": "wand",
    "🎮": "gamepad", "🕒": "clock", "🕰": "clock", "🌐": "globe", "🔤": "type",
    "🔥": "fire", "❔": "question",
    "🚌": "bus", "🚗": "car",
    "🟢": "dot", "⚪": "dot", "🟦": "square", "⭐": "star", "🔘": "toggle",
    "⏩": "refresh",
    "⬇": "download", "⬆": "upload", "☑": "check-box", "✳": "sparkle",

    # Dingbats that were sitting in icon slots. They are not emoji by default,
    # but a page that mixes drawn icons with font glyphs looks like two sets,
    # and several of these do render in colour on iOS.
    "▶": "play", "⏸": "pause", "⏮": "prev", "⏭": "next", "◀": "left",
    "☀": "sun", "☁": "cloud", "⛈": "storm", "❄": "snow", "☾": "moon",
    "⚙": "gear", "♫": "music", "⌂": "home", "◎": "target", "▦": "grid",
    "⛁": "database", "⌬": "hexagon", "✦": "sparkle", "⛶": "frame",
}
