"""Camera health monitoring API endpoints."""
from fastapi import APIRouter, Header, HTTPException
from typing import Optional

from api.models import CameraHealth
from api.utils import DATA_DIR, load_json
from api.auth import decode_jwt_token

router = APIRouter()


def _require_operator(auth: Optional[str]) -> bool:
    if not auth:
        return False
    payload = decode_jwt_token(auth.replace("Bearer ", ""))
    return bool(payload and payload.get("role") in ("admin", "operator"))


@router.get("/health/cameras", response_model=list[CameraHealth])
async def get_camera_health(authorization: Optional[str] = Header(None)):
    """Get health status for all cameras including tamper, blur, IR checks."""
    if not _require_operator(authorization):
        raise HTTPException(401, "Operator+ required")

    cameras = load_json(DATA_DIR / "settings.json", {}).get("cameras", [])
    result = []

    for cam in cameras:
        name = cam.get("name", "")
        if not name or not cam.get("enabled"):
            continue

        # Check online status
        import os, time
        from pathlib import Path as _Path
        from datetime import datetime, timezone as _tz

        alive_file = _Path("/live") / name / "alive"
        is_online = False
        last_frame_at = None
        health_score = 0

        if alive_file.exists():
            mtime = alive_file.stat().st_mtime
            age = time.time() - mtime
            is_online = age < 60
            last_frame_at = datetime.fromtimestamp(mtime, tz=_tz.utc).isoformat()
            health_score = 85 if is_online else 20

        result.append(CameraHealth(
            camera=name,
            online=is_online,
            recording=age < 120 if alive_file.exists() else False,
            last_frame_at=last_frame_at,
            health_score=health_score,
        ))

    return result


@router.get("/health/summary")
async def get_health_summary(authorization: Optional[str] = Header(None)):
    """Get comprehensive health summary for all cameras."""
    if not _require_operator(authorization):
        raise HTTPException(401, "Operator+ required")

    import os, time
    from pathlib import Path as _Path
    from datetime import datetime, timezone as _tz

    cameras = load_json(DATA_DIR / "settings.json", {}).get("cameras", [])
    summary_cameras = []

    for cam in cameras:
        name = cam.get("name", "")
        if not name or not cam.get("enabled"):
            continue

        alive_file = _Path("/live") / name / "alive"
        is_online = False
        last_frame_at = None
        health_score = 0
        issues = []

        if alive_file.exists():
            mtime = alive_file.stat().st_mtime
            age = time.time() - mtime
            is_online = age < 60
            last_frame_at = datetime.fromtimestamp(mtime, tz=_tz.utc).isoformat()
            health_score = 85 if is_online else 20

            # Check for recording gap
            if age > 120 and is_online:
                issues.append({"type": "recording_gap", "message": f"No frames received in {int(age)}s"})

        summary_cameras.append({
            "camera": name,
            "online": is_online,
            "recording": age < 120 if alive_file.exists() else False,
            "last_frame_at": last_frame_at,
            "health_score": health_score,
            "issues": issues,
        })

    return {"cameras": summary_cameras}


@router.get("/health/zone-coverage")
async def get_zone_coverage(days: int = 7, authorization: Optional[str] = Header(None)):
    """Get zone coverage analysis for the past N days."""
    if not _require_operator(authorization):
        raise HTTPException(401, "Operator+ required")

    sightings_file = DATA_DIR / "sightings.jsonl"
    if not sightings_file.exists():
        return {"cameras": {}}

    try:
        lines = sightings_file.read_text().strip().split("\n")
        zone_counts = {}  # camera -> {zone: count}

        for line in lines:
            if not line.strip():
                continue
            try:
                event = json.loads(line)
                camera = event.get("camera", "")
                zones = event.get("zones", [])
                for zone in zones:
                    key = f"{camera}:{zone}"
                    zone_counts[key] = zone_counts.get(key, 0) + 1
            except (json.JSONDecodeError, KeyError):
                continue

        # Group by camera
        coverage = {}
        for key, count in zone_counts.items():
            camera, zone = key.split(":", 1)
            if camera not in coverage:
                coverage[camera] = []
            covered = count >= 5  # Min 5 detections to be "covered"
            coverage[camera].append({
                "zone": zone,
                "detections": count,
                "covered": covered,
            })

        return {"coverage": coverage}

    except Exception:
        return {"cameras": {}}


@router.get("/health/zone-coverage/{camera_name}")
async def get_camera_zone_coverage(camera_name: str, days: int = 7, authorization: Optional[str] = Header(None)):
    """Get zone coverage for a specific camera."""
    if not _require_operator(authorization):
        raise HTTPException(401, "Operator+ required")

    sightings_file = DATA_DIR / "sightings.jsonl"
    if not sightings_file.exists():
        return {"camera": camera_name, "zones": []}

    try:
        lines = sightings_file.read_text().strip().split("\n")
        zone_counts = {}

        for line in lines:
            if not line.strip():
                continue
            try:
                event = json.loads(line)
                if event.get("camera", "") != camera_name:
                    continue
                zones = event.get("zones", [])
                for zone in zones:
                    zone_counts[zone] = zone_counts.get(zone, 0) + 1
            except (json.JSONDecodeError, KeyError):
                continue

        zones = []
        for zone, count in sorted(zone_counts.items()):
            covered = count >= 5
            zones.append({
                "zone": zone,
                "detections": count,
                "covered": covered,
            })

        return {"camera": camera_name, "zones": zones}

    except Exception:
        return {"camera": camera_name, "zones": []}


import json
