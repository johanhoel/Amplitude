# amplitude - guide for coding agents

These rules apply to every project folder in this repo. A project's own
`AGENTS.md` adds to them.

## Layout

One top-level folder per project, each with its own `README.md` and
`CHANGELOG.md`. The root `README.md` indexes them; add a row there for a
new project.

## Several sessions work here at once (always)

Several Claude sessions commit to this repo on the same day, from different machines.

- Run `git fetch` and merge `origin/main` before you start, and again before you push.
- After a push, check it landed with `git ls-remote origin refs/heads/main`.
- Read the newest commit messages for the area you touch. They say what the other session changed and why.
- Say in your commit message what another session needs to know: a new rule, a file that moved, a known gap.

## Private values stay off GitHub (always)

The repository is public. Its history was rewritten on 2026-10-28 to remove the owner's private data.
Where something still has to stand for a real value it is a placeholder: `192.168.1.x` for the home network
and `home.example.net` for the outside address.

- Never commit real addresses, names, MAC addresses, tokens or topics.
- Better than a placeholder is nothing: `panels/server` ships no house at all since 2026-10-29. The settings
  template is empty, and a page that needs to know something about the house asks the settings for it
  (`[links.extra]` for the consoles, `[services] buttons_panel` for the Deck, `[entities]` for the players).
  `panels/tests/install.py` fails on an address from any private network in the template or in `server/www`.
  Three places still assume one subnet in code - `presence.py`, `insights.py` - and lean on `private.map`.
- Panels: the live Home Deck (`192.168.100.52`) keeps its real values in two files that are never in git.
  `/opt/panel-wrapper/homedeck.toml` holds the settings. `/opt/panel-wrapper/private.map` lists
  `placeholder==>real value` pairs.
- Deploy Panels only with `panels/tools/deploy.sh`. It applies `private.map`, never uploads `homedeck.toml`,
  and runs a trial on port 8099 before anything goes live.
- The update card in Home Deck's Settings (`kit/homedeck-update`) applies `private.map` too, before it builds.
  Keep it that way: without it, the placeholders would break presence on the live house.
  The live house does not have the updater installed. Use `deploy.sh` there.
- Home Deck runs as the user `panel-wrapper`. A file you write in `/var/lib/panel-wrapper` as root must go
  back to that user (`chown panel-wrapper:panel-wrapper`). Otherwise Home Deck cannot read it.
  On 2026-10-29 a root-owned `secrets.json` cost the house its tokens.

## Screenshots of features (always)

Every project shows what it can do, with screenshots.

- Each project has a `## Screenshots` section in its `README.md`, near
  the top (after the intro or feature list), and keeps the images in
  `<project>/docs/screenshots/`.
- Every user-facing feature gets one: each page, panel, app screen,
  control panel or settings view. A project with no UI shows its status
  or web panel, or the terminal output of its main command.
- Adding or changing a visible feature means adding or updating its
  screenshot in the same change. Don't call the work done without it.
- Files: JPG, about 1280 px wide (phone screens as they are), named after
  the feature in kebab-case, e.g. `start.jpg`, `phone-remote.jpg`.
- Captions follow the panels README: the image, then `**Name**: what it
  does`, in a two-column table. Phone screens: `<img ... width="300">`.

  ```markdown
  | | |
  |---|---|
  | ![Start](docs/screenshots/start.jpg)<br>**Start**: the wall home | ![Control](docs/screenshots/control.jpg)<br>**Control**: every switch |
  ```

- Nothing private in a screenshot: no passwords, tokens or keys, no
  faces or camera footage of people, no personal names, addresses or
  phone numbers. Use demo data or blur it.
- Mention new or updated screenshots in the project's `CHANGELOG.md`.

## Writing: no AI slop (always)

Every piece of prose in an update follows the
[no-ai-slop](https://github.com/petergyang/no-ai-slop) rules: READMEs,
`CHANGELOG.md` entries, docs, commit messages, pull requests, UI text and
code comments.

- With the `/no-ai-slop` skill installed, check new or changed prose with
  it before calling the work done. Without it, apply the rules below by
  hand.
- Lead with the point. Be concrete: names, numbers, file paths, what
  changed and why, not "improves the experience".
- Cut the banned words (delve, leverage, utilize, robust, seamless,
  streamline, empower, cutting-edge, game changer, transformative, ...)
  and empty filler ("it's worth noting", "at its core", "in order to").
- Cut the patterns: "It's not X. It's Y.", throat-clearing openers,
  "here's what nobody tells you", colon reveals ("The best part: it
  learns."), importance puffery ("a testament to", "a pivotal moment"),
  "experts agree" without a source, dramatic fragments, and fake-profound
  closing lines.
- Plain formatting: no emoji in headings, no bold sprinkled mid-sentence,
  no bullets where two sentences read better, no em dashes as a habit.
- Edits keep the author's voice: change what's sloppy, leave strong
  sentences alone.
