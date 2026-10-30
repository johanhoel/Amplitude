# Services: connecting Home Deck to the rest of the house

A house gains machines over time — a Grafana, a Proxmox node, a second Pi-hole, an NVR, whatever
comes next. Each one used to mean an edit to `homedeck.toml` and a restart, and knowing which key
to put where. This is the mechanism that replaced that, and the recipe for adding the next one.

## What a service is here

One entry in `SERVICES` in `server/homedeck/services.py`. Nothing else. The entry carries
everything the Studio needs to teach, test and save it:

```python
Service(
    id="grafana",                       # settings key, status-dot id, URL fragment
    name="Grafana",
    gives="Graphs of the house on Ops, and a dot on Start when it stops answering.",
    find="Usually http://ADDRESS:3000 — the machine you installed it on.",
    probe="/api/health",                # GET; any answer at all counts as up
    secret=None,                        # or ("name shown", "where the user makes one")
    steps=[
        "Open Grafana and check the address in your browser's bar.",
        "Paste it below and press Test.",
    ],
)
```

## Where a connection is stored

Two layers, and the difference matters:

| Layer | Written by | Holds |
|---|---|---|
| `homedeck.toml` | the installer and the setup wizard, as root | what the house was built with |
| `/var/lib/panel-wrapper/settings.json` | Home Deck itself, while it runs | what you added afterwards |

Home Deck runs as `panel-wrapper` and **cannot write its own `homedeck.toml`** — by design, so a
web page can never change what the panels restart into. Services therefore save into
`settings.json` under `services`, which needs no restart and no root:

```json
{ "services": { "grafana": { "url": "http://10.0.0.9:3000" } } }
```

`services.url(id)` is what the code reads. It prefers the saved value, falls back to the matching
`[services]` key in `homedeck.toml`, and returns `""` when the house has neither — which is the
same "empty means this house has not got it" rule the addons follow.

## Adding a service

1. Add the `Service(...)` entry. That alone gives you the Studio card, the guided steps, the Test
   button, the saved address and the status dot.
2. If something in the panels should *use* it, read it with `services.url("your_id")` rather than a
   constant. One line.
3. If it needs a secret, give the entry a `secret=` pair. The value goes to `secrets.json` (mode
   600, never sent to a page), not to `settings.json`.
4. Add a line to `tests/services.py`'s expectations if the service is one the pages depend on.

There is deliberately no plugin loading, no per-service module and no discovery protocol. A service
is a name, an address, a way to check it and a sentence about what it gives you; anything more
belongs in the thing being connected, not here.

## What the Studio shows

Studio → Services lists every entry in three states:

- **Connected** — saved and answering. Shows the address and the round-trip in ms.
- **Not answering** — saved but silent. The commonest cause is the machine being off, so the card
  says when it last answered rather than treating it as unset.
- **Not set up** — no address yet. The card is the tutorial: what you get, where to find the
  address, a field and a Test button.

A service that is not set up is never hidden. Hiding it would make the house's possibilities
invisible, which is the opposite of what this page is for.
