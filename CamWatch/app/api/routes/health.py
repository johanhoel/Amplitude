"""Health check API endpoints."""
from fastapi import APIRouter, HTTPException
import os
import json
from pathlib import Path
from datetime import datetime, timezone

from api.models import HealthStatus, CameraHealth
from api.utils import get_cameras, get_camera_online_status, get_disk_usage, REC_DIR, DATA_DIR

router = APIRouter()


@router.get("/status", response_model=HealthStatus)
async def get_status():
    cameras = get_cameras()
    online = get_camera_online_status()
    camera_health = []
    for cam in cameras:
        name = cam.get("name", "")
        is_online = online.get(name, False)
        rec_file = Path("/live") / name / "alive"
        is_recording = False
        last_frame_at = None
        if rec_file.exists():
            mtime = rec_file.stat().st_mtime
            age = datetime.now(timezone.utc).timestamp() - mtime
            is_recording = age < 120
            last_frame_at = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
        camera_health.append(CameraHealth(camera=name, online=is_online, recording=is_recording, last_frame_at=last_frame_at, health_score=100 if is_online else 0))

    settings_file = DATA_DIR / "settings.json"
    try:
        raw = json.loads(settings_file.read_text()) if settings_file.exists() else {}
        mode = raw.get("mode", "armed")
        armed = mode != "disarmed"
    except Exception:
        mode, armed = "armed", True

    return HealthStatus(version=get_version_info(), cameras=camera_health, disk=get_disk_usage(), armed=armed, mode=mode)


@router.get("/healthz")
async def health_check():
    return {"status": "ok"}


def get_version_info() -> dict:
    vf = Path("/opt/camwatch/VERSION") if Path("/opt/camwatch").exists() else Path("VERSION")
    try: return {"text": vf.read_text().strip()}
    except (FileNotFoundError, OSError): return {}
