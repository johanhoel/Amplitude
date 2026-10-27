# Panel sync to GitHub

Copies the Home Deck panel code from `~/homedeck` into the **`panels/`** folder on `main` of
**github.com/johanhoel/Amplitude**.

## Update GitHub after changing the panels

```bash
~/homedeck-tools/panel-sync.sh
```

That's all. If nothing changed it says `panels/ already up to date` and pushes nothing.

To see what would go up without pushing:

```bash
~/homedeck-tools/panel-sync.sh --dry-run
```

## What it does

- Takes everything that's committed in `~/homedeck`. Uncommitted edits are not included, so commit first.
- Leaves out the coordinator and the developer-tooling files, and refuses to push if any of them are left.
- Adds one commit on top of `main` (author Alex Demo) that replaces only `panels/`.
  Everything else in Amplitude (`dantestreamer/`, `README.md`, other branches) is never touched.
- Stops instead of overwriting if someone pushed to `main` in the meantime. Just run it again.

## Settings (files in `~/homedeck-tools/`)

| File | Value | Meaning |
|---|---|---|
| `panel-remote` | `git@github.com:johanhoel/Amplitude.git` | repo to push to |
| `panel-branch` | `main` | branch |
| `panel-prefix` | `panels` | folder in the repo (empty file = whole repo) |

## Access

Pushing uses the key `~/.ssh/homedeck-panel`, added as a deploy key with write access under
Amplitude → Settings → Deploy keys. Removing it there cuts off access.
If the push says `Permission denied (publickey)`, the deploy key is missing. Add this public key again:

```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIEmUJt9puDvccLXD4Ks6QAYJ/OGdsLrbOiAllyy8tH9g homedeck-panel-sync@lab-server
```
