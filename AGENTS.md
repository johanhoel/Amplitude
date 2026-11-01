# amplitude - guide for coding agents

These rules apply to every agent and every project folder in this repo: Claude sessions, local models, scripts.
A project's own `AGENTS.md` adds to them. Where the two disagree, the stricter rule wins.

Read the whole file before your first change. It is short on purpose.

## The rules in one screen

1. **Start from `main` as it is now.** Fetch and merge `origin/main` before you start and again before you push.
2. **Work on a branch.** Changes reach `main` through a pull request with a green CI.
3. **One change per commit.** A commit does one thing, so `git revert <commit>` undoes exactly that thing.
4. **Document every change and its reason.** Use the commit message template below, every time.
5. **Run the project's tests before every commit.** The table below lists them. All must pass.
6. **Never weaken a test to make it pass.** Fix the code, or explain in the commit why the test was wrong.
7. **Try changes on staging, never on production.** Deploy only when Johan asks for it, in your session.
8. **Keep private values out of git.** No real addresses, names, MAC addresses, tokens or topics.
9. **When something breaks, stop.** Revert your change, say what happened, and fix it on a branch.
10. **Leave notes for the next agent.** A new rule, a moved file or a known gap goes in the commit message.

## Before you start

- Run `git fetch` and `git merge origin/main`. Read the newest commit messages for the folder you work in.
- Check the CI on `main`: GitHub, Actions. A red run on `main` is the first thing to fix, before any other work.
- This repository is the only source for its projects. `johanhoel/camwatch` is an older, separate CamWatch
  repository and is retired. Never build, release or deploy from it, or from any other copy of a project.
- Several sessions work here on the same day, from different machines. A file that changed since you last read it
  was changed on purpose. Merge with it; never overwrite it.

## Every change is documented, so it can be undone

Each commit message follows this template:

```
<project>: <what changed, in one line>

Why: the problem, and how you found it.
What: the change. Name the files when that is not obvious.
Tests: the commands you ran, and their result (for example "21/21 files, 767 checks").
Revert: git revert <this commit>. Name anything a revert does not undo: a server setting, a migrated file,
        a secret, a container.
```

- A user-facing change also gets a line in the project's `CHANGELOG.md`, in the same commit.
- Keep a commit to one change. Unrelated fixes go in their own commits.
- A change to a server (a settings file, a systemd unit, a moved folder) is a change too.
  Describe it in the commit that needs it, with the command that undoes it.
- Keep a backup before you change a file on a server, named `<file>.bak-<date>-<reason>`.
- Never rewrite published history (`git push --force` on `main`) unless Johan asks for it in your session.

## Tests to run before every commit

Run the tests for each project you touched. On Windows, run Python with `PYTHONUTF8=1`.

| Project | Before every commit | Also when |
|---|---|---|
| `CamWatch/` | `python tests/run.py --quick` (in `CamWatch/`) | the full `python tests/run.py` when you touched search, share, timelapse or the models |
| `panels/` | `tools/check.sh`, or every file in `panels/tests/` except `smoke.py` | `tests/smoke.py` with staging running (`HOMEDECK_STUB=1 tools/staging.sh`) when you changed a page |
| `design/` | `python design/check-icons.py`, `check-theme.py` and `check-contrast.py` | also CamWatch's `tests/test_design_tokens.py` and `panels/tests/tokens.py` |
| `installers/` | `bash -n installers/linux/setup.sh` and `python installers/tests/check.py` | |
| `dstreamer/` | `bash -n dstreamer/docker-entrypoint.sh`, and `docker compose config -q` in `dstreamer/` | the image build in `dstreamer/BUILD_AND_TEST.md` before a release |
| `dstreamer-desktop/` | the build in GitHub Actions ("Build DStreamer Desktop Apps") | `swift build` (macOS) or `dotnet build` (Windows) when you have the machine |
| `.github/workflows/` | the file loads as YAML | the workflow's next run is green |

- A new feature comes with a test that fails without it. Break the code on purpose once and watch the test fail.
- A bug fix comes with a test that would have caught the bug.
- Do not push while a test fails. "It was red before" is not a reason: fix it first, or ask Johan.

## Deploying (only when Johan asks)

The update buttons in CamWatch and Home Deck install `main` from GitHub, on Johan's servers and on his friends'.
So `main` must always be installable.

On 2026-10-31 a night of untested commits went straight to `main`. The CI failed on every one of them. Each was
installed on the production server to see whether it ran. A rollback then came from the retired repository, and
production ran three-day-old code until 2026-11-01. The unreviewed work is on the branch `camwatch-phase-2-3`.

- Deploy only when Johan asks for it in your session. Staging first, always.
- CamWatch: `extras/release.sh staging`, then `production` (it keeps a backup and rolls back by itself).
  From Windows, build the code with `git -c core.autocrlf=false archive`, or the scripts get Windows line endings.
- Home Deck: `panels/tools/deploy.sh`. It tries the new version on port 8099 before it goes live.
  The server's address is in `panels/.deploy-host` (ignored by git) or `HOMEDECK_HOST`.
- After a deploy, check the result: the version on the server, every container healthy, the main pages answer.
- Never test an unfinished change on production. Never install code that has not passed its tests.

## When something breaks

1. Stop. Do not stack fixes on a broken change.
2. Revert your commit (`git revert`), or roll the server back (CamWatch: the update helper or `.releases/`;
   Home Deck: `homedeck-apply` puts the last good snapshot back).
3. Tell Johan what broke, what you reverted, and what is still wrong.
4. Fix it on a branch, with a test that catches it.

## Layout

One top-level folder per project, each with its own `README.md` and `CHANGELOG.md`. The root `README.md` indexes
them; add a row there for a new project.

## Every README has the same shape (always)

A reader who knows one project should find their way around the next one
without looking. Sections come in this order, and keep these names:

```
# <Name>            one line: what it does, for whom
<logo, optional>
<intro, 3 to 6 lines>
## Screenshots      the tables, per the Screenshots rules below
## Features         what it can do, one bullet each
## Install          what you need, then the commands
## Use              running it day to day
## How it is built  folders, containers, hosts, ports
## Troubleshooting  symptom and fix
## Notes            privacy, licences, roadmap
```

- The title is the project's name as people say it, not the folder name
  where the two differ: `panels/` is titled `# Home Deck`.
- Leave a section out when the project has nothing for it. Never reorder
  them, and never invent a synonym (`Setup`, `Getting started`, `About`).
- Anything longer than a screenful goes under `###` inside its section,
  not into a new `##`.

## Private values stay off GitHub (always)

The repository is public. Its history was rewritten on 2026-10-28 to remove the owner's private data.
Where something still has to stand for a real value it is a placeholder: `192.168.1.x` for the home network
and `home.example.net` for the outside address. Tests and examples use the same placeholders, or `192.0.2.x`.

- Never commit real addresses, names, MAC addresses, tokens or topics.
- Better than a placeholder is nothing: `panels/server` ships no house at all since 2026-10-29. The settings
  template is empty, and a page that needs to know something about the house asks the settings for it
  (`[links.extra]` for the consoles, `[services] buttons_panel` for the Deck, `[entities]` for the players).
  `panels/tests/install.py` fails on an address from any private network in the template or in `server/www`.
  The home network comes from the settings too: `[network] home_subnet`, else the first Pi-hole's /24.
  Test addresses with `config.at_home()`, never with a written-out prefix (`panels/tests/subnet.py` checks).
- Panels: the live Home Deck keeps its real values in two files that are never in git.
  `/opt/panel-wrapper/homedeck.toml` holds the settings. `/opt/panel-wrapper/private.map` lists
  `placeholder==>real value` pairs.
- `panels/tools/deploy.sh` and the update card in Home Deck's Settings (`kit/homedeck-update`) both apply
  `private.map` before they build, and neither uploads `homedeck.toml`. Keep it that way: without it, the
  placeholders would break presence on the live house.
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
