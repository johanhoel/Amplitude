"""Home Deck: the backend behind the panel pages (Start, Admin, Family info, Media, Home, ...).

Settings: /opt/panel-wrapper/homedeck.toml (checked by config.py). Run: python3 /opt/panel-wrapper/server.py.
Modules by area: ha/home (Home Assistant), presence (phones on Wi-Fi), leave + notify (last one home, ntfy),
insights (Family + Network panels), transit/weather/news, audio (Genelec + Dante), layouts (edit mode),
links (status dots), status (wall-panel status), web (every /api route), main (starts everything), check (self-test).
"""
