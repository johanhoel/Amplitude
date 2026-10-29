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
"""
from .config import C
from .layouts import layout_get


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


def state():
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
        # The Proxmox cluster and the lab panel.
        'lab': bool(getattr(C, 'LABPANEL', None)),
    }


def enabled():
    """The addons that are on, space separated, for the pages to match on."""
    return ' '.join(sorted(k for k, v in state().items() if v))
