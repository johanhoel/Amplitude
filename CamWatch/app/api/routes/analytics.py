"""Analytics API endpoints."""
from fastapi import APIRouter, HTTPException, Header, Query
from typing import Optional

from api.auth import decode_jwt_token

router = APIRouter()


def _require_operator(auth: Optional[str]) -> bool:
    if not auth:
        return False
    payload = decode_jwt_token(auth.replace("Bearer ", ""))
    return bool(payload and payload.get("role") in ("admin", "operator"))


@router.get("/analytics/weekly-report")
async def get_weekly_report(authorization: Optional[str] = Header(None)):
    """Get weekly activity report."""
    if not _require_operator(authorization):
        raise HTTPException(401, "Operator+ required")

    try:
        from api.analytics_engine import analytics_engine
        report = analytics_engine.get_weekly_report()
        return report
    except Exception as e:
        raise HTTPException(500, f"Failed to get weekly report: {str(e)}")


@router.get("/analytics/monthly-summary")
async def get_monthly_summary(authorization: Optional[str] = Header(None)):
    """Get monthly summary for the past 6 months."""
    if not _require_operator(authorization):
        raise HTTPException(401, "Operator+ required")

    try:
        from api.analytics_engine import analytics_engine
        summary = analytics_engine.get_monthly_summary()
        return summary
    except Exception as e:
        raise HTTPException(500, f"Failed to get monthly summary: {str(e)}")


@router.get("/analytics/heatmap")
async def get_heatmap(days: int = Query(14, ge=1, le=90), authorization: Optional[str] = Header(None)):
    """Get activity heatmap data for the past N days."""
    if not _require_operator(authorization):
        raise HTTPException(401, "Operator+ required")

    try:
        from api.analytics_engine import analytics_engine
        heatmap = analytics_engine.get_heatmap_data(days)
        return heatmap
    except Exception as e:
        raise HTTPException(500, f"Failed to get heatmap: {str(e)}")


@router.get("/analytics/alert-summary")
async def get_alert_summary(days: int = Query(7, ge=1, le=90), authorization: Optional[str] = Header(None)):
    """Get alert summary for the past N days."""
    if not _require_operator(authorization):
        raise HTTPException(401, "Operator+ required")

    try:
        from api.analytics_engine import analytics_engine
        summary = analytics_engine.get_alert_summary(days)
        return summary
    except Exception as e:
        raise HTTPException(500, f"Failed to get alert summary: {str(e)}")


@router.get("/analytics/overview")
async def get_analytics_overview(authorization: Optional[str] = Header(None)):
    """Get a quick analytics overview combining multiple data points."""
    if not _require_operator(authorization):
        raise HTTPException(401, "Operator+ required")

    try:
        from api.analytics_engine import analytics_engine

        weekly = analytics_engine.get_weekly_report()

        # Calculate week-over-week change
        days_data = weekly.get("visits_per_day", {})
        sorted_days = sorted(days_data.keys())

        this_week_visits = sum(days_data.values()) if sorted_days else 0

        # Get last 7 days of visits
        total_visits = this_week_visits

        return {
            "total_visits_this_week": total_visits,
            "unique_people_seen": weekly.get("people_count", 0),
            "packages_delivered": len(weekly.get("packages", [])),
            "top_camera": weekly.get("top_cameras", [{}])[0].get("camera", "") if weekly.get("top_cameras") else "",
            "visits_by_hour": weekly.get("visits_per_hour", {}),
        }
    except Exception as e:
        raise HTTPException(500, f"Failed to get overview: {str(e)}")
