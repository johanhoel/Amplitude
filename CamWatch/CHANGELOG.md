# CamWatch: latest changes

Newest changes first.

## 2026-10-30 (3)

- Settings -> Image processing showed a C++ backtrace where it meant to say why a model stays on the
  CPU. It put the first 300 characters of the onnxruntime failure in the tooltip, which on a real
  install read "... const onnxruntime::openv" - cut mid-symbol. The reason is kept and the machinery
  dropped, so that row now says "Model is not supported by the device: operation NonMaxSuppression is
  not supported". Where nothing readable is left it says "the GPU driver refused this model", and the
  whole error goes to the log instead of the page.

## 2026-10-30 (2)

- The dashboard's "Package at ..." card led to Not Found. It linked to /clips, which is not a page:
  the clips list is /, and the only /clips routes are the two POSTs behind Select. The card now opens
  the clip the package was seen in, which is what the phone home has always done.
- The dashboard's "something unusual" alert never appeared. It read s.unusual; /api/status sends
  unusual_today, a list. It now shows the three most recent, each opening its clip.
- tests/test_links.py (4 checks): every path the static pages name is served by a route. The pages are
  served as they are and their links are string literals, so nothing looked at them before - test_routes.py
  walks the routes and asks whether they render, which is the other direction.

## 2026-10-30

- The dashboard is yours. Studio is a console now, the same shape as Home Deck's: a column of sections on the
  left, one at a time on the right. Its first section chooses what the dashboard shows - needs attention,
  today's numbers, search, now, cameras, where people walked, the page directory, and the weather once Home
  Deck is linked - in the order you put them, and which page camwatch opens on, including the icon on a phone.
  Setting cameras up is still there, under Cameras and Discover, with the changes collected and applied
  together. Devices that are not cameras no longer offer an identical Add button.
- The Mac installer is gone. CamWatch installs on Debian, Ubuntu or a Raspberry Pi with
  installers/linux/setup.sh, or in a Linux machine on a Mac - see docs/install-windows-mac.md.
- The README follows the shape every project in this repository now uses: Screenshots,
  Features, Install, Use, How it is built, Notes. Screenshots come before the feature list,
  the camera, update, storage, GPU and Home Deck sections sit under Use, and the container
  table under How it is built. Nothing was dropped; the opening paragraph is four lines
  instead of one sentence.
- The page bar says there is more of it. Fifteen pages, about ten of which fit: the bar scrolled sideways with
  its scrollbar hidden, so Plates, Zones, Studio, Settings and Home Assistant were not merely off the edge,
  nothing said they existed. The edge with more behind it now fades, and the page you are on is brought into
  view when it loads.
- The phone home said "1 people seen". It says "1 person seen".

## 2026-10-29

- New: Studio. Every camera and every device Home Deck knows about, in one list, with the ones a network
  scan finds. Adding a camera is a slot, a name and a stream address collected as a draft and applied
  together, instead of four separate forms on the Settings page. The apply before this one can be undone.
- New: the camera scan searches several networks at once, for houses that keep cameras on their own VLAN. The
  networks are suggested from the addresses already known - the one you reach CamWatch on, the ones the cameras
  are on, and the ones Home Deck's devices are on - and the list is remembered for the next scan.
- New: CamWatch links with the Studio in Home Deck. Settings → Home Deck makes the link key.
- The Studio lists CamWatch's cameras. A watched camera sends a notice when it goes offline.
- The Studio's People page shows when a camera last saw each person.
- The camera finder names cameras with Home Deck's names. It also lists cameras that the scan missed.
- The People page lists Home Deck's people who have no photos yet.
- The version is now 2026.10.29.4.
- New in Settings: Image processing. The image models can now use a GPU.
- Each model switches the next time it runs. Recording does not stop.
- Settings shows what each part runs on: objects, number plates, faces and search.
- On an Intel HD Graphics 630, object detection is about 3 times faster on the GPU.
- When a GPU cannot run a model, that model stays on the CPU. The face models always use the CPU.
- New in Settings: GPU on the server. The update helper scans the server for a GPU.
- The scan finds GPUs in Proxmox containers, in virtual machines and without a driver. Settings shows the next step.
- **Add GPU support** builds CamWatch with Intel (OpenVINO) or NVIDIA (CUDA) support. A failed build rolls back.
- The GPU build needs 6 GB free on Docker's disk. With less, the helper stops and says so.
- Fix: the recorder log no longer fills with `pthread_setaffinity_np failed` errors.
- The number plate models now get a fixed number of threads, like the other models.
- The version is now 2026.10.29.1.
- The face models now always use the CPU. Their GPU code did not compile on the Intel HD 630.
- A model that a GPU cannot run shows "this GPU cannot run this model" in grey, not a red error.
- The version is now 2026.10.29.2.

## 2026-10-28

- New: installers for Windows (`CamWatch-Setup.exe`) and Mac (`CamWatch.dmg`). See `installers/README.md` in amplitude.
- The installers set up CamWatch without a camera. You add the camera in Settings → Cameras.
- `deploy.sh` now installs Docker on Ubuntu too. Before this fix, it only worked on Debian.
- A green ⬆ Update button shows in the top bar of every page when a new version is ready.
- CamWatch asks GitHub every 30 minutes in the background. A page never waits for GitHub.
- Where recordings go works now. Before this fix, the helper on the server stopped at the start of a move.
- New guide: CamWatch on Windows and macOS (`docs/install-windows-mac.md`).
- The version is now 2026.10.28.10.
- Settings has a new section: Storage.
- Keep clips sets how long clips stay and how much disk stays free. Before, you set this in `.env`.
- Keep clips also shows how full the disk is and the date of the oldest clip.
- Where recordings go moves the recordings to another folder, another disk or a network share.
- A network share can be NFS or SMB (Windows, most NAS boxes).
- CamWatch copies the recordings first and keeps recording while it copies.
- When the new place does not work, CamWatch goes back to the old folder. The old copy stays until you delete it.
- A Proxmox container cannot connect to a network share itself. Settings then shows the Proxmox steps.
- Updates also work when an old or wrong access key is saved. CamWatch then asks GitHub without the key.
- The version is now 2026.10.28.9.
- The amplitude repository is public now. Updates need no access key.
- Request a feature works without a key: GitHub opens with your request filled in, and you press Submit.
- With a key, CamWatch still sends requests by itself. The key is optional now.
- The key guide and the README explain the new way.
- The version is now 2026.10.28.8.
- A banner at the top of Settings shows when a new version is ready.
- Updates has a Check again button. It asks GitHub at once.
- CamWatch now keeps GitHub's answer for 3 minutes, not 10.
- The version is now 2026.10.28.7.
- The Clips page has a Select button. You tick several clips at once.
- Download gives the ticked clips as one zip file: each video and its picture.
- Delete removes the ticked clips after one question. It tells you when starred clips are among them.
- The version is now 2026.10.28.6.
- New page: Request a feature. The link sits at the bottom of every page and in Settings → Updates.
- Each request becomes an issue on GitHub, so the developer gets it.
- The page lists your requests and shows which ones are done.
- CamWatch keeps every request, also when GitHub refuses it. Send again retries.
- The access key now also needs Issues: Read and write. The guide shows how to add it to your key.
- The version is now 2026.10.28.5.
- On a computer, Settings shows its sections in pairs, side by side.
- The pairs: Alerts and login with Snooze, Notifications with Off-site storage, Home Assistant with Updates.
- Cameras keep the full width. On a phone, all sections stay one below the other.
- The version is now 2026.10.28.4.
- An update no longer fails because of a container that was broken before the update.
- `release.sh` lists those containers at the end and skips them in the health check.
- `presence` waits quietly when `.env` has no `DB_PASSWORD`. Before this fix, it was unhealthy.
- Without `DB_PASSWORD`, the visit log stays off.
- A server installed from a git clone now knows its own commit. `deploy.sh` writes it into `app/BUILD`.
- Before this fix, Updates offered the same version again and again on such a server.
- A server without a known commit only gets an update with a higher version number.
- The version is now 2026.10.28.3.
- The 🗑 Remove button on a camera card works now.
- Before this fix, a click on Remove did nothing. The camera name broke the button's code.
- The version is now 2026.10.28.2.
- Updates links to a step-by-step guide for the GitHub access key.
- The guide also opens when GitHub refuses the key.
- The same guide is in `docs/update-key.md`.
- The version is now 2026.10.28.1. This release also tests the update button.
- Settings has a new section: Updates.
- Updates shows the version that runs on the server.
- Updates checks GitHub for a newer version.
- When a newer version exists, Update now installs it from the web page.
- A helper on the server does the update. `deploy.sh` and `release.sh` install it.
- A failed update puts the old version back by itself.
- A private repository needs an access key. You enter it in Updates.
- Zones show in the same place on a phone and on a computer.
- Before this fix, the zone editor drew on the button row above the picture too. Zones moved up on a phone.
- Zones drawn before this fix can sit slightly too high: up to about 7% of the picture at the top. Check them in Zones.
- Settings → Notifications has a new field: Link in pushes.
- Pushes, push buttons, face pushes, Home Assistant and the daily summary use this address.
- Use this address fills in the address you have open. `WEB_BASE_URL` in `.env` only counts until you save the field.
- CamWatch has a logo: an eye with a camera aperture as its iris, and a red recording dot.
- The logo shows in every page header and in the browser tab.
- The app icons on the phone home screen use the logo.
- The README starts with the logo and the name.
- `dev/make_logo.py` makes all logo files.
- Each camera card in Settings has a 🗑 Remove button.
- Remove asks first. Camera 1 then switches off. The other cameras lose their name and address.
- The recordings of a removed camera stay.
- Releases show their own commit again. `app/BUILD` held a fixed commit (a96c889) after the move into amplitude.
- The version is now 2026.10.28.
- All screenshots are new: they show the logo and the Remove button.

## 2026-10-27

- The README install steps now copy `amplitude` and work in `CamWatch/`.
- The old install steps pointed at a CamWatch repo of its own.
- The README shows a screenshot of every page, on a computer and on a phone.
- `dev/screenshots.py` takes these screenshots from demo pictures.
- You can now switch off camera 1, like the other cameras.
- Every page shows the version number (2026.10.27).
- `/api/version` returns the same version number.
- `release.sh` now runs when `.env` has no `CAMWATCH_PREFIX`.
- Before this fix, `release.sh` stopped with no message in that case.

## 2026-10-26

- The dots (••••••) in a camera address always stand for the whole saved password.
- Settings refuses a camera address where you changed only part of the dots.
- Settings keeps passwords with `/ # ? @` exactly as you typed them.
- A test copy of CamWatch runs on the data disk with a fake camera.
- A new release goes back to the last version by itself when it fails.
- GitHub runs the tests automatically.
- The repo holds its own tests (`tests/run.py`).
- AGENTS.md tells coding assistants how to work in the repo.
- The phone home page (`/m`) shows what needs your attention first.
- On the phone home page, you swipe between live cameras.
- The phone home page also lists today's visits and recent visits.
- Settings can search your network for cameras.
- The camera search shows the maker and model of each camera.
- The camera search fills in the camera addresses for you.
- CamWatch can copy clips to iCloud Drive, Google Drive, OneDrive, Dropbox, Backblaze B2, S3 or a home file server.
- CamWatch encrypts these copies unless you switch encryption off.
- CamWatch copies alarm clips at once and all other clips every night.
- "Sign in again" renews the sign-in and keeps the encryption keys.
- CamWatch joins one visit seen by several cameras into one visit.
- A visit sends one phone alert.
- *Play all* plays the clips from every camera in a visit.
- Phone alerts have a Star button and a Snooze 1h button.
- CamWatch sends an alert when it sees activity at an unusual time.
- You set the phone alerts (ntfy) on the Settings page.
- You can install CamWatch on a phone like an app.
- Settings shows each camera on a card of its own.
- You can list trusted networks, where you log in without a password.
- You set cameras and Home Assistant on the Settings page.
- CamWatch records up to 4 cameras.
- CamWatch makes fast-forward videos of each day.
- CamWatch makes short videos of the main moments.
- You can share a copy of a clip with heads and number plates blurred.
- You can search clips by the objects in them, for example a car or a dog.
- Every page now uses the dark "Wall" look.

## 2026-10-25

- CamWatch notices strangers who come back again and again.
- You can search clips by a description in your own words.
- Phone alerts about people in your household arrive without sound.
- You can choose to log in without a password from your home network.
- The dashboard shows a summary of today.
- A weekly report counts visits per day and per hour.
- A map shows where people walk most often.
- CamWatch notices when someone leaves a package.
- You can tag clips from the wall view.
- The wall view (`/view`) shows the cameras on a phone or tablet.
- CamWatch warns you when recording stops.
- CamWatch sends an alert when a camera or a service stops working.
- CamWatch cleans up its list of number plates.
- Home Assistant receives a separate event for each type of activity.
- CamWatch backs up its database.
- CamWatch added to this repo.
