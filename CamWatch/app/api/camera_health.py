"""Camera health monitoring — tamper, blur, IR failure, coverage analysis."""
import os
import json
import time
import threading
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional

import numpy as np

DATA_DIR = Path(os.environ.get("DATA_PATH", "/data"))
LIVE_DIR = Path("/live")

# Thresholds (tunable)
BLUR_THRESHOLD = 150.0          # Laplacian variance below this = blurry
TAMPER_VARIANCE_CHANGE = 3.0    # Variance change multiplier = tamper suspected
IR_BRIGHTNESS_MAX_NIGHT = 80    # Mean brightness > this at night = IR failure suspect
COVERAGE_MIN_DETECTIONS = 5     # Min detections per zone in 7 days to be "covered"

# Health score weights
WEIGHT_ONLINE = 0.30            # % of time online
WEIGHT_RECORDING = 0.25         # % of time recording when armed
WEIGHT_QUALITY = 0.25           # Blur/tamper/IR health
WEIGHT_DETECTION = 0.20         # Detection rate vs expected


class CameraHealthMonitor:
    """Monitors camera health metrics and produces per-camera scores."""

    def __init__(self):
        self._lock = threading.Lock()
        self._running = False
        self._thread = None
        self._health_history = {}  # camera -> list of {ts, score, issues}
        self._baseline_variances = {}  # camera -> baseline laplacian variance
        self._last_frame_times = {}  # camera -> timestamp
        self._zone_detection_counts = {}  # camera -> {zone_name: count}

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _run_loop(self):
        while self._running:
            try:
                self._check_all_cameras()
            except Exception:
                pass
            time.sleep(30)  # Check every 30 seconds

    def _check_all_cameras(self):
        """Run health checks for all known cameras."""
        cameras = self._get_known_cameras()
        for cam in cameras:
            name = cam.get("name", "")
            if not name:
                continue
            try:
                score, issues = self._check_camera(name)
                with self._lock:
                    self._health_history[name] = {
                        "score": score,
                        "issues": issues,
                        "checked_at": datetime.now(timezone.utc).isoformat()
                    }
            except Exception:
                pass

    def _get_known_cameras(self):
        """Get list of configured cameras from settings."""
        settings_file = DATA_DIR / "settings.json"
        try:
            raw = json.loads(settings_file.read_text()) if settings_file.exists() else {}
        except (FileNotFoundError, ValueError):
            raw = {}
        return raw.get("cameras", [])

    def _check_camera(self, camera_name: str) -> tuple:
        """Run all health checks for one camera. Returns (score_0_to_100, list_of_issues)."""
        issues = []
        scores = []

        # 1. Online status check
        online_score = self._check_online(camera_name)
        scores.append(("online", online_score))

        # 2. Recording health
        rec_score = self._check_recording_health(camera_name)
        scores.append(("recording", rec_score))

        # 3. Image quality (blur + tamper)
        quality_score = self._check_image_quality(camera_name)
        scores.append(("quality", quality_score))

        # 4. IR failure check at night
        ir_score = self._check_ir_failure(camera_name)
        scores.append(("ir", ir_score))

        # Calculate weighted score
        total_weight = WEIGHT_ONLINE + WEIGHT_RECORDING + WEIGHT_QUALITY + WEIGHT_DETECTION
        weighted = (
            online_score * WEIGHT_ONLINE / total_weight +
            rec_score * WEIGHT_RECORDING / total_weight +
            quality_score * WEIGHT_QUALITY / total_weight +
            ir_score * WEIGHT_DETECTION / total_weight
        )
        final_score = round(min(100, max(0, weighted)))

        # Build issue list
        if online_score < 50:
            issues.append({"type": "offline", "severity": "high", "message": f"{camera_name} is frequently offline"})
        if rec_score < 50:
            issues.append({"type": "recording_gap", "severity": "medium", "message": f"{camera_name} has recording gaps"})
        if quality_score < 60:
            issues.append({"type": "blurry", "severity": "medium", "message": f"{camera_name} lens appears blurry"})
        if ir_score < 50:
            issues.append({"type": "ir_failure", "severity": "high", "message": f"{camera_name} IR illuminator may have failed"})

        return final_score, issues

    def _check_online(self, camera_name: str) -> float:
        """Check if camera is online based on alive file freshness."""
        alive_file = LIVE_DIR / camera_name / "alive"
        if not alive_file.exists():
            return 0.0
        age = time.time() - alive_file.stat().st_mtime
        if age < 60:
            return 100.0
        elif age < 300:
            return 50.0
        else:
            return 10.0

    def _check_recording_health(self, camera_name: str) -> float:
        """Check if camera is actively recording."""
        rec_file = LIVE_DIR / camera_name / "alive"
        if not rec_file.exists():
            return 0.0
        age = time.time() - rec_file.stat().st_mtime
        if age < 120:
            return 100.0
        elif age < 360:
            return 50.0
        else:
            return 10.0

    def _check_image_quality(self, camera_name: str) -> float:
        """Check image quality via Laplacian variance (blur detection)."""
        live_dir = LIVE_DIR / camera_name
        if not live_dir.exists():
            return 50.0

        # Find the most recent alive file to get a frame reference
        try:
            frames = sorted(live_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
            # Try to read a JPEG frame
            for f in frames[:10]:
                if f.suffix.lower() in ('.jpg', '.jpeg'):
                    arr = np.frombuffer(f.read_bytes(), dtype=np.uint8)
                    img = cv2_imdecode(arr)
                    if img is not None:
                        return self._evaluate_quality(img, camera_name)
        except Exception:
            pass

        # Fallback: check if we have any recent frames
        for f in frames[:5]:
            age = time.time() - f.stat().st_mtime
            if age < 60:
                return 70.0
        return 30.0

    def _evaluate_quality(self, img, camera_name: str) -> float:
        """Evaluate image quality using Laplacian variance."""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()

        # Track baseline for tamper detection
        with self._lock:
            if camera_name not in self._baseline_variances:
                self._baseline_variances[camera_name] = laplacian_var
                return 80.0  # First frame, assume OK

            baseline = self._baseline_variances[camera_name]

            # Blur detection
            if laplacian_var < BLUR_THRESHOLD:
                return 30.0  # Very blurry

            # Tamper detection (sudden large change in variance)
            if baseline > 10 and abs(laplacian_var - baseline) / baseline > TAMPER_VARIANCE_CHANGE:
                self._baseline_variances[camera_name] = laplacian_var  # Reset baseline
                return 40.0  # Possible tamper

            # Normal operation
            if laplacian_var > BLUR_THRESHOLD * 2:
                return 100.0  # Sharp image
            elif laplacian_var > BLUR_THRESHOLD * 1.5:
                return 80.0   # Acceptable
            else:
                return 60.0   # Slightly soft

    def _check_ir_failure(self, camera_name: str) -> float:
        """Check if IR illuminator may have failed at night."""
        live_dir = LIVE_DIR / camera_name
        if not live_dir.exists():
            return 50.0

        now = datetime.now()
        # Only check between 21:00 and 06:00 (night hours)
        if not (now.hour >= 21 or now.hour < 6):
            return 100.0  # Not night time, skip

        try:
            frames = sorted(live_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
            for f in frames[:5]:
                if f.suffix.lower() not in ('.jpg', '.jpeg'):
                    continue
                age = time.time() - f.stat().st_mtime
                if age > 120:
                    continue
                arr = np.frombuffer(f.read_bytes(), dtype=np.uint8)
                img = cv2_imdecode(arr)
                if img is not None:
                    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img
                    mean_brightness = gray.mean()
                    if mean_brightness > IR_BRIGHTNESS_MAX_NIGHT:
                        return 30.0  # Too bright for night = IR may have failed
                    return 100.0  # Normal night brightness
        except Exception:
            pass

        return 70.0  # Couldn't determine

    def get_health_summary(self) -> dict:
        """Get health summary for all cameras."""
        cameras = self._get_known_cameras()
        result = []

        with self._lock:
            history = dict(self._health_history)

        for cam in cameras:
            name = cam.get("name", "")
            if not name:
                continue

            # Check online status
            alive_file = LIVE_DIR / name / "alive"
            is_online = False
            last_frame_at = None
            if alive_file.exists():
                mtime = alive_file.stat().st_mtime
                age = time.time() - mtime
                is_online = age < 60
                last_frame_at = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()

            health_data = history.get(name, {})
            score = health_data.get("score", None) if is_online else 0
            issues = health_data.get("issues", [])

            result.append({
                "camera": name,
                "online": is_online,
                "recording": age < 120 if alive_file.exists() else False,
                "last_frame_at": last_frame_at,
                "health_score": score if score is not None else (85 if is_online else 0),
                "issues": issues,
            })

        return {"cameras": result}

    def get_zone_coverage(self, days: int = 7) -> dict:
        """Analyze zone coverage over the past N days."""
        sightings_file = DATA_DIR / "sightings.jsonl"
        if not sightings_file.exists():
            return {}

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        zone_counts = {}  # camera -> {zone: count}

        try:
            lines = sightings_file.read_text().strip().split("\n")
            for line in lines:
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                    event_time = datetime.fromisoformat(event.get("start", "").replace("Z", "+00:00"))
                    if event_time < cutoff:
                        continue

                    camera = event.get("camera", "")
                    zones = event.get("zones", [])
                    for zone in zones:
                        key = f"{camera}:{zone}"
                        zone_counts[key] = zone_counts.get(key, 0) + 1
                except (json.JSONDecodeError, KeyError):
                    continue
        except Exception:
            pass

        # Determine which zones are "covered" (enough detections)
        coverage = {}
        for key, count in zone_counts.items():
            camera, zone = key.split(":", 1)
            if camera not in coverage:
                coverage[camera] = []
            coverage[camera].append({
                "zone": zone,
                "detections": count,
                "covered": count >= COVERAGE_MIN_DETECTIONS
            })

        return coverage


def cv2_imdecode(buf):
    """Decode a numpy buffer to an OpenCV image."""
    try:
        import cv2 as _cv2
        return _cv2.imdecode(np.frombuffer(buf, dtype=np.uint8), _cv2.IMREAD_COLOR)
    except Exception:
        return None


# Singleton instance
health_monitor = CameraHealthMonitor()
