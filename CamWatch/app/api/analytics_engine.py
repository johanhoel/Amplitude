"""Activity analytics engine — aggregates presence log data into insights."""
import os
import json
import threading
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import defaultdict, Counter

DATA_DIR = Path(os.environ.get("DATA_PATH", "/data"))


class AnalyticsEngine:
    """Aggregates sightings/visits data into analytics insights."""

    def __init__(self):
        self._lock = threading.Lock()

    def get_weekly_report(self) -> dict:
        """Generate a weekly activity report from the presence log."""
        sightings_file = DATA_DIR / "sightings.jsonl"

        result = {
            "visits_per_day": {},
            "visits_per_hour": {},
            "people_count": 0,
            "packages": [],
            "animals": [],
            "top_cameras": [],
            "unique_people": set(),
        }

        if not sightings_file.exists():
            return result

        try:
            lines = sightings_file.read_text().strip().split("\n")
            visits_data = []
            for line in lines:
                if not line.strip():
                    continue
                try:
                    visits_data.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

            now = datetime.now(timezone.utc)
            week_ago = now - timedelta(days=7)

            vpd = defaultdict(int)   # day -> count
            vph = defaultdict(int)   # hour -> count
            people_set = set()
            packages = []
            animals = []
            camera_counts = Counter()

            for visit in visits_data:
                start_str = visit.get("start", "")
                if not start_str:
                    continue
                try:
                    start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    continue

                # Only include last 7 days
                if start_dt < week_ago:
                    continue

                day_key = start_dt.strftime("%Y-%m-%d")
                hour_key = start_dt.strftime("%H:00")

                vpd[day_key] += 1
                vph[hour_key] += 1

                # Track unique people
                who = visit.get("who", "")
                if who and who != "unknown":
                    people_set.add(who)

                # Count cameras
                camera = visit.get("camera", "")
                if camera:
                    camera_counts[camera] += 1

                # Categorize visitors
                visitors = visit.get("visitors", [])
                for v in visitors:
                    kind = v.get("kind", "")
                    if kind == "package":
                        packages.append({
                            "camera": camera,
                            "time": start_str,
                            "detail": v.get("detail", ""),
                        })
                    elif kind == "animal":
                        animals.append({
                            "camera": camera,
                            "time": start_str,
                            "detail": v.get("detail", ""),
                        })

            result["visits_per_day"] = dict(vpd)
            result["visits_per_hour"] = dict(vph)
            result["people_count"] = len(people_set)
            result["packages"] = packages[-20:]  # Last 20 packages
            result["animals"] = animals[-20:]    # Last 20 animal detections
            result["top_cameras"] = [
                {"camera": cam, "count": cnt} 
                for cam, cnt in camera_counts.most_common(10)
            ]

        except Exception:
            pass

        return result

    def get_monthly_summary(self) -> dict:
        """Generate a monthly summary report."""
        sightings_file = DATA_DIR / "sightings.jsonl"

        if not sightings_file.exists():
            return {"error": "No sightings data"}

        try:
            lines = sightings_file.read_text().strip().split("\n")
            visits_data = []
            for line in lines:
                if not line.strip():
                    continue
                try:
                    visits_data.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

            # Group by month
            monthly = defaultdict(lambda: {"visits": 0, "people": set(), "packages": 0})

            for visit in visits_data:
                start_str = visit.get("start", "")
                if not start_str:
                    continue
                try:
                    start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    continue

                month_key = start_dt.strftime("%Y-%m")
                monthly[month_key]["visits"] += 1

                who = visit.get("who", "")
                if who and who != "unknown":
                    monthly[month_key]["people"].add(who)

                for v in visit.get("visitors", []):
                    if v.get("kind") == "package":
                        monthly[month_key]["packages"] += 1

            # Format output
            summary = {}
            for month, data in sorted(monthly.items(), reverse=True)[:6]:  # Last 6 months
                summary[month] = {
                    "visits": data["visits"],
                    "unique_people": len(data["people"]),
                    "packages": data["packages"],
                }

            return {"monthly_summary": summary}

        except Exception:
            return {"error": "Failed to generate monthly summary"}

    def get_heatmap_data(self, days: int = 14) -> dict:
        """Generate heatmap data for activity patterns by hour of day and day of week."""
        sightings_file = DATA_DIR / "sightings.jsonl"

        if not sightings_file.exists():
            return {"error": "No sightings data"}

        try:
            lines = sightings_file.read_text().strip().split("\n")
            visits_data = []
            for line in lines:
                if not line.strip():
                    continue
                try:
                    visits_data.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

            now = datetime.now(timezone.utc)
            cutoff = now - timedelta(days=days)

            # 7 days x 24 hours heatmap
            heatmap = [[0 for _ in range(24)] for _ in range(7)]
            day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

            for visit in visits_data:
                start_str = visit.get("start", "")
                if not start_str:
                    continue
                try:
                    start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    continue

                if start_dt < cutoff:
                    continue

                # day_of_week: 0=Monday ... 6=Sunday
                dow = start_dt.weekday()
                hour = start_dt.hour
                heatmap[dow][hour] += 1

            return {
                "heatmap": heatmap,
                "days": day_names,
                "hours": [f"{h:02d}:00" for h in range(24)],
                "days_range": days,
            }

        except Exception:
            return {"error": "Failed to generate heatmap"}

    def get_alert_summary(self, days: int = 7) -> dict:
        """Summarize alerts from the past N days."""
        # Read alert rules fires if available
        fires_file = DATA_DIR / "alert_fires.json"

        result = {
            "total_fires": 0,
            "rules_triggered": {},
            "recent_fires": [],
        }

        try:
            if fires_file.exists():
                fires = json.loads(fires_file.read_text())
                now = time.time()
                cutoff = now - (days * 86400)

                recent = []
                for rule_id, fire_time in sorted(fires.items(), key=lambda x: x[1], reverse=True):
                    if fire_time >= cutoff:
                        recent.append({"rule_id": rule_id, "fired_at": datetime.fromtimestamp(fire_time, tz=timezone.utc).isoformat()})

                result["total_fires"] = len(recent)
                result["recent_fires"] = recent[:20]  # Last 20 fires

        except Exception:
            pass

        return result


# Import time for alert summary
import time as _time


# Singleton instance
analytics_engine = AnalyticsEngine()
