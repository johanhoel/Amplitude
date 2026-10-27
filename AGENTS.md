# amplitude - guide for coding agents

These rules apply to every project folder in this repo. A project's own
`AGENTS.md` adds to them.

## Layout

One top-level folder per project, each with its own `README.md` and
`CHANGELOG.md`. The root `README.md` indexes them; add a row there for a
new project.

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
