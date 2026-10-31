# CamWatch — Next Level Plan

**Version:** 1.0 · **Date:** 2026-10-31
**Scope:** Architecture, features, migration path, and implementation phases for taking CamWatch from a single-camera self-hosted recorder to a multi-user, multi-camera surveillance platform.

---

## Executive Summary

CamWatch is currently a well-built, single-user, up-to-4-camera self-hosted surveillance system with face recognition, plate reading, zones, push notifications, and Home Assistant integration. The codebase (~10K lines of Python) is clean, functional, and Docker-native.

**The next level means:**
1. **Unlimited cameras** — from 4 to any number, with shared detection resources
2. **Multi-user with roles** — admin, viewer, operator accounts with audit log
3. **Live streaming** — real-time WebRTC/RTSP live view instead of snapshot polling
4. **Proper API + WebSocket** — REST API for external integrations, real-time push to clients
5. **Event-driven alert rules engine** — complex conditions across cameras/zones/times
6. **Mobile app** — native-feeling PWA with FCM/APNs push, offline support
7. **Camera health monitoring** — tamper, blur, IR failure, coverage analysis
8. **AI enhancements** — person re-ID across cameras, activity heatmaps, object counting

This plan is organized into **4 phases**, each building on the previous one, with estimated effort and dependencies clearly mapped.

---

## Current State Analysis

### What Works Well (keep these)
| Area | Strength |
|------|----------|
| Detection pipeline | Pixel motion → YOLO confirmation → event stitching is solid |
| Face recognition | Offline SFace embeddings, library caching, stranger clustering |
| Number plates | fast-alpr integration with known plate matching |
| Zones system | Polygon-based ignore/trigger/house/street/parking/package zones |
| Presence log | MariaDB visits table with arrived/left direction inference |
| Push notifications | ntfy with action buttons (Open, Star, Snooze) |
| Home Assistant | MQTT auto-discovery + webhook integration |
| Off-site storage | rclone with encryption to 6+ cloud providers |
| Search | CLIP model for natural language clip search |
| Timelapse | Daily timelapse + highlights reel generation |
| Docker architecture | Clean separation of recorder/facematch/presence/webui/offsite |

### What Needs Work (constraints)
| Area | Current Limitation | Impact |
|------|-------------------|--------|
| Camera count | Hardcoded 4 slots in docker-compose.yml | Limits multi-property users |
| Live view | Snapshot polling at ~5fps via /live.jpg | No audio, no real-time feel |
| Auth model | Single WEB_PASSWORD or LAN-only | No team/family sharing |
| Frontend | Inline Jinja2 templates in webui.py (~4000 lines) | Hard to maintain, no component reuse |
| API | Flask routes mix HTML + JSON | No clean REST boundary |
| Real-time | Polling every 30-60s for status/visits | Stale data, wasted bandwidth |
| Alert rules | Simple armed/disarmed/schedule per camera | No cross-camera or time-based logic |
| Mobile | Static HTML page (/m) with JS fetch polling | No push, no offline, no native feel |
| Camera health | Online/offline + recording stalled only | Misses tamper, blur, IR failure, coverage gaps |
| Resources | One YOLO model per camera (4 copies in memory) | CPU-bound at 4 cameras on modest hardware |

---

## Phase 1: Foundation — API, Live Streaming, Multi-Camera

**Goal:** Remove the 4-camera limit, add real live streaming, and create a proper API layer. This phase unlocks everything else.

### 1.1 Unlimited Camera Support

**Changes needed:**
- Replace hardcoded `recorder` through `recorder-4` in docker-compose.yml with a **dynamic service launcher**
- Implement a **camera registry** in settings.json that stores camera configs and auto-spawns recorder containers via Docker API (or a sidecar process)
- Shared detection model loading: instead of each recorder loading YOLO independently, use a **shared detector service** that multiple recorders query

**Implementation:**
```
┌─────────────────────────────────────────────┐
│  Camera Manager (new container)              │
│  - Watches settings.json for camera changes   │
│  - Spawns/recycles recorder containers via    │
│    Docker API (docker run with dynamic labels) │
│  - Maintains /data/cameras.json registry      │
└──────────────┬──────────────────────────────┘
               │ Docker events + settings watch
               ▼
┌─────────────────────────────────────────────┐
│  Shared Detector Service (new container)     │
│  - Loads YOLOv8 once in memory                │
│  - Accepts frame batches via gRPC/HTTP        │
│  - Returns detections for any camera          │
│  - Reduces CPU from ~4× to ~1.5× per camera   │
└──────────────┬──────────────────────────────┘
               │ gRPC detection calls
               ▼
┌─────────────────────────────────────────────┐
│  Recorder N (dynamic, any count)             │
│  - ffmpeg segmenter + frame reader            │
│  - Calls shared detector for YOLO             │
│  - Writes clips to /recordings                │
└─────────────────────────────────────────────┘
```

**Effort:** ~2 weeks
**Dependencies:** None (Phase 1 standalone)

### 1.2 Live Streaming with go2rtc

**Changes needed:**
- Add **go2rtc** container to the stack — it provides RTSP, MJPEG, WebRTC, and HLS from any RTSP source with zero extra CPU
- Replace `/live.jpg` polling with a **WebRTC peer connection** for real-time live view
- Keep MJPEG fallback for compatibility

**Implementation:**
```yaml
# docker-compose.yml addition
services:
  go2rtc:
    image: alexeypr/go2rtc:latest
    ports:
      - "1984:1984"   # config API
      - "8554:8554"   # RTSP (optional)
      - "8089:8089/tcp"  # WebRTC
      - "8089:8089/udp"  # WebRTC
    volumes:
      - ${DATA_PATH}:/etc/go2rtc
```

- go2rtc reads RTSP URLs from the camera registry and creates streams automatically
- The web UI uses `RTCPeerConnection` to establish a WebRTC connection for live view
- Fallback: if WebRTC fails, show MJPEG stream at `/live.mjpg` (already exists)

**Frontend change:** Replace the snapshot polling in `/view` and `/live` with a WebRTC video element. Detect WebRTC support; fall back to MJPEG or HLS.

**Effort:** ~1 week
**Dependencies:** Phase 1.1 (camera registry provides RTSP URLs to go2rtc)

### 1.3 REST API Layer

**Changes needed:**
- Create a **FastAPI application** alongside the existing Flask webui
- All JSON endpoints (`/api/status`, `/api/cameras`, `/api/days`, `/api/visits`, `/api/thumb`, `/api/heatmap`, `/api/share/<id>`) move to FastAPI
- Flask webui becomes a thin layer that serves HTML templates and delegates data fetching to the API

**Architecture:**
```
┌─────────────────────┐     ┌──────────────────┐
│  Flask Web UI       │     │  FastAPI REST    │
│  (port 8080)        │     │  (port 8081)     │
│                     │     │                  │
│  Serves HTML/JS     │◄────│  JSON API        │
│  Templates          │     │  /api/status     │
│                     │     │  /api/cameras    │
└─────────────────────┘     │  /api/visits     │
                            │  /api/clips      │
                            │  /api/search     │
                            └────────┬─────────┘
                                     │ shared data layer
                                     ▼
                            ┌──────────────────┐
                            │  /data/*.json    │
                            │  MariaDB         │
                            │  /recordings/    │
                            └──────────────────┘
```

**Key API endpoints to add:**
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/cameras` | GET | List all cameras with status, zones, settings |
| `/api/cameras` | POST | Add a new camera (RTSP URL, name, detection substream) |
| `/api/cameras/{id}` | PUT | Update camera settings |
| `/api/cameras/{id}` | DELETE | Remove a camera |
| `/api/clips` | GET | Paginated clip list with filters (date range, person, vehicle, zone) |
| `/api/clips/{stem}` | GET | Clip metadata + faces + plates + tags |
| `/api/clips/{stem}/stream` | GET | HLS or DASH stream for a clip |
| `/api/visits` | GET | Presence log with pagination and filters |
| `/api/alerts` | GET | Alert history (all pushes sent) |
| `/api/alerts/rules` | GET/POST | CRUD alert rules |
| `/api/users` | GET/POST | User management |
| `/api/users/{id}` | PUT/DELETE | Update/delete user |
| `/api/settings` | GET/PUT | Full settings snapshot (read + write) |
| `/api/events/webhook` | POST | Receive events from external systems |

**Effort:** ~2 weeks
**Dependencies:** None (can run alongside existing Flask app during transition)

### 1.4 WebSocket Support

**Changes needed:**
- Add a **WebSocket server** (FastAPI built-in or separate service) for real-time push to clients
- Clients subscribe to events: camera status changes, new clips, alerts, settings updates
- Replaces the current 30-second polling on `/api/status` and 60-second polling on `/api/visits`

**Implementation:**
```python
# FastAPI WebSocket handler
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    # Subscribe to event types
    async for message in websocket.iter_text():
        msg = json.loads(message)
        if msg["type"] == "subscribe":
            subscriptions[msg["channel"]] = websocket
```

**Client-side change:** Replace `setInterval(loadStatus, 30000)` with WebSocket connection. On reconnect, send a snapshot request to catch up.

**Effort:** ~1 week
**Dependencies:** Phase 1.3 (FastAPI layer)

---

## Phase 2: Multi-User, Alert Rules, Mobile App

**Goal:** Enable team/family sharing, complex alert logic, and a proper mobile experience.

### 2.1 User Management with Roles

**Changes needed:**
- Add **SQLite or PostgreSQL** for user data (separate from MariaDB presence log)
- Implement **JWT-based authentication** alongside existing HTTP Basic auth
- Three roles: `admin`, `operator`, `viewer`

| Permission | Admin | Operator | Viewer |
|-----------|-------|----------|--------|
| View live | ✓ | ✓ | ✓ |
| View clips | ✓ | ✓ | ✓ |
| Delete clips | ✓ | ✓ | ✗ |
| Star/unstar | ✓ | ✓ | ✓ |
| Tag faces | ✓ | ✓ | ✗ |
| Edit zones | ✓ | ✓ | ✗ |
| Manage cameras | ✓ | ✗ | ✗ |
| Manage users | ✓ | ✗ | ✗ |
| Change settings | ✓ | ✓ | ✗ |
| View reports | ✓ | ✓ | ✓ |

**Database schema:**
```sql
CREATE TABLE users (
    id UUID PRIMARY KEY,
    username VARCHAR(64) UNIQUE NOT NULL,
    password_hash VARCHAR(128) NOT NULL,
    role ENUM('admin', 'operator', 'viewer') DEFAULT 'viewer',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE audit_log (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id UUID REFERENCES users(id),
    action VARCHAR(64) NOT NULL,  -- 'login', 'clip_delete', 'zone_edit', etc.
    target VARCHAR(256),          -- clip stem, camera name, setting key
    details JSON,                 -- additional context
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE sessions (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES users(id),
    token VARCHAR(256) UNIQUE NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Migration path:** Existing single-password mode becomes "admin only" mode. Users can enable multi-user from Settings → toggle `multi_user_enabled`. On first login with a password, the user becomes admin automatically.

**Effort:** ~2 weeks
**Dependencies:** Phase 1.3 (FastAPI API layer)

### 2.2 Event-Driven Alert Rules Engine

**Changes needed:**
- Create an **alert rules engine** that evaluates conditions on every new event/clip
- Rules are stored in the database and evaluated by a background worker
- Support complex conditions: time windows, camera zones, object types, person presence, cross-camera correlation

**Rule format (JSON):**
```json
{
  "id": "rule_001",
  "name": "Garden at night",
  "enabled": true,
  "conditions": {
    "cameras": ["garden"],
    "zones": [],
    "objects": ["person"],
    "time_window": {"from": "22:00", "to": "06:00"},
    "days_of_week": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
  },
  "actions": {
    "push_ntfy": true,
    "ha_event": true,
    "webhook_url": "https://hooks.example.com/camwatch"
  },
  "cooldown_seconds": 300
}
```

**Rule evaluation flow:**
```
New event/clip detected
        │
        ▼
┌─────────────────────┐
│  Rule Evaluator     │
│  (background worker) │
└──────────┬──────────┘
           │ For each enabled rule:
           │   1. Check camera match
           │   2. Check zone overlap
           │   3. Check object type match
           │   4. Check time window
           │   5. Check cooldown
           ▼
    Conditions met? → Execute actions
```

**Advanced rule types to support:**
| Rule Type | Description | Example |
|-----------|-------------|---------|
| **Time-based** | Fire only during specific hours | "Front door after 10pm" |
| **Zone-based** | Fire only when object enters/exits a zone | "Driveway: car arrived" |
| **Cross-camera** | Fire when same person appears on multiple cameras | "Person seen at front AND back door within 5 min" |
| **Absence** | Fire when expected person hasn't been seen | "No one home after 6pm on weekdays" |
| **Package** | Fire on delivery/pickup detection | "Package delivered to doorstep" |
| **Unusual time** | Fire when activity at unusual hour (existing, but enhanced) | "Garage door open at 3am" |
| **Duration** | Fire after object stays in zone N seconds | "Person loitering > 60s" |

**Effort:** ~2 weeks
**Dependencies:** Phase 1.4 (WebSocket for real-time rule evaluation push)

### 2.3 Mobile App — PWA Upgrade

**Changes needed:**
- Transform `/m` from a static HTML page into a **full PWA with service worker caching, offline support, and FCM/APNs push**
- Add **push notification registration** via Firebase Cloud Messaging (FCM) or Apple Push Notification Service (APNs)
- Implement **offline clip viewing** — cache recently viewed clips for playback without internet

**Architecture:**
```
┌─────────────────────────────────────────────┐
│  Mobile PWA (React/Next.js or vanilla JS)   │
│                                             │
│  ┌──────────┬──────────┬──────────┐         │
│  │ Home     │ Live     │ Clips    │ Settings│
│  │ Tab      │ Tab      │ Tab      │ Tab     │
│  └──────────┴──────────┴──────────┘         │
│                                             │
│  Service Worker:                             │
│  - Cache API responses                       │
│  - Queue actions when offline                │
│  - Handle push notifications                 │
│  - Background sync                           │
└──────────────┬──────────────────────────────┘
               │ FCM / APNs registration
               ▼
┌─────────────────────────────────────────────┐
│  Push Notification Service                   │
│  (FCM for Android, APNs for iOS)             │
│                                             │
│  Routes push to:                             │
│  - ntfy (existing, LAN-only)                 │
│  - FCM/APNs (cloud, remote access)           │
│  - Webhook (custom integrations)             │
└─────────────────────────────────────────────┘
```

**Key features:**
- **Push notifications**: Replace ntfy-only with FCM/APns as primary, ntfy as fallback for LAN
- **Offline mode**: Cache last N clips' thumbnails and metadata; allow viewing without connection
- **Biometric unlock**: Use WebAuthn API for fingerprint/FaceID login on supported browsers
- **Camera swipe gestures**: Swipe left/right between cameras in live view (already partially implemented)
- **Snooze from push**: ntfy/FCM action buttons that call the snooze API directly

**Effort:** ~3 weeks
**Dependencies:** Phase 2.1 (user auth for per-device registration), Phase 1.4 (WebSocket for real-time updates)

---

## Phase 3: Camera Health, AI Enhancements, Analytics

**Goal:** Add intelligence about camera health, cross-camera person tracking, and advanced analytics.

### 3.1 Camera Health Monitoring

**Changes needed:**
- Detect **camera tampering** — sudden change in scene that suggests the camera was moved or covered
- Detect **lens blur** — compare frame sharpness (Laplacian variance) against baseline
- Detect **IR failure** — monitor IR illuminator status via ONVIF or detect absence of night-mode frames
- Detect **coverage gaps** — analyze zone coverage to identify blind spots

**Implementation:**
```python
# Camera health checks (run every 60s per camera)
def check_camera_health(camera):
    frame = get_latest_frame(camera)

    # Tamper detection: compare against baseline scene
    if abs(laplacian_variance(frame) - baseline_variance) > threshold:
        alert("Camera may have been moved or covered")

    # Blur detection: Laplacian variance below threshold
    if laplacian_variance(frame) < BLUR_THRESHOLD:
        alert(f"Lens appears blurry on {camera.name}")

    # IR failure: check for night-mode frames without corresponding IR brightness
    if is_night_time() and frame_mean_brightness > IR_BRIGHTNESS_MAX:
        alert(f"IR illuminator may have failed on {camera.name}")

    # Coverage analysis: count detections per zone over 7 days
    coverage = analyze_zone_coverage(camera, days=7)
    for zone in coverage:
        if zone.detection_count < MIN_DETECTIONS:
            alert(f"Zone '{zone.name}' has low detection rate — may need adjustment")
```

**Health dashboard:**
- Per-camera health score (0-100) based on online time, recording quality, detection rate
- Alerts for tamper, blur, IR failure, coverage gaps
- Historical health trend chart

**Effort:** ~2 weeks
**Dependencies:** Phase 1.2 (live streaming provides consistent frame access)

### 3.2 Person Re-Identification Across Cameras

**Changes needed:**
- Implement **person re-ID** using a lightweight embedding model to match people across different camera views
- When the same person appears on Camera A and Camera B within a time window, link them as one visit
- Show cross-camera movement paths in the presence log

**Architecture:**
```
┌─────────────────────────────────────────────┐
│  Re-ID Pipeline                              │
│                                              │
│  For each new face detection:                │
│  1. Extract person embedding (ReID model)    │
│  2. Compare against active person tracks     │
│  3. If match within threshold → link visits  │
│  4. Update cross-camera movement graph       │
└─────────────────────────────────────────────┘
```

**Model:** Use a pre-trained person re-ID model (e.g., OSNet, ResNet50-ibn) exported to ONNX. Run on CPU with OpenVINO if available.

**Output:** The presence log shows "Alex walked from front door → kitchen → back garden" as a continuous visit across cameras.

**Effort:** ~2 weeks
**Dependencies:** Phase 1.1 (unlimited cameras), Phase 3.1 (camera health for reliable feeds)

### 3.3 Activity Analytics Dashboard

**Changes needed:**
- Build an **analytics dashboard** with charts and insights about activity patterns
- Show heatmaps of where people spend time, peak activity hours, most-seen visitors
- Compare week-over-week trends

**Dashboard sections:**
| Section | Content |
|---------|---------|
| **Activity overview** | Total visits this week vs last week, trend arrow |
| **Peak hours** | Bar chart of detections per hour (24h) |
| **Top visitors** | List of most-seen people/vehicles with count |
| **Zone activity** | Heatmap of zone usage over time |
| **Camera reliability** | Online time %, recording quality score |
| **Alert summary** | Number of alerts by type this week |

**Effort:** ~2 weeks
**Dependencies:** Phase 2.2 (alert rules engine provides alert categorization)

---

## Phase 4: Platform Polish, Integrations, Distribution

**Goal:** Make CamWatch production-ready for teams and easy to distribute.

### 4.1 Settings Export/Import & Backup

**Changes needed:**
- **Export all settings** as a single JSON file (cameras, zones, rules, users, alert preferences)
- **Import settings** from a file — useful for migrating between installations or restoring from backup
- **Automated backups** of the entire data directory to off-site storage

**Implementation:**
```json
// camwatch-export.json
{
  "version": "2.0",
  "exported_at": "2026-10-31T12:00:00Z",
  "cameras": [...],
  "zones": [...],
  "users": [...],
  "alert_rules": [...],
  "settings": {...}
}
```

**Effort:** ~1 week
**Dependencies:** Phase 2.1 (user management)

### 4.2 Webhook & API Integrations

**Changes needed:**
- **Outgoing webhooks** for every event type — users can configure a URL to receive JSON payloads
- **Incoming webhook handler** — accept events from external systems (e.g., "doorbell pressed" triggers camera recording)
- **GraphQL endpoint** (optional) — for complex queries on the presence log

**Webhook payload example:**
```json
{
  "event": "person_detected",
  "camera": "front_door",
  "time": "2026-10-31T14:30:00Z",
  "clip_url": "https://camwatch.local/clip/2026-10-31/abc123",
  "person": {
    "name": "Alex",
    "confidence": 0.92
  },
  "zone": "front_yard"
}
```

**Effort:** ~1 week
**Dependencies:** Phase 2.2 (alert rules engine provides event categorization)

### 4.3 Docker Compose One-Command Install

**Changes needed:**
- Create a **single `docker-compose.yml`** that works out of the box with sensible defaults
- Add an **interactive setup wizard** (`./setup.sh`) that guides users through camera discovery, ntfy config, and user creation
- Generate `.env` from wizard answers

**Setup wizard flow:**
```
1. Detect cameras on network (ONVIF scan)
2. Choose which to add
3. Configure push notifications (ntfy or FCM)
4. Create admin user
5. Set retention period
6. Start CamWatch
```

**Effort:** ~1 week
**Dependencies:** Phase 1.1 (camera registry), Phase 2.1 (user management)

### 4.4 Documentation & Distribution

**Changes needed:**
- **Full documentation site** — MkDocs or Docusaurus with setup guides, API reference, architecture diagrams
- **Docker Hub images** — publish `camwatch:latest` and `camwatch:stable` tags
- **Helm chart** for Kubernetes deployment (optional, for enterprise users)

**Effort:** ~2 weeks
**Dependencies:** All previous phases complete

---

## Implementation Timeline

| Phase | Duration | Key Deliverables |
|-------|----------|-----------------|
| **Phase 1** | 6 weeks | Unlimited cameras, go2rtc live streaming, REST API, WebSocket support |
| **Phase 2** | 7 weeks | Multi-user auth, alert rules engine, upgraded mobile PWA |
| **Phase 3** | 6 weeks | Camera health monitoring, person re-ID, analytics dashboard |
| **Phase 4** | 4 weeks | Settings export/import, webhooks, one-command install, docs |
| **Total** | **~23 weeks (~5-6 months)** | Complete CamWatch platform upgrade |

---

## Architecture Target State

```
┌─────────────────────────────────────────────────────────────────────┐
│                        CLIENT LAYER                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────────────────┐ │
│  │ Desktop   │  │ Mobile   │  │ Tablet   │  │ Home Assistant      │ │
│  │ React SPA │  │ PWA      │  │ React    │  │ MQTT + Webhook      │ │
│  └──────────┘  └──────────┘  └──────────┘  └─────────────────────┘ │
├─────────────────────────────────────────────────────────────────────┤
│                        API LAYER                                     │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  FastAPI REST + WebSocket Server (port 8081)                   │  │
│  │  - JWT auth, role-based access                                │  │
│  │  - Real-time event push via WebSocket                          │  │
│  │  - REST API for all resources                                  │  │
│  └───────────────────────────┬───────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────────────┤
│                        SERVICE LAYER                                 │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌─────────────────┐  │
│  │ Camera     │ │ Alert      │ │ Person     │ │ Analytics       │  │
│  │ Manager    │ │ Rules      │ │ Re-ID      │ │ Engine          │  │
│  │ (dynamic   │ │ Evaluator  │ │ Worker     │ │ (aggregates     │  │
│  │  spawn)    │ │            │ │            │ │  presence data) │  │
│  └────────────┘ └────────────┘ └────────────┘ └─────────────────┘  │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌─────────────────┐  │
│  │ Shared     │ │ Face       │ │ Plate      │ │ Off-site        │  │
│  │ Detector   │ │ Match      │ │ Reader     │ │ Sync            │  │
│  │ (YOLOv8)   │ │ Worker     │ │ Worker     │ │ (rclone)        │  │
│  └────────────┘ └────────────┘ └────────────┘ └─────────────────┘  │
├─────────────────────────────────────────────────────────────────────┤
│                        INFRASTRUCTURE                                │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌─────────────────┐  │
│  │ go2rtc     │ │ Redis      │ │ MariaDB    │ │ PostgreSQL/     │  │
│  │ (live      │ │ (cache +   │ │ (presence  │ │ SQLite          │  │
│  │  streaming)│  │ WS broker)│  │ log)       │ │ (users + auth) │  │
│  └────────────┘ └────────────┘ └────────────┘ └─────────────────┘  │
│  ┌────────────┐ ┌────────────┐                                      │
│  │ FCM/APNs   │ │ ntfy       │                                      │
│  │ (push)     │ │ (LAN push) │                                      │
│  └────────────┘ └────────────┘                                      │
├─────────────────────────────────────────────────────────────────────┤
│                        DATA LAYER                                    │
│  /recordings/   /photos/   /data/*.json   /data/search_index.npz    │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Migration Strategy

### Step-by-step rollout:

1. **Week 1-2:** Deploy Phase 1.3 (FastAPI) alongside existing Flask app. All new API endpoints are dual-path (Flask + FastAPI). No breaking changes.

2. **Week 3-4:** Enable WebSocket support. Clients gradually migrate from polling to WebSocket. Keep polling as fallback for 2 weeks.

3. **Week 5-6:** Deploy Phase 1.1 (unlimited cameras) and 1.2 (go2rtc). Test with existing cameras, then add new ones dynamically.

4. **Week 7-8:** Enable multi-user auth (Phase 2.1). Existing single-password mode continues to work. New users can be created via admin panel.

5. **Week 9-10:** Deploy alert rules engine (Phase 2.2). Import existing schedule-based rules as simple rules. Users create complex rules gradually.

6. **Week 11-12:** Launch upgraded mobile PWA (Phase 2.3). Existing `/m` page continues to work. New PWA available at `/app`.

7. **Week 13+:** Phase 3 and 4 features roll out as optional modules. Each can be enabled/disabled independently.

### Data migration:
- All existing data formats (settings.json, sightings.jsonl, plates.jsonl) are preserved
- MariaDB presence log schema is extended with new columns (backward compatible)
- User data starts empty; existing users migrate on first login

---

## Resource Requirements

| Component | Current | Target | Notes |
|-----------|---------|--------|-------|
| Cameras | 4 max | Unlimited | Shared detector reduces per-camera overhead |
| CPU (YOLO) | ~175ms × cameras | ~175ms shared + small overhead | ~3× improvement at scale |
| RAM | ~2 GB | ~3-4 GB | go2rtc + FastAPI + Redis add ~1 GB |
| Storage | Existing | +50 MB for new DB tables | Negligible increase |
| Network | LAN only | WAN via FCM/APNs + VPN optional | Push works remotely |

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| go2rtc RTSP compatibility issues | Medium | High | Test with target camera brands; keep ffmpeg fallback |
| WebSocket connection drops on unstable networks | High | Low | Auto-reconnect with exponential backoff; polling fallback |
| Person re-ID accuracy across wide angle differences | Medium | Medium | Use ensemble of models; allow manual correction in UI |
| FCM/APNs push delivery delays | Low | Medium | ntfy as always-available fallback |
| Multi-user auth breaking existing LAN-only mode | Low | High | Dual-mode: single-password OR multi-user, never both broken |

---

## Success Metrics

| Metric | Current | Target (Phase 4) |
|--------|---------|-----------------|
| Max cameras per install | 4 | Unlimited |
| Live view latency | ~2s (snapshot poll) | <500ms (WebRTC) |
| Push notification delivery | ntfy only, LAN | FCM/APNs + ntfy, global |
| Concurrent users | 1 | 50+ |
| Alert rule complexity | Armed/disarmed/schedule | Cross-camera, time-based, absence detection |
| Camera health insights | Online/offline | Tamper, blur, IR, coverage (4 metrics) |
| Documentation quality | README + HANDOVER.md | Full docs site with API reference |

---

*Plan generated 2026-10-31. All phases are designed to be backward compatible — existing CamWatch installations can upgrade incrementally without data loss or downtime.*
