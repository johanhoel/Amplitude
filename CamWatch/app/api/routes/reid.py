"""Person Re-Identification API endpoints."""
from fastapi import APIRouter, HTTPException, Header, Query
from typing import Optional

from api.auth import decode_jwt_token

router = APIRouter()


def _require_operator(auth: Optional[str]) -> bool:
    if not auth:
        return False
    payload = decode_jwt_token(auth.replace("Bearer ", ""))
    return bool(payload and payload.get("role") in ("admin", "operator"))


@router.get("/reid/tracks")
async def get_active_tracks(authorization: Optional[str] = Header(None)):
    """Get all active person tracks (people tracked across cameras)."""
    if not _require_operator(authorization):
        raise HTTPException(401, "Operator+ required")

    try:
        from api.reid_worker import reid_engine
        tracks = reid_engine.get_active_tracks()
        return {"tracks": tracks}
    except Exception as e:
        raise HTTPException(500, f"Failed to get tracks: {str(e)}")


@router.get("/reid/cross-camera-paths")
async def get_cross_camera_paths(days: int = 7, authorization: Optional[str] = Header(None)):
    """Get cross-camera movement paths for the past N days."""
    if not _require_operator(authorization):
        raise HTTPException(401, "Operator+ required")

    try:
        from api.reid_worker import reid_engine
        paths = reid_engine.get_cross_camera_paths(days)
        return {"paths": paths}
    except Exception as e:
        raise HTTPException(500, f"Failed to get paths: {str(e)}")


@router.post("/reid/process-event")
async def process_reid_event(event_data: dict, authorization: Optional[str] = Header(None)):
    """Process a new detection event for re-ID matching."""
    if not _require_operator(authorization):
        raise HTTPException(401, "Operator+ required")

    try:
        from api.reid_worker import reid_engine
        result = reid_engine.process_event(event_data)
        return result
    except Exception as e:
        raise HTTPException(500, f"Failed to process event: {str(e)}")


@router.get("/reid/stats")
async def get_reid_stats(authorization: Optional[str] = Header(None)):
    """Get re-ID engine statistics."""
    if not _require_operator(authorization):
        raise HTTPException(401, "Operator+ required")

    try:
        from api.reid_worker import reid_engine
        tracks = reid_engine.get_active_tracks()

        cameras_seen = set()
        for t in tracks:
            for c in t.get("cameras", []):
                cameras_seen.add(c)

        return {
            "active_tracks": len(tracks),
            "unique_cameras_tracked": len(cameras_seen),
            "known_people_matched": sum(1 for t in tracks if t.get("name")),
            "unknown_persons": sum(1 for t in tracks if not t.get("name")),
        }
    except Exception as e:
        raise HTTPException(500, f"Failed to get stats: {str(e)}")
