"""Which parts of the panels this house actually has.

There used to be two editions: the owner's pages, and a copy with his
hardware cut out of them by a generator. Everybody except him ran the copy.
The cutting happened at build time against a list of CSS selectors, so a
house with no Genelecs got a build with the speaker dial deleted, and a house
that bought some later needed a new build to see it.

An addon is on when it is configured. Nothing here carries its own switch:
the Genelec dial appears because there are Genelecs in homedeck.toml, the bus
card appears because a stop is set, the PC controls appear because there is a
PC to talk to. The setup wizard fills that config in from what it finds on
the network, so a fresh install shows what the house has and nothing else.

The names are the ones build_www.py used to strip, because that list was
already the inventory of what is personal.

Plugins: the person who lives here can also switch a configured addon off
(the gear on the start page, Plugins). That only ever hides: an addon is on
when it is configured AND not switched off. The switches are a list of names
in settings.json ('addons_off'), so they survive updates and need no restart.
"""
import threading

from .config import C
from .layouts import layout_get
from .store import SETTINGS, load, save

# What each addon is, for the Plugins list: name -> (label, what it shows, what it needs when it is not set up)
PLUGINS = {
    'deck': ('Deck', 'The Buttons panel on Home', 'a Buttons page under [services] buttons_panel in homedeck.toml'),
    'speakers': ('Speakers', 'Volume dial, speaker and source picker', 'Genelec speakers in homedeck.toml'),
    'pc': ('PC', 'Wake, sleep and whether the PC is on', 'a PC under [pc] in homedeck.toml'),
    'cameras': ('Motion alerts', 'Camera motion alerts and the strip that shows them', 'a camera detection setting'),
    'charger': ('Car charger', 'The charger\'s power reading', 'a charger sensor'),
    'tv': ('TV', 'The TV section and its app shortcuts', 'a TV in homedeck.toml'),
    'spotify': ('Spotify', 'Now playing and the transport controls', 'a Spotify player'),
    'vacuum': ('Vacuum', 'The vacuum button', 'a vacuum entity'),
    'lock': ('Door lock', 'The door lock', 'a lock entity'),
    'bus': ('Bus departures', 'The next buses', 'a bus stop (the Family info editor)'),
    'weather': ('Weather', 'Outside temperature, the forecast and the next hours', 'a weather entity'),
    'lab': ('Lab', 'The Proxmox cluster and the lab panel', 'a lab panel service'),
}
_lock = threading.Lock()


def _set(name):
    """A config value that is really set, not left as a template placeholder."""
    v = getattr(C, name, None)
    if not v:
        return False
    text = str(v)
    return not (text.startswith('__') and text.endswith('__'))


def _bus_stop():
    """The stop the editor picked, else the one in homedeck.toml."""
    try:
        gid = str((layout_get('familyinfo').get('stop') or {}).get('gid') or '')
    except Exception:
        gid = ''
    return gid or (str(getattr(C, 'BUS_STOP', '') or ''))


def switched_off():
    return set(load(SETTINGS, {}).get('addons_off') or [])


def state():
    """{name: bool} - what this house has and wants. Cheap: config and settings reads, no network."""
    off = switched_off()
    return {k: v and k not in off for k, v in configured().items()}


def configured():
    """{name: bool} - what this house has. Cheap: config reads, no network."""
    pc_host = (getattr(C, 'PC', None) or ('', 0))[0]
    return {
        # The volume dial, the speaker picker and the source picker.
        'speakers': bool(getattr(C, 'GENELECS', None)),
        # Wake, sleep, and the line that says whether the PC is on.
        'pc': bool(pc_host),
        # Motion alerts and the strip that shows them.
        'cameras': _set('CAM_DETECT'),
        # The car charger's power reading.
        'charger': _set('CHARGER'),
        # The TV section and its app shortcuts.
        'tv': _set('TV'),
        # Now playing and the transport controls.
        'spotify': _set('SPOTIFY'),
        'vacuum': _set('VACUUM'),
        'lock': _set('LOCK'),
        # Next departures. On when a stop is set, here or in the editor.
        'bus': bool(_bus_stop()),
        # Outside temperature on Pulse, Start and Family info.
        'weather': _set('WEATHER'),
        # The Buttons page the Deck card shows inside itself. A status dot for the
        # Buttons service is not enough: the card embeds one panel's own address.
        'deck': _set('BUTTONS_PANEL'),
        # The Proxmox cluster and the lab panel.
        'lab': bool(getattr(C, 'LABPANEL', None)),
    }


def catalog():
    """[{name, label, what, needs, configured, on}] for the Plugins list, in a fixed order."""
    have, off = configured(), switched_off()
    return [{'name': k, 'label': lab, 'what': what, 'needs': needs, 'configured': have.get(k, False),
             'on': have.get(k, False) and k not in off} for k, (lab, what, needs) in PLUGINS.items()]


def switch(name, on):
    """Show (on) or hide (off) a plugin. Hiding works for any plugin; showing one that is not set up does nothing."""
    if name not in PLUGINS:
        raise ValueError('unknown plugin')
    with _lock:
        settings = load(SETTINGS, {})
        off = set(settings.get('addons_off') or [])
        (off.discard if on else off.add)(name)
        settings['addons_off'] = sorted(off)
        save(SETTINGS, settings)
    return {'enabled': enabled(), 'plugins': catalog()}


def enabled():
    """The addons that are on, space separated, for the pages to match on."""
    return ' '.join(sorted(k for k, v in state().items() if v))
