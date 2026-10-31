"""Clip management API endpoints."""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
import os
from pathlib import Path
import json
import shutil

from api.models import ClipMetadata, ClipListResponse
from api.utils import get_clip_metadata, get_clips_for_day, get_all_days, REC_DIR

router = APIRouter()


@router.get("/clips", response_model=ClipListResponse)
async def list_clips(
    day: Optional[str] = Query(None),
    person: Optional[str] = Query(None),
    plate: Optional[str] = Query(None),
    starred: bool = Query(False),
    camera: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
):
    all_days = get_all_days() if not day else ([day] if day in get_all_days() else [])
    all_clips = []
    for d in all_days:
        clips = get_clips_for_day(d)
        all_clips.extend(clips)

    filtered = all_clips
    if person:
        pl = person.lower()
        filtered = [c for c in filtered if _matches_person(c, pl)]
    if plate:
        pu = plate.upper().replace(" ", "")
        filtered = [c for c in filtered if any(p.get("plate", "").upper().replace(" ", "") == pu for p in c.get("plates", []))]
    if starred:
        filtered = [c for c in filtered if c.get("starred")]
    if camera:
        filtered = [c for c in filtered if c.get("camera") == camera]

    filtered.sort(key=lambda x: x.get("start", ""), reverse=True)
    total = len(filtered)
    start = (page - 1) * per_page
    end = start + per_page
    return ClipListResponse(clips=filtered[start:end], total=total, page=page, per_page=per_page)


@router.get("/clips/{day}/{stem}", response_model=ClipMetadata)
async def get_clip(day: str, stem: str):
    meta = get_clip_metadata(day, stem)
    if not meta:
        raise HTTPException(status_code=404, detail=f"Clip {day}/{stem} not found")
    return ClipMetadata(
        day=day, stem=stem, camera=meta.get("camera", ""), start=meta.get("start"),
        end=meta.get("end"), labels=meta.get("labels", {}), zones=meta.get("zones", []),
        loitering=meta.get("loitering", False), test=meta.get("test", False),
        plates=meta.get("plates", []), vehicles=meta.get("vehicles", []),
        faces_seen=meta.get("faces_seen", 0), unknown_faces=meta.get("unknown_faces", 0),
        starred=meta.get("starred", False),
    )


@router.post("/clips/{day}/{stem}/star")
async def toggle_star(day: str, stem: str):
    meta = get_clip_metadata(day, stem)
    if not meta:
        raise HTTPException(status_code=404, detail=f"Clip {day}/{stem} not found")
    star_path = REC_DIR / day / f"{stem}.star"
    starred = star_path.exists()
    if starred:
        star_path.unlink(missing_ok=True)
    else:
        star_path.touch()
    return {"starred": not starred}


@router.post("/clips/{day}/{stem}/delete")
async def delete_clip(day: str, stem: str):
    day_dir = REC_DIR / day
    if not day_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Day {day} not found")
    deleted_files = []
    for ext in [".mp4", ".mkv", ".jpg", ".json", ".faces.json", ".labels.json", ".track.json", ".star"]:
        fpath = day_dir / f"{stem}{ext}"
        if fpath.exists():
            fpath.unlink()
            deleted_files.append(str(fpath))
    for dname in [f"{stem}_faces", f"{stem}_plates"]:
        ddir = day_dir / dname
        if ddir.is_dir():
            shutil.rmtree(ddir)
            deleted_files.append(str(ddir))
    return {"deleted": len(deleted_files), "files": deleted_files}


@router.post("/clips/bulk/delete")
async def delete_clips_bulk(body: dict):
    stems = body.get("stems", [])
    deleted = []
    for item in stems:
        parts = item.split("/", 1)
        if len(parts) != 2: continue
        day, stem = parts
        meta = get_clip_metadata(day, stem)
        if not meta: continue
        day_dir = REC_DIR / day
        for ext in [".mp4", ".mkv", ".jpg", ".json", ".faces.json", ".labels.json", ".track.json", ".star"]:
            fpath = day_dir / f"{stem}{ext}"
            if fpath.exists(): fpath.unlink()
        for dname in [f"{stem}_faces", f"{stem}_plates"]:
            ddir = day_dir / dname
            if ddir.is_dir(): shutil.rmtree(ddir)
        deleted.append(item)
    return {"deleted": len(deleted), "stems": deleted}


@router.get("/clips/days")
async def list_days():
    days = get_all_days()
    result = []
    for d in days:
        clips = get_clips_for_day(d)
        result.append({"day": d, "clip_count": len(clips)})
    return result


def _matches_person(clip_meta: dict, person_lower: str) -> bool:
    for label_key in clip_meta.get("labels", {}):
        if person_lower in label_key.lower(): return True
    faces_path = REC_DIR / clip_meta["day"] / f"{clip_meta['stem']}.faces.json"
    try:
        faces_data = json.loads(faces_path.read_text())
        for face in faces_data.get("known", []):
            if person_lower in face.get("name", "").lower(): return True
    except Exception: pass
    for plate_entry in clip_meta.get("plates", []):
        name = plate_entry.get("name") or ""
        if person_lower in name.lower(): return True
    return False
