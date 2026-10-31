"""FastAPI server for CamWatch — mounts all route routers with JWT auth middleware."""
import os
import json
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Import the alert engine so it can be started/stopped with the app lifecycle
import sys
sys.path.insert(0, str(Path(__file__).parent))
from api.alert_engine import alert_engine

DATA_DIR = Path(os.environ.get("DATA_PATH", "/data"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: start the alert rules engine background thread
    print("[api] Starting CamWatch API server on :8081")
    alert_engine.start()
    yield
    # Shutdown: stop the alert engine
    alert_engine.stop()
    print("[api] CamWatch API server stopped")


app = FastAPI(
    title="CamWatch",
    description="REST + WebSocket API for CamWatch surveillance system",
    version=os.environ.get("CAMWATCH_VERSION", "2.0.0"),
    lifespan=lifespan,
)

# CORS — allow the Flask web UI and mobile PWA to call API endpoints
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- JWT auth middleware ----------

def _decode_token(auth_header: str | None) -> dict:
    """Extract and decode a JWT from the Authorization header. Returns empty dict on failure."""
    if not auth_header:
        return {}
    token = auth_header.replace("Bearer ", "")
    try:
        from api.auth import decode_jwt_token
        return decode_jwt_token(token)
    except Exception:
        return {}


@app.middleware("http")
async def jwt_auth_middleware(request: Request, call_next):
    """
    Protect all API routes with JWT auth. Public routes (health, status) are exempt.
    """
    # Routes that don't require authentication
    public_paths = {"/api/healthz", "/api/status", "/api/version", "/ws"}
    if request.url.path in public_paths or request.url.path.startswith("/static/"):
        return await call_next(request)

    # Check for JWT token
    auth_header = request.headers.get("Authorization")
    payload = _decode_token(auth_header)

    if not payload:
        # Return 401 only for API routes, otherwise let it pass (Flask handles its own auth)
        if request.url.path.startswith("/api/"):
            return JSONResponse(
                status_code=401,
                content={"detail": "Authentication required. Provide a valid JWT token."}
            )

    # Attach decoded user info to the request state for downstream use
    request.state.user = payload if payload else {}
    return await call_next(request)


# ---------- WebSocket support ----------

@app.websocket("/ws")
async def websocket_endpoint(websocket):
    """
    Broadcast real-time events (new clips, camera status changes) to connected clients.
    Clients can subscribe by sending a JSON message like {"action": "subscribe", "camera": "camera1"}
    """
    await websocket.accept()
    client_id = id(websocket)
    print(f"[ws] Client connected: {client_id}")

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data) if data.strip() else {}
            action = msg.get("action", "")

            if action == "subscribe":
                # Client wants to subscribe to events (optionally filtered by camera)
                print(f"[ws] Client {client_id} subscribed")
                await websocket.send_text(json.dumps({"type": "subscribed", "camera": msg.get("camera")}))

            elif action == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))

    except Exception as e:
        print(f"[ws] Client {client_id} disconnected: {e}")
    finally:
        print(f"[ws] Client {client_id} removed")


# ---------- Mount all route routers ----------

from api.routes import cameras, clips, visits, settings as settings_routes, users, alerts, health

app.include_router(cameras.router, prefix="/api", tags=["cameras"])
app.include_router(clips.router, prefix="/api", tags=["clips"])
app.include_router(visits.router, prefix="/api", tags=["visits"])
app.include_router(settings_routes.router, prefix="/api", tags=["settings"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(alerts.router, prefix="/api/alerts", tags=["alerts"])
app.include_router(health.router, prefix="/api", tags=["health"])


# ---------- Additional endpoints not in route modules ----------

@app.post("/api/cameras/{camera_name}/snooze")
async def snooze_camera(camera_name: str, request: Request):
    """Snooze pushes from a specific camera for 1 hour."""
    try:
        body = await request.json()
        minutes = body.get("minutes", 60)
    except Exception:
        minutes = 60

    settings_file = DATA_DIR / "settings.json"
    try:
        raw = json.loads(settings_file.read_text()) if settings_file.exists() else {}
    except (FileNotFoundError, ValueError):
        raw = {}

    snoozed = raw.get("snoozed", {})
    from datetime import datetime, timezone, timedelta
    snoozed[camera_name] = (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()
    raw["snoozed"] = snoozed

    tmp = settings_file.with_suffix(".tmp")
    tmp.write_text(json.dumps(raw))
    tmp.replace(settings_file)

    return {"camera": camera_name, "snoozed_until": snoozed[camera_name]}


@app.post("/api/cameras/{camera_name}/unsnooze")
async def unsnooze_camera(camera_name: str):
    """Un-snooze a camera (re-enable pushes)."""
    settings_file = DATA_DIR / "settings.json"
    try:
        raw = json.loads(settings_file.read_text()) if settings_file.exists() else {}
    except (FileNotFoundError, ValueError):
        raw = {}

    snoozed = raw.get("snoozed", {})
    if camera_name in snoozed:
        del snoozed[camera_name]
        raw["snoozed"] = snoozed
        tmp = settings_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(raw))
        tmp.replace(settings_file)

    return {"camera": camera_name, "unsnoozed": True}


@app.get("/api/cameras/{camera_name}/snooze-status")
async def get_snooze_status(camera_name: str):
    """Check if a camera is currently snoozed."""
    settings_file = DATA_DIR / "settings.json"
    try:
        raw = json.loads(settings_file.read_text()) if settings_file.exists() else {}
    except (FileNotFoundError, ValueError):
        raw = {}

    snoozed = raw.get("snoozed", {})
    is_snoozed = camera_name in snoozed
    return {"camera": camera_name, "snoozed": is_snoozed}


@app.post("/api/events/evaluate")
async def trigger_event_evaluation(request: Request):
    """
    Trigger alert engine evaluation for a new event.
    Called by the recorder after each clip is finalized.
    Expects JSON body with event data (camera, stem, day, labels, etc.)
    Returns list of matched rule IDs.
    """
    try:
        event_data = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON body")

    matched = alert_engine.evaluate_event(event_data)
    return {"matched_rules": matched}


@app.get("/api/alerts/rules/{rule_id}")
async def get_rule(rule_id: str):
    """Get a single alert rule by ID."""
    rules_file = DATA_DIR / "alert_rules.json"
    try:
        rules = json.loads(rules_file.read_text()) if rules_file.exists() else []
    except (FileNotFoundError, ValueError):
        rules = []

    for r in rules:
        if r.get("id") == rule_id:
            return {"id": r["id"], "name": r["name"], "enabled": r.get("enabled", True),
                    "conditions": r.get("conditions", {}), "actions": r.get("actions", {}),
                    "cooldown_seconds": r.get("cooldown_seconds", 300)}
    raise HTTPException(404, f"Rule '{rule_id}' not found")


@app.post("/api/alerts/rules/{rule_id}/evaluate-now")
async def evaluate_rule_now(rule_id: str):
    """Manually trigger evaluation of a specific rule against the latest event."""
    rules_file = DATA_DIR / "alert_rules.json"
    try:
        rules = json.loads(rules_file.read_text()) if rules_file.exists() else []
    except (FileNotFoundError, ValueError):
        rules = []

    target_rule = None
    for r in rules:
        if r.get("id") == rule_id:
            target_rule = r
            break

    if not target_rule:
        raise HTTPException(404, f"Rule '{rule_id}' not found")

    # Create a synthetic event from the latest clip data
    clips_dir = Path(os.environ.get("RECORDINGS_PATH", "/recordings"))
    days = sorted([d.name for d in clips_dir.iterdir() if d.is_dir()], reverse=True)
    if not days:
        raise HTTPException(404, "No recordings found")

    latest_day = days[0]
    day_dir = clips_dir / latest_day
    json_files = sorted([f for f in day_dir.iterdir() if f.suffix == ".json"], reverse=True)
    if not json_files:
        raise HTTPException(404, "No clip data found")

    event_data = json.loads(json_files[0].read_text())
    matched = alert_engine.evaluate_event(event_data)
    return {"rule_id": rule_id, "matched": rule_id in matched}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("API_PORT", 8081))
    print(f"[api] Starting on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
