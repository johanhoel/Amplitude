# CamWatch — UX Architecture Document

**Version:** 1.0 · **Date:** 2026-10-31
**Author:** Senior UX Designer & Information Architect
**Product:** CamWatch — Self-hosted camera service for up to four RTSP cameras
**Platform:** Web app (desktop + mobile responsive) · PWA-capable
**Industry:** Smart Home / Prosumer Surveillance SaaS
**Target Users:** Tech-comfort home users who want a simple, self-hosted surveillance system with face recognition, number plate reading, and smart alerts.
**Core Problem:** Easy setup and onboarding — get cameras recording, identify people/vehicles, and stay informed via push notifications without cloud subscriptions.
**Inspiration:** Frigate, ZoneMinder, Home Assistant ecosystem

---

## Table of Contents

1. [Information Architecture (IA)](#1-information-architecture-ia)
2. [User Flows](#2-user-flows)
3. [Full Screen-by-Screen Breakdown](#3-full-screen-by-screen-breakdown)
4. [Microcopy for Every Screen](#4-microcopy-for-every-screen)
5. [Error States](#5-error-states)
6. [Empty States](#6-empty-states)
7. [Loading & Transition States](#7-loading--transition-states)
8. [Structural Recommendations](#8-structural-recommendations)

---

## 1. Information Architecture (IA)

### 1.1 Product Overview

CamWatch is a **self-hosted, LAN-based surveillance system** with two distinct interface surfaces:

| Surface | Route(s) | Purpose |
|---------|----------|--------|
| **Desktop Dashboard** | `/dashboard` | At-a-glance overview with configurable cards |
| **Desktop Web App** | All other routes | Full management, browsing, and configuration |
| **Mobile Home** | `/m` | Phone-optimized "what needs attention" screen |
| **Wall View** | `/view` | Tablet/phone live view + swipeable player |

### 1.2 Complete Sitemap

```
camwatch (root)
│
├── DASHBOARD (/dashboard)
│   ├── Configurable card layout (Studio-managed order)
│   │   ├── Stats card — today's summary
│   │   ├── Search card — quick search bar
│   │   ├── Now card — live snapshot + latest event
│   │   ├── Cameras card — multi-camera grid
│   │   ├── Pages card — navigation tiles to every section
│   │   ├── Heatmap card — 7-day heatmap thumbnail
│   │   ├── Attention card — alerts needing action
│   │   └── Weather card — Home Deck weather (optional)
│
├── CLIPS (/) -- "Clips" tab on mobile nav
│   ├── Clips listing page
│   │   ├── Day-grouped timeline view
│   │   ├── Filter chips (person, vehicle, package, etc.)
│   │   ├── Tag chips for filtering by detected objects
│   │   └── Bulk select mode (download/delete multiple)
│   ├── Individual clip viewer (/clip/<day>/<stem>)
│   │   ├── Video player with pre-roll
│   │   ├── Play all from same visit
│   │   ├── Tag faces in the clip
│   │   ├── Star/unstar toggle
│   │   ├── Share (blurred copy)
│   │   ├── Delete
│   │   └── Navigate to previous/next clip
│   ├── Timelapse (/timelapse)
│   │   ├── Daily timelapse player
│   │   ├── Highlights reel of every event
│   │   └── Build new timelapse button
│   └── Starred clips (?starred=1)
│
├── LIVE (/live) -- "Live" tab on mobile nav
│   ├── Multi-camera live view grid
│   ├── Camera picker (when multiple cameras)
│   ├── End-to-end test button (simulate motion -> push -> clip -> page)
│   └── Individual camera full-screen view (?camera=...)
│
├── WALL VIEW (/view) -- "Camera view" tile from dashboard
│   ├── Live picture grid with filter chips
│   ├── Swipeable full-screen player for recordings
│   └── Camera selector overlay
│
├── PEOPLE (and sub-pages)
│   ├── People library (/people)
│   │   ├── Grid of known people cards
│   │   ├── Each card: name, photo thumbnail, count
│   │   └── Add person button -> upload photos
│   ├── Person detail (/people/<name>)
│   │   ├── Person's reference photos
│   │   ├── Upload new photo
│   │   ├── Rename person
│   │   ├── Delete person
│   │   └── Clips where this person was detected
│   └── Home Deck integration (linked from Settings)
│
├── LOG (/log) -- "Who came and when"
│   ├── Presence log entries grouped by day
│   │   ├── Each entry: who, direction (arrived/left), camera, time
│   │   ├── Filter by person, camera, date range
│   │   └── Last-seen sidebar for each person
│   └── Log types: visits, arrivals, departures
│
├── REPORT (/report)
│   ├── Weekly report with charts
│   │   ├── Visits per day (bar chart)
│   │   ├── Visits per hour (line chart)
│   │   ├── People breakdown
│   │   └── Packages section
│   ├── Heatmap tab (#heat) -- where people walk most
│   └── Weekly push notification summary
│
├── STRANGERS (/strangers)
│   ├── Grouped recurring unknown faces
│   │   ├── Each group: photos, count of appearances
│   │   └── "Name this person" button -> assigns name
│   ├── Hidden strangers (dismissed)
│   └── Auto-recheck when photo library changes
│
├── PLATES (/plates)
│   ├── Known plates list (saved with names)
│   │   ├── Each: plate number, associated name
│   │   └── Delete button per entry
│   └── Seen plates log (all detected plates, chronological)
│
├── ZONES (/zones)
│   ├── Per-camera zone editor
│   │   ├── Camera selector dropdown
│   │   ├── Live picture overlay with drawing canvas
│   │   └── Zone types: ignore, trigger, house, street, parking, package
│   └── Visual zone legend
│
├── SETTINGS (/settings) -- "Settings" tab on mobile nav
│   ├── Arming schedule (armed/disarmed/schedule mode)
│   │   ├── From/to time inputs
│   │   └── Loitering detection seconds setting
│   ├── Cameras management
│   │   ├── Up to 4 camera slots
│   │   ├── Each: name, RTSP URL, detection substream
│   │   ├── "Find" button (network scan + ONVIF)
│   │   └── Test picture per camera
│   ├── Off-site copies (/settings#offsite)
│   │   ├── Service selection (iCloud, Google Drive, OneDrive, Dropbox, B2, S3, NAS)
│   │   ├── Connection settings per service
│   │   ├── Retention & speed limit
│   │   └── Test connection / Run now buttons
│   ├── Updates (/settings#updates)
│   │   ├── Current version display
│   │   ├── "Update now" button (GitHub-based)
│   │   └── Repository settings (repo, folder, branch, token)
│   ├── Storage (/settings#storage)
│   │   ├── Keep clips duration setting
│   │   ├── Free space target
│   │   └── Move recordings to another disk/share
│   ├── Image processing (/settings#processing)
│   │   ├── GPU enable/disable toggle
│   │   └── Per-model status table (what runs on CPU vs GPU)
│   ├── Home Assistant (/settings#homeassistant)
│   │   ├── MQTT broker settings (IP, user, password)
│   │   └── Webhook URL setting
│   ├── Network / Security
│   │   ├── No-password access on LAN toggle
│   │   └── Trusted networks list
│   └── Home Deck integration (/settings#homedeck)
│       ├── Make link key button
│       └── Sync status display
│
├── STUDIO (/studio) -- Layout editor
│   ├── Dashboard card order (drag to reorder)
│   ├── Default page selection on login
│   ├── Camera setup wizard (multi-VLAN support)
│   └── Discover cameras across VLANs
│
├── FEATURE REQUESTS (/requests)
│   ├── Submit new feature request
│   │   ├── Title input
│   │   ├── Description textarea
│   │   └── Optional name field
│   ├── Sent requests list with GitHub issue status
│   └── "Send again" for failed submissions
│
├── HOME ASSISTANT (/homeassistant)
│   ├── Setup guide with step-by-step instructions
│   ├── MQTT auto-discovery info
│   ├── Event entity configuration
│   └── Automation examples
│
├── SHARE (/shares/<name>)
│   ├── Shared blurred clip viewer
│   │   ├── Faces and plates pixelated
│   │   └── Sound removed
│   └── Share link with expiration
│
└── MOBILE NAV (bottom tab bar on /m)
    ├── Home (/m) -- "what needs attention"
    ├── Live (/live)
    ├── Clips (/)
    ├── Search (/search)
    └── Settings (/settings)
```

### 1.3 Navigation Structure Recommendation

| Surface | Pattern | Rationale |
|---------|---------|-----------|
| **Desktop (all pages)** | **Top header + sidebar** | The app has ~15 distinct sections. A persistent left sidebar with icon+label navigation gives quick access to every section while keeping the main content area maximized. Dashboard cards provide secondary discovery. |
| **Mobile (/m)** | **Bottom tab bar (5 tabs)** | Already implemented: Home, Live, Clips, Search, Settings. This is optimal for thumb-reach on phones. The "Home" tab serves as a command center with attention items. |
| **Wall View (/view)** | **Full-screen immersive** | No nav chrome -- designed for tablet/phone mounted as a display. Filter chips at top, swipeable player. |

**Recommended Desktop Navigation (new structure):**

```
+-----------------------------------------------------+
|  camwatch          [Search]    [User] [Settings]   | <- Top header
+----------+------------------------------------------+
| Dashboard|                                          |
| Clips    |     Main content area                    |
| Live     |     (full-width, responsive)             |
| People   |                                          |
| Log      |                                          |
| Report   |                                          |
| Strangers|                                          |
| Plates   |                                          |
| Zones    |                                          |
| Settings | <- Collapsible sidebar                   |
+----------+------------------------------------------+
```

**Why this structure:**
- **Grouped by function**: Monitoring (Dashboard, Live), Content (Clips, Timelapse), Intelligence (People, Strangers, Plates, Log), Analytics (Report), Configuration (Zones, Settings)
- **Progressive disclosure**: Most users only need Dashboard -> Clips -> Settings. Power users navigate deeper.
- **Mobile parity**: Desktop sidebar maps to mobile bottom tabs for the 5 most-used sections.

---

## 2. User Flows

### 2.1 Onboarding & Account Creation Flow

```
+-------------+     +--------------+     +------------------+     +---------------+
| Deploy      |     | First open   |     | Set credentials   |     | Add cameras   |
| Docker      |---->| web UI at    |---->| /dashboard        |---->| Settings ->   |
| stack       |     | :8080        |     |                  |     | Cameras       |
+-------------+     +--------------+     +------------------+     +---------------+
                                              |                            |
                                              v                            v
                                    +------------------+         +---------------+
                                    | No password on   |         | Find cameras  |
                                    | LAN toggle?      |         | (network scan)|
                                    +------------------+         +---------------+
                                              |                            |
                                              v                            v
                                    +------------------+         +---------------+
                                    | Set trusted      |         | Enter RTSP    |
                                    | networks         |         | URL manually  |
                                    +------------------+         +---------------+
                                              |                            |
                                              v                            v
                                    +------------------+         +---------------+
                                    | Configure ntfy   |         | Test picture  |
                                    | topic & login    |         | button        |
                                    +------------------+         +---------------+
                                              |                            |
                                              v                            v
                                    +------------------+         +---------------+
                                    | Set retention &  |         | Enable GPU?   |
                                    | storage path     |         | (optional)    |
                                    +------------------+         +---------------+
                                              |                            |
                                              v                            v
                                    +---------------------------------------+
                                    |          SETUP COMPLETE               |
                                    |   Dashboard shows cameras online,     |
                                    |   recording. Press "Simulate motion"  |
                                    |   to test full chain.               |
                                    +---------------------------------------+
```

**Decision Points:**
- **Credentials required?** If `WEB_PASSWORD` is set in `.env`, show login. Otherwise, LAN-only no-password mode.
- **Camera found via scan?** If "Find" discovers cameras, pre-fill RTSP URL. If not, manual entry.
- **GPU available?** Show GPU setup prompt if NVIDIA/Intel GPU detected.

**Success Path:** User sees Dashboard with live camera feeds and today's stats.

**Edge Cases:**
- No cameras configured -> Dashboard shows "Add your first camera" CTA
- ntfy not configured -> Dashboard shows "Configure push notifications" banner
- Storage path invalid -> Settings shows error with fix instructions

### 2.2 Core Action Flow -- Browsing & Watching Clips

```
+-------------+     +--------------+     +------------------+
| Dashboard   |     | Click "Clips"|    | Clip listing     |
| or nav to   |---->| tab / tile   |---->| (day-grouped)   |
| Clips       |     +--------------+     +------------------+
│              │                              │
│              v                              v
│        +--------------+           +------------------+
│        │ Filter by    │           │ Select clips     │
│        │ person/      │           │ (bulk mode)      │
│        │ vehicle/etc  │           +------------------+
│        +--------------+                    │
│                                             ▼
│                                    +------------------+
│                                    │ Download /       │
│                                    │ Delete selected  │
│                                    +------------------+
│                                             │
│              +------------------------------┤
│              v                              v
│     +---------------+         +------------------+
│     │ Click a clip  |-------->| Clip viewer      │
│     │ (day tile)    │         │                  │
│     +---------------+         │ [Play video]     │
│                               │ [Star/unstar]    │
│                               │ [Share]          │
│                               │ [Delete]         │
│                               │ [Tag faces]      │
│                               +------------------+
│                                        │
│                              +----------┤
│                              v          v
│                     +---------------+  +---------------+
│                     │ Tag face:     │  │ Share:        │
│                     │ "This is X"   │  │ Blurred copy  │
│                     +---------------+  │ ready         │
│                                        +---------------+
```

**Decision Points:**
- **Filter active?** Show filter chips at top of clip listing. Clear filters to show all.
- **Multiple cameras?** Clip picker shows camera selector per day group.
- **Starred clips?** Toggle star -> starred clips never auto-delete, kept forever.

### 2.3 Settings & Profile Management Flow

```
+-------------+     +--------------+     +------------------+
| Dashboard   |     | Click       │    │ Settings page    │
| -> Settings |---->| Settings    │----│ (sectioned)      │
| or nav      │     | tile/tab    │    │                  │
+-------------+     +--------------+     +------------------+
                                              │
                    +-------------------------┤
                    v                         v
           +-----------------+      +------------------+
           │ Arming &        │      │ Cameras          │
           │ Schedule        │      │ (up to 4)        │
           │                 │      │                  │
           │ Armed/Disarmed  │      │ Slot 1: RTSP     │
           │ Schedule mode   │      │ Slot 2-4: Add    │
           │ From -> To time │      │ Find/Test        │
           +-----------------+      +------------------+
                    │                         │
                    v                         v
           +-----------------+      +------------------+
           │ Loitering sec   │      │ Off-site copies  │
           │ setting         │      │ (iCloud, GDrive) │
           +-----------------+      +------------------+
                    │                         │
                    v                         v
           +-----------------+      +------------------+
           │ Trusted         │      │ Retention &      │
           │ networks        │      │ Storage path     │
           +-----------------+      +------------------+
                    │                         │
                    v                         v
           +-----------------+      +------------------+
           │ Image           │      │ Updates          │
           │ Processing      │      │ (check/install)  │
           │ (GPU toggle)    │      +------------------+
           +-----------------+              │
                    │                        ▼
                    v               +------------------+
           +-----------------+     │ Home Assistant   │
           │ Home Deck       │     │ (MQTT + webhook) │
           │ (link key)      │     +------------------+
           +-----------------+              │
                    │                        ▼
                    v               +------------------+
           +-----------------+     │ No-password LAN  │
           │ Feature         │     │ access toggle    │
           │ Requests link   │     +------------------+
           +-----------------+              │
                    │                        ▼
                    v               +------------------+
           +-----------------+     │ Version info     │
           │                 |---->| + changelog      │
           +-----------------+     +------------------+
```

### 2.4 Error Recovery Flow

```
+---------------------------------------------------------------------+
|                      ERROR RECOVERY OVERVIEW                         |
+-------------------+-------------------------------------------------+
| Form Validation   | Show inline error below field                   |
|                   | Red border + red text with specific message     |
|                   | CTA: "Try Again" or "Clear"                     |
+-------------------+-------------------------------------------------+
| Network/Conn      | Toast notification at top of page               |
| Errors            | "Could not reach the camera. Check your        |
|                   |  network and try again."                        |
|                   | CTA: "Retry" (retries once, then shows status) |
+-------------------+-------------------------------------------------+
| Permission        | Modal dialog                                    |
| Denied            | "You need admin access to change this setting." |
|                   | CTA: "OK" or "Contact Admin"                    |
+-------------------+-------------------------------------------------+
| Session Expired   | Redirect to login page                          |
|                   | Toast: "Session expired. Please log in again."  |
|                   | CTA: "Log In"                                   |
+-------------------+-------------------------------------------------+
| Camera Offline    | Red dot on camera tile + alert card             |
|                   | "Camera X is offline - no picture"              |
|                   | CTA: Link to live page for that camera          |
+-------------------+-------------------------------------------------+
| Off-site Upload   | Alert in Settings -> Off-site copies            |
| Failure           | "iCloud upload failed: [error reason]"          |
|                   | CTA: "Test Connection" or "Retry"              |
+-------------------+-------------------------------------------------+
| Update Failed     | Settings -> Updates shows previous version      |
|                   | "Update failed. Reverted to v1.x."             |
|                   | CTA: "Try Again" or "View Logs"                |
+-------------------+-------------------------------------------------+
| Storage Full      | Dashboard stat shows red percentage (>=90%)     |
|                   | "Storage 95% full - clips will be deleted soon."|
|                   | CTA: Link to Settings -> Storage               |
+---------------------------------------------------------------------+
```

---

## 3. Full Screen-by-Screen Breakdown

### 3.1 Dashboard (`/dashboard`)

| Property | Details |
|----------|---------|
| **Purpose** | At-a-glance overview of today's activity, live cameras, and quick navigation to every section |
| **Key UI Elements** | Configurable card grid (stats, search bar, live snapshot, latest event, camera tiles, page navigation tiles, heatmap thumbnail, attention alerts, weather) |
| **Primary Action** | Click any tile to navigate to that section |
| **Secondary Actions** | Toggle arm/disarm button in header; click "Simulate motion" on Live page to test full chain |
| **Navigation Options** | Links to every major section via tiles; bottom nav bar on mobile; Studio link for card reordering |

### 3.2 Clips Listing (`/`)

| Property | Details |
|----------|---------|
| **Purpose** | Browse all recorded clips organized by day, filterable by detected objects/people |
| **Key UI Elements** | Day-grouped timeline; filter chips (person, vehicle, package, etc.); tag chips for custom tags; bulk select checkbox mode; camera picker (multi-camera) |
| **Primary Action** | Click a clip thumbnail to open the clip viewer |
| **Secondary Actions** | Apply/clear filters; toggle bulk select mode; star clips from listing |
| **Navigation Options** | Back to dashboard via header; mobile nav bar; link to starred clips view |

### 3.3 Clip Viewer (`/clip/<day>/<stem>`)

| Property | Details |
|----------|---------|
| **Purpose** | Watch a single recorded event with pre-roll, tag faces, and manage the clip |
| **Key UI Elements** | Video player (MP4 with pre-roll); face tagging overlay; star toggle button; share button; delete button; previous/next navigation; "Play all" from same visit |
| **Primary Action** | Play/watch the video |
| **Secondary Actions** | Star/unstar; tag faces; share blurred copy; delete; play all clips from same visit |
| **Navigation Options** | Previous/next clip buttons; back to clips listing; link to person page if face tagged |

### 3.4 Live View (`/live`)

| Property | Details |
|----------|---------|
| **Purpose** | Watch all cameras live simultaneously and test the alert chain |
| **Key UI Elements** | Multi-camera grid (16:9 tiles); camera name labels with online/offline status dots; "Simulate motion" end-to-end test button; camera picker dropdown (multi-camera) |
| **Primary Action** | Watch live feeds |
| **Secondary Actions** | Click a camera tile to view full-screen; press "Simulate motion" to test push -> clip -> page chain |
| **Navigation Options** | Back to dashboard via header; mobile nav bar; link to wall view |

### 3.5 Wall View (`/view`)

| Property | Details |
|----------|---------|
| **Purpose** | Immersive live + playback experience for tablets and phones mounted as displays |
| **Key UI Elements** | Live picture grid with filter chips at top; swipeable full-screen player for recordings; camera selector overlay |
| **Primary Action** | Swipe between cameras (live) or clips (recordings) |
| **Secondary Actions** | Tap to show/hide controls; long-press a live tile to jump to recent clip from that camera |
| **Navigation Options** | Minimal chrome -- tap to reveal nav; swipe down to exit |

### 3.6 People Library (`/people`)

| Property | Details |
|----------|---------|
| **Purpose** | Manage the face recognition reference library |
| **Key UI Elements** | Grid of person cards (name + photo thumbnail); "Add person" button; Home Deck linked people section (if connected) |
| **Primary Action** | Click a person card to view/manage their photos and clips |
| **Secondary Actions** | Add new person; upload additional photos; delete person |
| **Navigation Options** | Back to dashboard via header; mobile nav bar; link from clip face tagging |

### 3.7 Person Detail (`/people/<name>`)

| Property | Details |
|----------|---------|
| **Purpose** | Manage a specific person's reference photos and view their detected clips |
| **Key UI Elements** | Person name header; photo grid (reference photos); "Upload photo" button; rename input; delete confirmation; clips list where this person was detected |
| **Primary Action** | Upload/add reference photos |
| **Secondary Actions** | Rename person; delete person; click a clip to view it |
| **Navigation Options** | Back to people library; link from any clip where this person appears |

### 3.8 Presence Log (`/log`)

| Property | Details |
|----------|---------|
| **Purpose** | "Who came and when" -- chronological log of arrivals, departures, and visits |
| **Key UI Elements** | Day-grouped entries; each entry shows who (person name or unknown), direction (arrived/left), camera, time; filter by person/camera/date range; last-seen sidebar per person |
| **Primary Action** | Browse the presence log to see who was at home and when |
| **Secondary Actions** | Filter by person, camera, or date range; click an entry to view the associated clip |
| **Navigation Options** | Back to dashboard via header; mobile nav bar (via Clips tab) |

### 3.9 Weekly Report (`/report`)

| Property | Details |
|----------|---------|
| **Purpose** | Analyze weekly activity patterns with charts and heatmaps |
| **Key UI Elements** | Visits per day chart (bar); visits per hour chart (line); people breakdown; packages section; heatmap tab (#heat) showing where people walk most over 7 days |
| **Primary Action** | Review the weekly summary to understand activity patterns |
| **Secondary Actions** | Switch between charts and heatmap tabs; click a data point to see associated clips |
| **Navigation Options** | Back to dashboard via header; mobile nav bar (via Clips tab) |

### 3.10 Strangers (`/strangers`)

| Property | Details |
|----------|---------|
| **Purpose** | Identify recurring unknown faces by assigning names |
| **Key UI Elements** | Grouped cards of recurring unknown faces; each group shows multiple photos and appearance count; "Name this person" button per group; hidden/dismissed strangers section |
| **Primary Action** | Click "Name this person" on a stranger group |
| **Secondary Actions** | Dismiss a stranger (hide from list); click a photo to view the clip where it was detected |
| **Navigation Options** | Back to dashboard via header; mobile nav bar (via Clips tab) |

### 3.11 Plates (`/plates`)

| Property | Details |
|----------|---------|
| **Purpose** | Manage known license plates and view all detected plates |
| **Key UI Elements** | Two sections: "Known plates" (saved with names) and "Seen plates" (chronological log); each entry shows plate number, associated name (if known), camera, time; delete button per known plate |
| **Primary Action** | Save a detected plate as known |
| **Secondary Actions** | Delete a known plate; click a seen plate to view the clip |
| **Navigation Options** | Back to dashboard via header; mobile nav bar (via Clips tab) |

### 3.12 Zones (`/zones`)

| Property | Details |
|----------|---------|
| **Purpose** | Draw detection zones on each camera's live picture |
| **Key UI Elements** | Camera selector dropdown; live picture with drawing canvas overlay; zone type legend (ignore, trigger, house, street, parking, package); visual zone shapes on the image |
| **Primary Action** | Draw a new zone or edit an existing one |
| **Secondary Actions** | Switch cameras to draw zones per camera; delete individual zones; toggle zone visibility |
| **Navigation Options** | Back to dashboard via header; mobile nav bar (via Clips tab) |

### 3.13 Settings (`/settings`)

| Property | Details |
|----------|---------|
| **Purpose** | Configure all CamWatch settings in one place |
| **Key UI Elements** | Sectioned layout with expandable/collapsible sections: Arming schedule, Cameras (up to 4), Off-site copies, Updates, Storage, Image processing (GPU), Home Assistant, Network/Security, Home Deck; each section has its own form inputs and save button |
| **Primary Action** | Save settings changes per section |
| **Secondary Actions** | Expand/collapse sections; test camera connection; check for updates; make Home Deck link key |
| **Navigation Options** | Back to dashboard via header; mobile nav bar (Settings tab) |

### 3.14 Studio (`/studio`)

| Property | Details |
|----------|---------|
| **Purpose** | Customize the dashboard layout and discover cameras across VLANs |
| **Key UI Elements** | Drag-and-drop card reorder interface; default page selector on login; camera setup wizard with multi-VLAN support; discover button for network-wide camera scan |
| **Primary Action** | Reorder dashboard cards to personal preference |
| **Secondary Actions** | Set default landing page; run VLAN camera discovery; apply draft layout changes |
| **Navigation Options** | Back to dashboard via header; link from dashboard "Pages" section |

### 3.15 Timelapse (`/timelapse`)

| Property | Details |
|----------|---------|
| **Purpose** | Watch a condensed version of the entire day plus highlights reel |
| **Key UI Elements** | Daily timelapse player; highlights reel (every event in quick succession); "Build new timelapse" button; date selector for past days |
| **Primary Action** | Play the daily timelapse or highlights reel |
| **Secondary Actions** | Build a new timelapse for today; select a different day to view its timelapse |
| **Navigation Options** | Back to dashboard via header; mobile nav bar (via Clips tab) |

### 3.16 Search (`/search`)

| Property | Details |
|----------|---------|
| **Purpose** | Find clips by natural language description using the local CLIP model |
| **Key UI Elements** | Search input with placeholder "white van, person with a dog, red jacket..."; results grid showing matching clips with thumbnails; indexing status indicator |
| **Primary Action** | Type a search query and press Enter |
| **Secondary Actions** | Clear search to show all clips; click a result to open the clip viewer |
| **Navigation Options** | Back to dashboard via header; mobile nav bar (Search tab) |

### 3.17 Home Assistant (`/homeassistant`)

| Property | Details |
|----------|---------|
| **Purpose** | Guide users through Home Assistant integration setup |
| **Key UI Elements** | Step-by-step setup guide; MQTT auto-discovery status; webhook configuration; automation examples with code blocks; copy-to-clipboard buttons for config snippets |
| **Primary Action** | Follow the setup steps to integrate with Home Assistant |
| **Secondary Actions** | Copy MQTT config snippet; copy automation YAML; test connection |
| **Navigation Options** | Back to dashboard via header; link from Settings -> Home Assistant section |

### 3.18 Feature Requests (`/requests`)

| Property | Details |
|----------|---------|
| **Purpose** | Submit feature ideas that become GitHub issues |
| **Key UI Elements** | "Request a feature" form (title, description, optional name); sent requests list with GitHub issue numbers and status; "Send again" button for failed submissions |
| **Primary Action** | Submit a new feature request |
| **Secondary Actions** | View existing submitted requests; retry a failed submission |
| **Navigation Options** | Link from every page footer; back to dashboard via header |

### 3.19 Mobile Home (`/m`)

| Property | Details |
|----------|---------|
| **Purpose** | Phone-optimized command center showing what needs attention |
| **Key UI Elements** | Sticky top bar with arm/disarm toggle; "Needs attention" alert cards (camera offline, unusual visits, packages, strangers, off-site errors, snoozes); swipeable live camera tiles with snooze buttons; today's stats (visits, people seen, weekly count); recent visits list with thumbnails |
| **Primary Action** | Review alerts and take action (snooze, view clip, resume camera) |
| **Secondary Actions** | Toggle arm/disarm; swipe between cameras; tap a visit to view the clip; pull-to-refresh |
| **Navigation Options** | Bottom tab bar: Home, Live, Clips, Search, Settings |

### 3.20 Share Viewer (`/shares/<name>`)

| Property | Details |
|----------|---------|
| **Purpose** | View a shared clip with faces and plates pixelated, sound removed |
| **Key UI Elements** | Video player; share info banner (shared by, date); download button; close button to return to CamWatch |
| **Primary Action** | Watch the shared clip |
| **Secondary Actions** | Download the blurred copy; close viewer |
| **Navigation Options** | Close returns to CamWatch dashboard or external referrer |

---

## 4. Microcopy for Every Screen

### 4.1 Dashboard (`/dashboard`)

| Element | Copy |
|---------|------|
| Page title | `camwatch` (logo text) |
| Arm button (armed) | `Armed` |
| Arm button (disarmed) | `Disarmed` |
| Arm tooltip (schedule mode) | `Schedule {from}-{to}` |
| Stats -- Camera label | `Camera` |
| Stats -- Events today label | `Events today` |
| Stats -- Seen today label | `Seen today` |
| Stats -- Last event label | `Last event` |
| Stats -- Packages label | `Packages` |
| Stats -- Storage label | `Storage` |
| Search placeholder | `Search recordings: white van, person with a dog, red jacket...` |
| Pages tile -- Phone home | Title: `Phone home` · Subtitle: `Made for phones: what needs attention, cameras, recent visits` |
| Pages tile -- Camera view | Title: `Camera view` · Subtitle: `Live picture, recordings, player, tagging` |
| Pages tile -- Clips | Title: `Clips` · Subtitle: `All recordings by day, timeline, filters` |
| Pages tile -- Live | Title: `Live` · Subtitle: `Live video and the test button` |
| Pages tile -- Log | Title: `Log` · Subtitle: `Who came and when, arrived / left` |
| Pages tile -- Weekly report | Title: `Weekly report` · Subtitle: `Visits per day and hour, people, cars, packages` |
| Pages tile -- Heatmap | Title: `Heatmap` · Subtitle: `Where people walk` |
| Pages tile -- Search | Title: `Search` · Subtitle: `Find clips by description` |
| Pages tile -- Timelapse | Title: `Timelapse` · Subtitle: `The day in a minute, highlights reel` |
| Pages tile -- Strangers | Title: `Strangers` · Subtitle: `Unknown faces seen again and again` |
| Pages tile -- People | Title: `People` · Subtitle: `Reference photos for face matching` |
| Pages tile -- Plates | Title: `Plates` · Subtitle: `Known and seen number plates` |
| Pages tile -- Zones | Title: `Zones` · Subtitle: `Ignore, trigger, house/street, parking, package` |
| Pages tile -- Settings | Title: `Settings` · Subtitle: `Arming schedule, loitering` |
| Pages tile -- Starred | Title: `Starred` · Subtitle: `Clips kept forever` |
| Pages tile -- Home Assistant | Title: `Home Assistant` · Subtitle: `Setup guide and automations` |
| Heatmap caption | `Where people walked · last 7 days` |
| Attention heading | `Needs attention` |
| Weather heading | `Outside` |
| Weather no-data | `Home Deck has not sent the weather yet` |

### 4.2 Clips Listing (`/`)

| Element | Copy |
|---------|------|
| Page title | `Clips` |
| Filter placeholder | `Filter clips...` |
| Bulk select mode header | `Select clips to download or delete` |
| Download button (bulk) | `Download selected` |
| Delete button (bulk) | `Delete selected` |
| Confirm delete dialog title | `Delete {N} clips?` |
| Confirm delete dialog body | `This will remove {N} recordings. Starred clips are kept.` |
| Confirm delete CTA | `Delete` |
| Cancel CTA | `Cancel` |

### 4.3 Clip Viewer (`/clip/<day>/<stem>`)

| Element | Copy |
|---------|------|
| Page title | `{Person/Vehicle/Motion} · {time}` |
| Play all button | `Play all` |
| Star button (unstarred) | `Star` |
| Star button (starred) | `Unstar` |
| Share button | `Share` |
| Delete button | `Delete` |
| Confirm delete dialog title | `Delete this clip?` |
| Confirm delete dialog body | `This recording will be removed. If starred, it is kept.` |
| Confirm delete CTA | `Delete` |
| Cancel CTA | `Cancel` |
| Face tag prompt | `Tag face: who is this?` |
| Face tag confirm | `This is {name}` |
| Face tag unknown | `Unknown person` |
| Share success toast | `Blurred copy ready -- share link copied` |

### 4.4 Live View (`/live`)

| Element | Copy |
|---------|------|
| Page title | `Live` |
| Simulate motion button | `Simulate motion` |
| Simulate motion success toast | `Motion simulated -- check your phone for the push` |
| Camera offline label | `{camera} is offline` |
| Camera online indicator | `Online` |
| Test chain description | `Tests the full chain: camera -> alert -> clip -> page` |

### 4.5 Wall View (`/view`)

| Element | Copy |
|---------|------|
| Page title | (no title -- immersive) |
| Filter chip -- All | `All` |
| Filter chip -- People | `People` |
| Filter chip -- Vehicles | `Vehicles` |
| Filter chip -- Packages | `Packages` |
| Snooze button | `Snooze 1h` |
| Snoozed indicator | `until {time}` |

### 4.6 People Library (`/people`)

| Element | Copy |
|---------|------|
| Page title | `People` |
| Add person button | `Add person` |
| Person card label | `{name}` |
| Upload photo placeholder | `Upload a clear face photo...` |
| Upload accepted formats | `JPG, PNG, or WebP -- 3-10 photos per person recommended` |

### 4.7 Person Detail (`/people/<name>`)

| Element | Copy |
|---------|------|
| Page title | `{name}` |
| Upload photo button | `Upload photo` |
| Rename input placeholder | `New name...` |
| Rename save button | `Save name` |
| Delete person button | `Delete {name}` |
| Confirm delete dialog title | `Delete {name}?` |
| Confirm delete dialog body | `This person and all their reference photos will be removed. Clips tagged with this name stay.` |
| Confirm delete CTA | `Delete` |
| Cancel CTA | `Cancel` |

### 4.8 Presence Log (`/log`)

| Element | Copy |
|---------|------|
| Page title | `Log` |
| Subtitle | `Who came and when, arrived / left` |
| Filter -- Person placeholder | `Filter by person...` |
| Filter -- Camera placeholder | `Filter by camera...` |
| Date range start label | `From` |
| Date range end label | `To` |
| Apply filter button | `Apply` |
| Clear filter button | `Clear` |

### 4.9 Weekly Report (`/report`)

| Element | Copy |
|---------|------|
| Page title | `Weekly report` |
| Tab -- Chart | `Chart` |
| Tab -- Heatmap | `Heatmap` |
| Visits per day chart label | `Visits per day` |
| Visits per hour chart label | `Visits per hour` |
| People breakdown title | `People this week` |
| Packages section title | `Packages` |
| Weekly push subtitle | `Sent weekly by default` |

### 4.10 Strangers (`/strangers`)

| Element | Copy |
|---------|------|
| Page title | `Strangers` |
| Subtitle | `Unknown faces seen again and again` |
| Name this person button | `Name this person` |
| Name input placeholder | `Enter a name...` |
| Name confirm button | `Save name` |
| Dismiss stranger button | `Dismiss` |
| Hidden section title | `Hidden strangers` |

### 4.11 Plates (`/plates`)

| Element | Copy |
|---------|------|
| Page title | `Plates` |
| Subtitle | `Known and seen number plates` |
| Known plates heading | `Known plates` |
| Seen plates heading | `Seen plates` |
| Save plate button | `Save as known` |
| Plate name placeholder | `Name for this vehicle...` |
| Delete known plate CTA | `Delete` |

### 4.12 Zones (`/zones`)

| Element | Copy |
|---------|------|
| Page title | `Zones` |
| Camera selector label | `Camera` |
| Zone type -- Ignore | `Ignore (no alerts)` |
| Zone type -- Trigger | `Trigger (alerts say "person at door")` |
| Zone type -- House | `House (arrived home)` |
| Zone type -- Street | `Street (left home)` |
| Zone type -- Parking | `Parking (car arrived/left)` |
| Zone type -- Package | `Package (delivered/picked up)` |
| Draw new zone button | `Draw new zone` |
| Delete zone CTA | `Delete zone` |
| Save zones button | `Save zones` |

### 4.13 Settings (`/settings`)

| Element | Copy |
|---------|------|
| Page title | `Settings` |
| Section -- Arming schedule | `Arming schedule` |
| Mode -- Armed label | `Armed (always)` |
| Mode -- Disarmed label | `Disarmed (never)` |
| Mode -- Schedule label | `Schedule (from -> to)` |
| From time label | `From` |
| To time label | `To` |
| Loitering seconds label | `Loitering detection (seconds)` |
| Section -- Cameras | `Cameras` |
| Find cameras button | `Find` |
| Test picture button | `Test picture` |
| Camera name placeholder | `Camera name...` |
| RTSP URL placeholder | `rtsp://user:pass@host/stream` |
| Detection substream label | `Detection substream (optional)` |
| Section -- Off-site copies | `Off-site copies` |
| Service selector placeholder | `Select a service...` |
| Test connection button | `Test connection` |
| Run now button | `Run now` |
| Disconnect button | `Disconnect` |
| Retention label | `Retention period` |
| Speed limit label | `Speed limit (MB/s)` |
| Section -- Updates | `Updates` |
| Current version label | `Current version` |
| Update available toast | `Update available!` |
| Update now button | `Update now` |
| Where updates come from heading | `Where updates come from` |
| Repository folder placeholder | `owner/repo` |
| Branch placeholder | `main` |
| Token placeholder | `ghp_xxxxxxxxxxxx (optional)` |
| How to make the key link | `How to make the key ->` |
| Section -- Storage | `Storage` |
| Keep clips label | `Keep clips for` |
| Free space target label | `Free space target` |
| Move recordings heading | `Where recordings go` |
| New path placeholder | `/new/path/to/recordings` |
| Move button | `Move` |
| Section -- Image processing | `Image processing` |
| GPU toggle label | `Use the GPU when the server has one` |
| Model status heading | `Model status` |
| CPU label | `CPU` |
| GPU label | `GPU` |
| Section -- Home Assistant | `Home Assistant` |
| MQTT broker IP label | `MQTT broker address` |
| MQTT user label | `MQTT username` |
| MQTT password label | `MQTT password` |
| Webhook URL label | `Webhook URL` |
| Section -- Network / Security | `Network & security` |
| No-password LAN toggle | `No-password access on the home network` |
| Trusted networks heading | `Trusted networks` |
| Add network button | `Add network` |
| Section -- Home Deck | `Home Deck` |
| Make link key button | `Make a link key` |
| Sync status label | `Sync status: {status}` |

### 4.14 Studio (`/studio`)

| Element | Copy |
|---------|------|
| Page title | `Studio` |
| Section -- Dashboard layout | `Dashboard layout` |
| Layout instruction | `Drag cards to reorder them. Your order determines what you see.` |
| Default page heading | `Default page on login` |
| Camera setup heading | `Camera setup` |
| Discover cameras button | `Discover cameras` |
| VLAN selector label | `VLAN (optional)` |
| Apply changes button | `Apply changes` |
| Undo changes button | `Undo` |

### 4.15 Timelapse (`/timelapse`)

| Element | Copy |
|---------|------|
| Page title | `Timelapse` |
| Subtitle | `The day in a minute, highlights reel` |
| Build new timelapse button | `Build new timelapse` |
| Date selector label | `Select a date` |
| Building toast | `Building timelapse...` |
| Built toast | `Timelapse ready` |

### 4.16 Search (`/search`)

| Element | Copy |
|---------|------|
| Page title | `Search` |
| Search input placeholder | `Search recordings: white van, person with a dog, red jacket...` |
| Search button | `Search` |
| Indexing status -- Indexed | `Indexed · {N} clips ready` |
| Indexing status -- Indexing | `Indexing in progress...` |
| No results message | `No clips match "{query}"` |
| Try again suggestion | `Try different keywords or check the indexing status.` |

### 4.17 Home Assistant (`/homeassistant`)

| Element | Copy |
|---------|------|
| Page title | `Home Assistant` |
| Subtitle | `Setup guide and automations` |
| Step 1 heading | `Step 1: Enable MQTT auto-discovery` |
| Step 2 heading | `Step 2: Configure the webhook` |
| Step 3 heading | `Step 3: Add automation examples` |
| Copy config button | `Copy to clipboard` |
| Copied toast | `Copied!` |

### 4.18 Feature Requests (`/requests`)

| Element | Copy |
|---------|------|
| Page title | `Request a feature` |
| Subtitle | `Send your idea to GitHub as an issue` |
| Title label | `Title` |
| Title placeholder | `Brief description of your idea...` |
| Description label | `Description` |
| Description placeholder | `Tell us more about what you'd like to see...` |
| Name label | `Your name (optional)` |
| Submit button | `Submit request` |
| Sent status -- Success | `Submitted as issue #{number}` |
| Sent status -- Failed | `Failed to submit. {error}` |
| Send again button | `Send again` |

### 4.19 Mobile Home (`/m`)

| Element | Copy |
|---------|------|
| Page title | `camwatch` |
| Subtitle (armed) | `pushes on` |
| Subtitle (disarmed) | `recording, no pushes` |
| Subtitle (schedule) | `schedule {from}-{to}` |
| Arm button (armed) | `Armed` |
| Arm button (disarmed) | `Disarmed` |
| Needs attention heading | `Needs attention` |
| All quiet message | `All quiet -- {N} camera(s) online` |
| Today heading | `Today` |
| Recent heading | `Recent` |
| Empty recent state | `Nothing recorded today or yesterday.` |

### 4.20 Share Viewer (`/shares/<name>`)

| Element | Copy |
|---------|------|
| Page title | `Shared clip` |
| Shared by label | `Shared by {name}` |
| Date shared label | `{date}` |
| Download button | `Download blurred copy` |
| Close button | `Close` |

---

## 5. Error States

### 5.1 Form Validation Errors

| Scenario | Headline | Body Copy | CTA Label |
|----------|----------|-----------|-----------|
| Empty required field | `This field is required` | Please fill in this field before saving. | `OK` |
| Invalid RTSP URL format | `Invalid stream address` | Check the URL format: rtsp://user:pass@host/stream | `Try Again` |
| Time from >= time to (schedule) | `From time must be before To time` | Adjust the schedule times so From is earlier than To. | `OK` |
| Loitering seconds out of range | `Invalid duration` | Enter a value between 0 and 3600 seconds. | `Try Again` |
| Duplicate camera name | `Camera name already exists` | Each camera needs a unique name. Choose another. | `Try Again` |
| Plate number too long | `Plate too long` | Keep the plate under 20 characters. | `OK` |

### 5.2 Network / Connection Errors

| Scenario | Headline | Body Copy | CTA Label |
|----------|----------|-----------|-----------|
| Camera offline (detected) | `{camera} is offline` | No picture from this camera. Check the cable and power. | `View camera` |
| ntfy connection failed | `Push notifications not reaching you` | Check your ntfy topic, server URL, and login in Settings. | `Go to Settings` |
| API unreachable (general) | `Could not reach camwatch` | The service may be restarting. Try again in a moment. | `Retry` |
| Home Deck sync failed | `Home Deck sync failed` | Check that the link key is correct and Home Deck is running. | `Go to Settings` |

### 5.3 Permission Errors

| Scenario | Headline | Body Copy | CTA Label |
|----------|----------|-----------|-----------|
| No password mode, wrong network | `Access denied from this network` | Only trusted networks can access camwatch without a password. | `OK` |
| Settings change requires login | `Log in to save changes` | You're viewing in no-password mode. Log in to edit settings. | `Log In` |

### 5.4 Session Errors

| Scenario | Headline | Body Copy | CTA Label |
|----------|----------|-----------|-----------|
| Session expired | `Session expired` | Your session has ended. Please log in again. | `Log In` |
| Password incorrect (3 attempts) | `Too many failed attempts` | Wait 30 seconds and try again, or check your password. | `Try Again` |

### 5.5 Storage Errors

| Scenario | Headline | Body Copy | CTA Label |
|----------|----------|-----------|-----------|
| Storage >= 90% full | `Storage nearly full` | {pct}% used -- clips will be deleted soon to free space. Adjust retention in Settings -> Storage. | `Go to Storage` |
| Move recordings failed | `Move failed` | The new path could not be reached. Check permissions and try again. | `Try Again` |
| Disk write error | `Could not save clip` | The disk may be full or disconnected. Check storage in Settings. | `Check Storage` |

### 5.6 Update Errors

| Scenario | Headline | Body Copy | CTA Label |
|----------|----------|-----------|-----------|
| Update failed (rollback) | `Update failed -- reverted` | The new version did not start. Reverted to {old_version}. Check logs for details. | `Try Again` |
| GitHub rate limited | `GitHub rate limit reached` | Too many update checks. Try again later or add an access key in Settings -> Updates. | `OK` |
| Invalid repo/folder format | `Invalid repository path` | Enter the path as owner/repo (e.g., johanhoel/amplitude). | `Try Again` |

### 5.7 Off-site Upload Errors

| Scenario | Headline | Body Copy | CTA Label |
|----------|----------|-----------|-----------|
| iCloud connection failed | `iCloud connection failed` | Check your share path and credentials in Settings -> Off-site copies. | `Go to Settings` |
| Google Drive OAuth expired | `Google Drive session expired` | Reconnect your Google account to resume uploads. | `Reconnect` |
| S3 upload timeout | `Upload timed out` | The connection may be slow. Check speed limit in Settings -> Off-site copies. | `Try Again` |

### 5.8 Search Errors

| Scenario | Headline | Body Copy | CTA Label |
|----------|----------|-----------|-----------|
| CLIP model not indexed yet | `Search is indexing` | The search model needs to index your clips first. This may take a few minutes. | `Check Status` |
| Search query too long | `Query too long` | Keep your search under 200 characters. | `OK` |

---

## 6. Empty States

### 6.1 First-Time User -- No Cameras Configured

| Element | Copy |
|---------|------|
| Illustration description | A simple line-art illustration of a camera with a dashed outline, suggesting "add me" |
| Headline | `Add your first camera` |
| Supporting copy | `Go to Settings -> Cameras and enter an RTSP stream address. CamWatch will start recording within seconds.` |
| CTA label | `Go to Cameras` |

### 6.2 No Clips Recorded Yet

| Element | Copy |
|---------|------|
| Illustration description | A film strip with a single empty frame, soft gray tones |
| Headline | `No clips yet` |
| Supporting copy | `Clips appear here once motion or an object is detected. Try simulating motion on the Live page.` |
| CTA label | `Go to Live` |

### 6.3 No People in Library

| Element | Copy |
|---------|------|
| Illustration description | A silhouette of a person with a plus icon, minimal line art |
| Headline | `Add people for face recognition` |
| Supporting copy | `Upload 3-10 clear face photos per person. CamWatch will recognize them in future clips.` |
| CTA label | `Add Person` |

### 6.4 No Strangers Detected

| Element | Copy |
|---------|------|
| Illustration description | A question mark inside a circle, soft gray |
| Headline | `No recurring strangers yet` |
| Supporting copy | `Unknown faces that appear in multiple clips will be grouped here so you can name them once.` |
| CTA label | (none -- informational) |

### 6.5 No Known Plates Saved

| Element | Copy |
|---------|------|
| Illustration description | A simplified license plate outline with a star icon |
| Headline | `Save known plates` |
| Supporting copy | `Detected plates appear below. Save the ones you recognize to get quiet push notifications for familiar vehicles.` |
| CTA label | (none -- informational) |

### 6.6 No Zones Drawn

| Element | Copy |
|---------|------|
| Illustration description | A camera view rectangle with dashed zone outlines, minimal line art |
| Headline | `Draw detection zones` |
| Supporting copy | `Click on the live picture to draw areas that trigger alerts, ignore motion, or detect arrivals.` |
| CTA label | `Start Drawing` |

### 6.7 Zero-Result Search / Filter

| Element | Copy |
|---------|------|
| Illustration description | A magnifying glass with an empty search result area |
| Headline | `No results for "{query}"` |
| Supporting copy | `Try different keywords, check spelling, or clear your filters to see all clips.` |
| CTA label | `Clear Filters` |

### 6.8 No Recent Visits (Today & Yesterday)

| Element | Copy |
|---------|------|
| Illustration description | A calendar page with no events marked |
| Headline | `Nothing recorded today or yesterday.` |
| Supporting copy | `Visits appear here once motion is detected. Check your camera connection and zones.` |
| CTA label | `Check Camera` |

### 6.9 No Feature Requests Submitted

| Element | Copy |
|---------|------|
| Illustration description | A lightbulb icon with a plus sign, minimal line art |
| Headline | `No feature requests yet` |
| Supporting copy | `Have an idea? Submit it and it will become a GitHub issue for the CamWatch team to review.` |
| CTA label | `Request a Feature` |

### 6.10 No Home Deck Connected

| Element | Copy |
|---------|------|
| Illustration description | Two overlapping squares with an arrow between them, minimal line art |
| Headline | `Connect to Home Deck` |
| Supporting copy | `Link CamWatch to your Home Deck Studio for a unified dashboard. Click "Make a link key" below.` |
| CTA label | `Make Link Key` |

---

## 7. Loading & Transition States

### 7.1 Dashboard Initial Load

| Element | Description |
|---------|-------------|
| Loading state | Skeleton screens for each card placeholder -- gray rounded rectangles with shimmer animation matching the card layout |
| Loading copy | None (skeleton is sufficient) |
| Transition after load | Cards fade in sequentially (staggered 100ms apart) |

### 7.2 Mobile Home -- Status Polling

| Element | Description |
|---------|-------------|
| Loading state | Skeleton cards for attention items; skeleton stat boxes; skeleton visit list rows |
| Loading copy | Subtitle shows `loading...` in the top bar |
| Transition after load | Content fades in; toast appears if there are attention items |

### 7.3 Clip Viewer -- Video Load

| Element | Description |
|---------|-------------|
| Loading state | Black placeholder with centered spinner |
| Loading copy | `Loading clip...` |
| Transition after load | Video plays automatically when ready; toast shows if pre-roll is available |

### 7.4 Settings -- Save Confirmation

| Element | Description |
|---------|-------------|
| Success state | Toast notification at bottom of screen |
| Success copy | `Settings saved` |
| Duration | 2 seconds, then auto-dismiss |
| Error state | Red-bordered section with inline error message |
| Error copy | `{section}: {error_message}` |

### 7.5 Camera "Find" Scan

| Element | Description |
|---------|-------------|
| Loading state | Spinner overlay on the camera list area |
| Loading copy | `Scanning network for cameras...` |
| Transition after success | Discovered cameras appear as pre-filled entries in the form |
| Transition after timeout | Toast: `No cameras found. Enter an RTSP address manually.` |

### 7.6 Off-site Upload -- Test Connection

| Element | Description |
|---------|-------------|
| Loading state | Button shows spinner, text changes to `Testing...` |
| Success state | Green checkmark icon appears next to connection status; toast: `Connection successful` |
| Error state | Red X icon; inline error below the test button |

### 7.7 Update Check / Install

| Element | Description |
|---------|-------------|
| Loading state (check) | Button text changes to `Checking...`, spinner in button |
| Update available | Green banner at top of Settings -> Updates section: `Update v{version} is available` with "Update now" CTA |
| Installing | Full-screen overlay with spinner and copy: `Updating camwatch... Do not close this page.` |
| Success | Toast: `Updated to v{version}`; page reloads automatically after 2 seconds |
| Failure | Red banner: `Update failed. Reverted to {old_version}.` with "Try Again" CTA |

### 7.8 Timelapse Build

| Element | Description |
|---------|-------------|
| Loading state | Button shows spinner, text changes to `Building...` |
| Success toast | `Timelapse ready!` |
| Error toast | `Could not build timelapse. Check storage and try again.` |

### 7.9 Face Tagging in Clip Viewer

| Element | Description |
|---------|-------------|
| Loading state (person lookup) | Modal with spinner: `Matching faces...` |
| Success | Person cards appear for matching results; "Unknown person" option always available |
| After confirming tag | Toast: `{name} tagged in this clip` |

### 7.10 Share Link Generation

| Element | Description |
|---------|-------------|
| Loading state | Button shows spinner, text changes to `Preparing...` |
| Success toast | `Blurred copy ready -- share link copied` |
| Error toast | `Could not prepare the shared clip. Try again.` |

---

## 8. Structural Recommendations

### 8.1 Navigation Pattern Recommendation

**Current state:** CamWatch uses a tile-based dashboard with direct URL routes for each section, plus a bottom tab bar on mobile (`/m`). This works well but has room for improvement.

**Recommendation: Implement a persistent sidebar on desktop + keep the mobile bottom nav.**

| Aspect | Current | Recommended |
|--------|---------|-------------|
| Desktop nav | Tile grid on dashboard only; direct URLs everywhere | Persistent left sidebar with icon+label navigation, always visible |
| Mobile nav | Bottom tab bar (5 tabs) -- already optimal | Keep as-is |
| Wall view | Full-screen immersive, no chrome | Keep as-is |

**Why a sidebar:**
- The app has ~15 distinct sections. Tiles on the dashboard require two clicks to reach most sections.
- A sidebar provides one-click access to every section from any page.
- It scales better if new sections are added (e.g., alerts history, notifications center).
- It mirrors the mobile bottom nav structure: both surfaces show the 5-7 primary destinations always visible.

**Proposed sidebar grouping:**
```
Monitoring    -> Dashboard, Live, Wall View
Content       -> Clips, Timelapse, Starred
Intelligence  -> People, Strangers, Plates, Log
Analytics     -> Report, Search
Configuration -> Zones, Settings, Studio
```

### 8.2 Screens That Might Cause Confusion or Drop-off

| Screen | Issue | Recommendation |
|--------|-------|----------------|
| **Dashboard** | Too many tiles can overwhelm first-time users; the card order is configurable but there's no guidance on what to configure | Add a "guided tour" overlay on first visit that highlights: (1) live camera tile, (2) arm/disarm toggle, (3) Settings link. After tour completes, collapse the pages section by default. |
| **Settings** | All settings in one page with many sections; users may not find what they need | Add a search/filter bar at the top of Settings: "Search settings..." that highlights matching sections. Group related items more explicitly with visual dividers. |
| **Zones** | Drawing zones on a live picture requires understanding zone types; first-time users may draw random shapes without purpose | Add an interactive tutorial mode: click "Draw new zone" -> show animated example of drawing an ignore zone -> let user try -> save. |
| **Strangers** | Users may not understand why strangers exist or what to do with them | Add a tooltip on the Strangers tile in Dashboard: "Unknown faces seen multiple times -- name them once and they'll be recognized forever." |
| **Clips listing** | Day-grouped timeline can feel overwhelming with many clips per day | Add a default filter (e.g., "People only") that users can clear. Show clip count per day group to set expectations. |

### 8.3 Flows That Could Be Simplified or Merged

| Current Flow | Issue | Recommendation |
|-------------|-------|----------------|
| **Settings -> Cameras** has separate sections for each camera slot, plus "Find" and "Test picture" per camera | Users may not know which slot corresponds to which physical camera | Add a visual camera layout diagram at the top of Settings -> Cameras showing slots 1-4 with labels. Drag-to-rename slots. |
| **Off-site copies** requires navigating through multiple sub-sections (service selection, connection, retention) | Too many clicks for simple setup | Collapse the off-site flow into a single wizard: step 1 = choose service, step 2 = enter credentials, step 3 = test & save. Show progress indicator. |
| **Feature requests** are submitted from every page footer but go to a separate `/requests` page | Users may forget what they submitted or check status | Add a "My Requests" section in Settings -> Account that shows all submitted requests with their GitHub issue status inline. |
| **Face tagging** requires going into the clip viewer, clicking on the face, then selecting from a list | Three steps to tag one person | On the clip viewer, show a "Quick tag" panel below the video that lists recently detected people (from the library) as one-tap buttons. |

### 8.4 Progressive Disclosure Opportunities

| Area | What to Show First | What to Reveal on Demand |
|------|-------------------|-------------------------|
| **Dashboard** | Stats card, live snapshot, attention alerts | Full page tiles (collapse by default); heatmap thumbnail; weather card |
| **Settings** | Arming schedule, cameras status, storage usage | Advanced options: trusted networks, Home Deck key, update token, GPU per-model table |
| **Clips listing** | Day groups with clip thumbnails and counts | Filter chips, bulk select mode, camera picker |
| **People library** | Person cards with names and photo count | Per-person details (clips list, upload button) -- expand on click |
| **Zones** | Camera selector + live picture | Zone type palette (appears when clicking "Draw new zone") |
| **Report** | Visits per day chart | Hourly breakdown, people breakdown, packages section, heatmap tab |

### 8.5 Accessibility Considerations Per Screen

| Screen | Consideration | Implementation |
|--------|--------------|----------------|
| **Dashboard** | Keyboard navigation between cards | Add `tabindex="0"` and arrow-key navigation between tiles; visible focus ring (already has `outline: 3px solid var(--accent)`) |
| **Dashboard** | Screen reader for dynamic content | Use `aria-live="polite"` on stat values that update every 30 seconds |
| **Clips listing** | Filter chips are interactive | Ensure each chip is a `<button>` with `aria-pressed` state; announce filter changes via `aria-live` |
| **Clip viewer** | Video player accessibility | Include `<track>` for captions (when available); keyboard controls (space=play/pause, left/right=seek) |
| **Zones** | Drawing canvas on live picture | Provide a "List zones" toggle that shows zone names as clickable list items for keyboard/screen reader users |
| **Settings** | Many form inputs | Every input has an associated `<label>`; required fields marked with `aria-required="true"` and visual asterisk |
| **Mobile home** | Touch targets on small screens | All interactive elements >= 44x44px (already meets this via min-height: 44px on arm button) |
| **All screens** | Color contrast | Dark theme uses `var(--ink)` on `var(--bg)` -- verify WCAG AA contrast ratio (>= 4.5:1 for body text) |
| **All screens** | Reduced motion preference | Already implemented via `@media (prefers-reduced-motion: reduce)` in CSS |
| **Wall view** | Swipeable player accessibility | Provide arrow key navigation as alternative to swipe; announce current camera/clip name on transition |

### 8.6 Additional Recommendations

1. **Add a global search shortcut**: Press `Ctrl+K` (or `Cmd+K` on Mac) from any page to open a command palette that lets users jump to any section, search clips, or run quick actions (arm/disarm, snooze camera).

2. **Implement a notifications center**: Currently alerts appear inline on the dashboard and mobile home. A dedicated notifications panel (accessible via bell icon in header) would let users review historical alerts, mark them as read, and manage notification preferences per camera.

3. **Add a "What's new" changelog**: Settings -> Updates already shows version info. Add a collapsible changelog section that highlights what changed in the current version (new features, bug fixes).

4. **Consider a compact mode for Dashboard**: Power users who use CamWatch daily may prefer fewer cards visible. Add a "Compact" toggle that hides the pages tile grid and shows only stats + live snapshot.

5. **PWA install prompt**: The app already has a manifest.webmanifest and service worker. Add an install banner on first visit (after 30 seconds) encouraging users to install as a standalone app, especially for wall view use cases.

6. **Multi-language support**: The current UI is English-only. Structure all copy in external JSON files (not inline HTML) to enable future i18n without template changes.

---

## Appendix A: Design Tokens Reference

| Token | Value | Usage |
|-------|-------|-------|
| `--bg` | `#0d1117` | Page background |
| `--card` | `#161b22` | Card backgrounds |
| `--card-hi` | `#1c2333` | Elevated card / hover state |
| `--ink` | `#e6edf3` | Primary text |
| `--mute` | `#8b949e` | Secondary text, labels |
| `--line` | `#30363d` | Borders, dividers |
| `--accent` | `#38bdf8` | Primary action color |
| `--ok` | `#22c55e` | Success / online status |
| `--warn` | `#f59e0b` | Warning status |
| `--bad` | `#ef4444` | Error / offline status |
| `--r` | `8px` | Standard border radius |
| `--r-sm` | `4px` | Small border radius |
| `--tab` | `56px` | Mobile bottom nav height |

## Appendix B: Icon Inventory (iconfont class names)

| Icon Class | Used On |
|-----------|---------|
| `icon-home` | Dashboard tile, mobile nav Home tab |
| `icon-film` | Clips tile, mobile nav Clips tab |
| `icon-antenna` | Live tile |
| `icon-phone` | Phone home tile, live camera label |
| `icon-list` | Log tile |
| `icon-chart` | Report tile |
| `icon-fire` | Heatmap tile |
| `icon-search` | Search tile, mobile nav Search tab |
| `icon-refresh` | Timelapse tile |
| `icon-question` | Strangers tile |
| `icon-person` | People tile, strangers alert icon |
| `icon-car` | Plates tile |
| `icon-map` | Zones tile |
| `icon-gear` | Settings tile, mobile nav Settings tab |
| `icon-star` | Starred tile |
| `icon-shield` | Arm button (armed state) |
| `icon-bell-off` | Arm button (disarmed state) |
| `icon-sleep` | Snooze buttons |
| `icon-dot` | Online camera indicator |
| `icon-video` | Live mobile nav tab |
| `icon-package` | Package alerts |
| `icon-cloud` | Off-site upload alerts |
| `icon-link` | Visit link tag |

---

*Document generated 2026-10-31. This specification maps directly to the current CamWatch codebase routes and templates in [amplitude/CamWatch/app/](https://github.com/johanhoel/Amplitude/tree/main/CamWatch/app).*
