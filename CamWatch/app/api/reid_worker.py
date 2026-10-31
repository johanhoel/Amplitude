"""Person Re-Identification across cameras using lightweight embeddings."""
import os
import json
import time
import threading
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional

import numpy as np

DATA_DIR = Path(os.environ.get("DATA_PATH", "/data"))
PHOTOS_DIR = Path(os.environ.get("PHOTOS_PATH", "/photos"))
REC_DIR = Path(os.environ.get("RECORDINGS_PATH", "/recordings"))

# Re-ID settings
REID_THRESHOLD = 0.65          # Cosine similarity threshold for matching
REID_TIME_WINDOW = 3600 * 24   # 24 hours - max time between cross-camera matches
REID_MAX_TRACKS = 100          # Max active person tracks to keep in memory


class PersonTrack:
    """Represents a tracked person across cameras."""

    def __init__(self, track_id, name="", embedding=None):
        self.track_id = track_id
        self.name = name
        self.embedding = embedding  # numpy array or None
        self.cameras = []           # List of camera names seen on
        self.last_seen = datetime.now(timezone.utc)
        self.first_seen = datetime.now(timezone.utc)
        self.detection_count = 0

    def update(self, camera_name, embedding=None):
        """Update track with new detection."""
        if camera_name not in self.cameras:
            self.cameras.append(camera_name)
        self.last_seen = datetime.now(timezone.utc)
        self.detection_count += 1
        if embedding is not None and self.embedding is None:
            self.embedding = embedding

    def to_dict(self):
        return {
            "track_id": self.track_id,
            "name": self.name,
            "cameras": list(set(self.cameras)),
            "last_seen": self.last_seen.isoformat(),
            "first_seen": self.first_seen.isoformat(),
            "detection_count": self.detection_count,
        }


class PersonReID:
    """Lightweight person re-ID engine that links people across cameras."""

    def __init__(self):
        self._lock = threading.Lock()
        self._tracks = {}  # track_id -> PersonTrack
        self._next_track_id = 1
        self._known_embeddings = {}  # name -> embedding (from photo library)
        self._active_tracks = []     # List of active tracks (recently seen people)

    def start(self):
        """Load known embeddings from photo library."""
        self._load_known_faces()

    def stop(self):
        pass

    def _load_known_faces(self):
        """Load person embeddings from the photo library."""
        if not PHOTOS_DIR.exists():
            return

        for person_dir in PHOTOS_DIR.iterdir():
            if not person_dir.is_dir():
                continue
            name = person_dir.name
            # Load first photo as reference embedding
            photos = sorted(person_dir.glob("*.jpg")) + sorted(person_dir.glob("*.jpeg")) + sorted(person_dir.glob("*.png"))
            if photos:
                try:
                    from PIL import Image
                    img = Image.open(photos[0]).convert("RGB")
                    # Simple embedding: average color histogram of face region
                    arr = np.array(img)
                    # Use a simplified approach - mean RGB values as lightweight embedding
                    embedding = arr.mean(axis=(0, 1))[:64]  # Take first 64 dims
                    self._known_embeddings[name] = embedding / (np.linalg.norm(embedding) + 1e-8)
                except Exception:
                    pass

    def _cosine_similarity(self, a, b):
        """Calculate cosine similarity between two vectors."""
        if a is None or b is None:
            return 0.0
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a < 1e-8 or norm_b < 1e-8:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))

    def process_event(self, event_data: dict) -> dict:
        """
        Process a new detection event and try to match against existing tracks.

        Args:
            event_data: Event with camera, stem, day, labels, faces_seen, unknown_faces

        Returns:
            Dict with matched_track_id (if any), person_name (if known)
        """
        camera = event_data.get("camera", "")
        stem = event_data.get("stem", "")
        day = event_data.get("day", "")

        # Try to load face embeddings from the clip's faces data
        faces_file = REC_DIR / day / f"{stem}.faces.json"
        embedding = None
        if faces_file.exists():
            try:
                faces_data = json.loads(faces_file.read_text())
                # Use the first unknown face's embedding if available
                unknown_faces = faces_data.get("unknown", [])
                if unknown_faces and "embedding" in unknown_faces[0]:
                    emb_list = unknown_faces[0]["embedding"]
                    if isinstance(emb_list, list) and len(emb_list) > 0:
                        embedding = np.array(emb_list[:64])  # Truncate/pad to 64 dims
            except Exception:
                pass

        result = {"matched_track_id": None, "person_name": None}

        with self._lock:
            now = datetime.now(timezone.utc)

            # Clean old tracks (older than time window)
            active = []
            for track in self._active_tracks:
                if (now - track.last_seen).total_seconds() < REID_TIME_WINDOW:
                    active.append(track)
            self._active_tracks = active

            best_match = None
            best_score = 0.0

            # Try to match against existing tracks
            for track in self._active_tracks:
                if camera in track.cameras:
                    continue  # Skip same camera

                sim = self._cosine_similarity(track.embedding, embedding)
                if sim > REID_THRESHOLD and sim > best_score:
                    best_match = track
                    best_score = sim

            # Try to match against known people from photo library
            best_known_name = None
            best_known_score = 0.0
            for name, known_emb in self._known_embeddings.items():
                sim = self._cosine_similarity(known_emb, embedding)
                if sim > REID_THRESHOLD and sim > best_known_score:
                    best_known_name = name
                    best_known_score = sim

            if best_match:
                # Link to existing track (cross-camera match!)
                best_match.update(camera, embedding)
                result["matched_track_id"] = best_match.track_id
                result["person_name"] = best_match.name or None
                result["match_type"] = "cross_camera"
                result["confidence"] = round(best_score, 3)

            elif best_known_name:
                # Matched a known person from library
                if not any(t.name == best_known_name for t in self._active_tracks):
                    new_track = PersonTrack(self._next_track_id, best_known_name, embedding)
                    new_track.first_seen = now
                    self._next_track_id += 1
                    self._active_tracks.append(new_track)
                else:
                    # Update existing track with this name
                    for t in self._active_tracks:
                        if t.name == best_known_name:
                            t.update(camera, embedding)
                            break
                result["matched_track_id"] = None
                result["person_name"] = best_known_name
                result["match_type"] = "known_person"
                result["confidence"] = round(best_known_score, 3)

            else:
                # New person - create a new track
                if len(self._active_tracks) < REID_MAX_TRACKS:
                    new_track = PersonTrack(self._next_track_id, "", embedding)
                    new_track.first_seen = now
                    self._next_track_id += 1
                    self._active_tracks.append(new_track)
                    result["matched_track_id"] = new_track.track_id
                    result["person_name"] = None
                    result["match_type"] = "new_person"

        return result

    def get_active_tracks(self) -> list:
        """Get all active person tracks."""
        with self._lock:
            return [t.to_dict() for t in self._active_tracks]

    def get_cross_camera_paths(self, days: int = 7) -> list:
        """Get cross-camera movement paths for the past N days."""
        with self._lock:
            now = datetime.now(timezone.utc)
            cutoff = now - timedelta(days=days)

            paths = []
            for track in self._active_tracks:
                if (now - track.first_seen).total_seconds() > days * 86400:
                    continue
                unique_cameras = list(dict.fromkeys(track.cameras))  # Preserve order, remove dupes
                if len(unique_cameras) >= 2:
                    paths.append({
                        "track_id": track.track_id,
                        "name": track.name or f"Person #{track.track_id}",
                        "cameras": unique_cameras,
                        "first_seen": track.first_seen.isoformat(),
                        "last_seen": track.last_seen.isoformat(),
                    })

            return paths


# Singleton instance
reid_engine = PersonReID()
