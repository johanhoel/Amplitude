#!/usr/bin/env python3
"""The shared component layer: one set of parts for panels and CamWatch.

The tokens made the two projects agree on colour; this makes them agree on
shape. The vocabulary is CamWatch's dashboard, which was already the clearest
page in either project: a strip of stat tiles, quiet uppercase section
headings, and a grid of identical tiles that each carry an icon, a name and a
line saying what it is. Nothing is decorated; it reads because it repeats.

Values are taken from CamWatch/app/dashboard.html as it stood, so adopting
this changes nothing about how CamWatch looks. The panels move to meet it.

Every class is prefixed ui-. That is not house style, it is a scar: the icon
work first used .ic, which the panels already used for something else, and
391 existing rules silently restyled every icon. A prefix makes a collision
impossible to introduce by accident.

Run design/sync-components.py after editing, then commit both.
"""

CSS = """
/* ---- page ------------------------------------------------------------
   One column, centred, with the phone's safe areas added to the padding so
   a home-screen app runs edge to edge without putting text under a bar. */
.ui-page {
  max-width: var(--ui-page-w, 1000px);
  margin: 0 auto;
  padding:
    calc(env(safe-area-inset-top, 0px) + 10px)
    calc(env(safe-area-inset-right, 0px) + 12px)
    calc(env(safe-area-inset-bottom, 0px) + 30px)
    calc(env(safe-area-inset-left, 0px) + 12px);
}

/* ---- header ---------------------------------------------------------- */
.ui-head { display: flex; align-items: center; gap: 10px; margin: 2px 0 14px; }
.ui-head h1 { flex: 1; margin: 0; font-size: 26px; font-weight: 750; letter-spacing: -0.015em; }
.ui-head h1 small { color: var(--mute); font-size: 15px; font-weight: 600; margin-left: 6px; }
.ui-head .ui-mark { width: 28px; height: 28px; flex: none; }

/* ---- section heading -------------------------------------------------
   Quiet, spaced capitals. It names the group and then gets out of the way;
   the tiles below it carry the weight. */
.ui-cap {
  display: flex; align-items: center; gap: 8px;
  margin: 18px 2px 8px;
  font-size: 13px; font-weight: 700; letter-spacing: .12em;
  text-transform: uppercase; color: var(--mute);
}
.ui-cap .icon { color: var(--dim); }
/* A heading placed inside a grid rather than above it spans every column. */
.ui-cap-row { grid-column: 1 / -1; }
.ui-cap em { font-style: normal; letter-spacing: 0; text-transform: none;
  font-weight: 500; color: var(--dim); font-size: 13px; }

/* ---- stat strip ------------------------------------------------------
   A label and the number it describes. The number is the thing being read,
   so it gets the weight; the label stays muted above it. */
.ui-stats { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 10px; }
.ui-stat {
  background: var(--card); border: 1px solid var(--line);
  border-radius: var(--r, 18px); padding: 12px 14px; min-height: 88px;
}
.ui-stat b { display: block; font-size: 26px; font-weight: 750; line-height: 1.15;
  font-variant-numeric: tabular-nums; }
.ui-stat span { color: var(--mute); font-size: 13px; }
.ui-stat .small { display: block; font-size: 16px; font-weight: 700; line-height: 1.3; margin-top: 4px; }
.ui-stat .ok { color: var(--ok); } .ui-stat .warn { color: var(--warn); } .ui-stat .bad { color: var(--bad); }

/* ---- tiles -----------------------------------------------------------
   The repeating unit: icon, name, and a line saying what it is. Identical
   every time, which is what makes a wall of them readable at a glance. */
.ui-tiles { display: grid; grid-template-columns: repeat(auto-fill, minmax(var(--ui-tile-w, 150px), 1fr)); gap: 10px; }
.ui-tile {
  display: flex; flex-direction: column; gap: 4px;
  background: var(--card); border: 1px solid var(--line);
  border-radius: var(--r, 18px); padding: 14px; min-height: 104px;
  color: inherit; text-decoration: none;
  transition: border-color .15s var(--ease-out, ease), transform .15s var(--ease-out, ease);
}
/* A tile may carry its own accent, so a wall of them is still scannable by
   colour. It falls back to the one accent when nothing sets --c. */
.ui-tile .icon { font-size: 26px; color: var(--c, var(--accent)); }
.ui-tile b { font-size: 15.5px; font-weight: 650; letter-spacing: -0.005em;
  display: flex; align-items: center; gap: 7px; }
.ui-tile > span { color: var(--mute); font-size: 12.5px; line-height: 1.4; }
/* An optional third line: the address a tile opens, or any quiet detail.
   It must not push the tile wider, so it truncates. */
.ui-tile small { display: block; margin-top: auto; padding-top: 6px;
  color: var(--dim); font-size: 11.5px; overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap; max-width: 100%; }
.ui-tile b .ui-dot { margin-left: auto; }
/* A row of small icons at the foot of a tile, saying what is inside it -
   which modules a board holds, which cameras a group covers. Muted, because
   it is a hint about the contents, not the contents. */
.ui-tile-icons { display: flex; gap: 7px; margin-top: auto; padding-top: 10px;
  font-size: 17px; flex-wrap: wrap; }
/* Specific enough to beat .ui-tile .icon, which paints the tile's own icon in
   the accent. These are a hint about the contents, so they stay muted. */
.ui-tile .ui-tile-icons .icon { color: var(--dim); }
/* The tile that adds another one. Dashed, so it reads as an outline waiting
   to be filled rather than a card that failed to load. */
.ui-tile.is-new {
  border-style: dashed; border-color: color-mix(in srgb, var(--accent) 55%, var(--line));
  background: color-mix(in srgb, var(--accent) 7%, transparent);
  color: var(--accent-text); font-weight: 650;
  align-items: center; justify-content: center; text-align: center;
}
/* Hover only where there is a pointer: on a touch screen it sticks after a tap. */
@media (hover: hover) and (pointer: fine) {
  .ui-tile:hover { border-color: var(--accent); }
}
/* Pressable things answer the press. Subtle on purpose - these are tapped often. */
.ui-tile:active { transform: scale(0.985); }
.ui-tile:focus-visible { outline: 3px solid var(--accent); outline-offset: 3px; }
/* The one tile that matters most in a group. */
.ui-tile.is-lead { border-color: color-mix(in srgb, var(--accent) 45%, var(--line)); }
/* State, shown as a dot in the corner rather than a word. */
.ui-tile .ui-dot { margin-left: auto; }
.ui-tile .ui-row { display: flex; align-items: center; gap: 8px; }

/* A dot that says running / needs attention / down, in the status colours. */
.ui-dot { width: 8px; height: 8px; border-radius: 50%; flex: none; background: var(--faint); }
.ui-dot.is-ok { background: var(--ok); } .ui-dot.is-warn { background: var(--warn); }
.ui-dot.is-bad { background: var(--bad); }

/* ---- control tile -----------------------------------------------------
   A button that does something to the house, as opposed to .ui-tile, which
   goes somewhere. Promoted out of control.html, which had the only good one.
   It carries four things a link never needs: an on state, a hold-to-confirm
   fill, a busy/done/failed outcome, and a warning border.

   The on state inverts - a light surface with dark type - because at a glance
   across a room "lit up" reads faster than a changed border. Both colours are
   tokens so the inversion follows the palette instead of being two hardcoded
   greys, which is what it was. */
.ui-ctl {
  position: relative; overflow: hidden; text-align: left;
  display: flex; align-items: center; gap: 11px;
  border-radius: var(--r, 18px); padding: 12px;
  background: var(--card); border: 1px solid var(--line);
  color: inherit; font: inherit; cursor: pointer;
  transition: transform .15s var(--ease-out, ease), background .15s var(--ease-out, ease),
              border-color .15s var(--ease-out, ease);
}
.ui-ctl:active { transform: scale(0.97); }
.ui-ctl:focus-visible { outline: 3px solid var(--accent); outline-offset: 3px; }
.ui-ctl .ui-ctl-ic {
  width: 36px; height: 36px; border-radius: 50%; flex: none;
  display: grid; place-items: center; font-size: 17px;
  background: var(--card-hi);
}
.ui-ctl b { font-size: 14px; font-weight: 650; line-height: 1.2; }
.ui-ctl small { display: block; font-size: 12px; color: var(--mute); margin-top: 2px; }

/* On. 16.23:1 for the title, 7.15:1 for the line under it. */
.ui-ctl.is-on { background: var(--ink); color: var(--bg); border-color: transparent; }
.ui-ctl.is-on small { color: #4a5159; }
.ui-ctl.is-on .ui-ctl-ic { background: var(--c, var(--ok)); color: var(--status-ink); }

/* Hold to confirm: the fill grows across the tile for as long as the finger
   is down, so the wait is visible rather than a button that seems stuck. */
.ui-ctl .ui-ctl-fill { position: absolute; inset: 0 auto 0 0; width: 0;
  background: color-mix(in srgb, var(--accent) 35%, transparent); pointer-events: none; }
.ui-ctl .ui-ctl-hold { position: absolute; top: 10px; right: 12px;
  font-size: 10px; letter-spacing: .08em; text-transform: uppercase;
  color: var(--dim); font-weight: 700; }
.ui-ctl.is-on .ui-ctl-hold { color: #5e656e; }
/* The badge sits over the top-right corner, so the title needs that corner
   kept clear or it wraps underneath it. */
.ui-ctl:has(.ui-ctl-hold) b { padding-right: 36px; }

/* Outcome, held briefly after the tap so the result is seen. */
.ui-ctl.is-busy { opacity: .55; }
.ui-ctl.is-done { border-color: var(--ok); }
.ui-ctl.is-failed { border-color: var(--bad); }
.ui-ctl.is-warn { border-color: color-mix(in srgb, var(--warn) 35%, transparent); }
.ui-ctl.is-bad { border-color: color-mix(in srgb, var(--bad) 40%, transparent); }

@media (prefers-reduced-motion: reduce) {
  .ui-ctl { transition-duration: .01ms; }
  .ui-ctl:active { transform: none; }
}

/* ---- grouped list ----------------------------------------------------
   A card of rows divided by hairlines, each row an icon, a title with a line
   under it, and something on the right - a status, a count, a chevron. The
   third shape both projects need and neither shared: admin's console links,
   CamWatch's settings. A tile is for a handful of destinations you scan; a
   list is for many you read down. */
.ui-list {
  border-radius: var(--r); background: var(--card);
  border: 1px solid var(--line); overflow: hidden;
}
.ui-list-row {
  display: grid; grid-template-columns: 30px minmax(0, 1fr) auto;
  gap: 12px; align-items: center;
  padding: 11px 14px; min-height: 54px;
  border-top: 1px solid var(--line);
  color: inherit; text-decoration: none;
  transition: background .15s var(--ease-out, ease);
}
/* The card's own border draws the top edge of the first row. */
.ui-list-row:first-child { border-top: 0; }
.ui-list-row .icon { font-size: 20px; color: var(--accent); justify-self: center; }
.ui-list-row b { display: block; font-size: 15.5px; font-weight: 600;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ui-list-row small { display: block; font-size: 12.5px; color: var(--mute);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-top: 1px; }
.ui-list-meta { display: flex; align-items: center; gap: 8px;
  color: var(--mute); font-size: 12px; }
.ui-chev { opacity: .35; font-size: 18px; }
@media (hover: hover) and (pointer: fine) {
  .ui-list-row:hover { background: var(--card-hi); }
}
.ui-list-row:active { background: var(--card-hi); }
.ui-list-row:focus-visible { outline: 3px solid var(--accent); outline-offset: -3px; }
@media (prefers-reduced-motion: reduce) { .ui-list-row { transition-duration: .01ms; } }


/* ---- nothing here -----------------------------------------------------
   A page whose cards all belong to hardware this house has not got ends up
   blank, and blank reads as broken. This says what is missing and where to
   say what the house has. Quiet on purpose: it is not an error. */
.ui-empty { padding: 44px 24px; text-align: center; color: var(--mute); font-size: 14px; line-height: 1.55; }
.ui-empty b { display: block; color: var(--ink); font-size: 16px; font-weight: 650; margin-bottom: 6px; }
.ui-empty p { margin: 0 auto; max-width: 44ch; }
.ui-empty a { color: var(--accent-text); text-decoration: none; }
/* Beside something rather than instead of it: a page with one card on it
   needs the same sentence, but as an aside under the card, not centred in
   the hole where the other cards would be. */
.ui-empty.is-aside { text-align: left; padding: 4px 2px 0; }

/* A heading whose list came back empty is a heading over nothing, and reads
   as something that failed to load. The pages fill these containers from
   JavaScript, so an empty one really is empty and :empty is exact. */
.ui-cap:has(+ :empty), .cap:has(+ :empty) { display: none; }
.ui-empty.is-aside p { margin: 0; }
@media (hover: hover) and (pointer: fine) { .ui-empty a:hover { text-decoration: underline; } }

/* ---- search ---------------------------------------------------------- */
.ui-search { margin-top: 12px; }
.ui-search input {
  width: 100%; min-height: 48px; padding: 0 16px;
  border-radius: var(--r-sm, 12px); border: 1px solid var(--line);
  background: var(--card); color: var(--ink); font: inherit; font-size: 16px;
}
.ui-search input::placeholder { color: var(--dim); }
.ui-search input:focus { outline: none; border-color: var(--accent); }

@media (prefers-reduced-motion: reduce) {
  .ui-tile { transition-duration: .01ms; }
  .ui-tile:active { transform: none; }
}
"""
