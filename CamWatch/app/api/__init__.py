"""FastAPI application with REST endpoints and WebSocket support."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os

DATA_DIR = os.environ.get("DATA_PATH", "/data")


def create_app() -> FastAPI:
    app = FastAPI(
        title="CamWatch API",
        description="Self-hosted camera service API",
        version="2.0.0",
    )

    # CORS for PWA and external clients
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Import routes (avoid circular imports)
    from api.routes import cameras, clips, visits, settings as settings_routes, users, alerts, health

    app.include_router(cameras.router, prefix="/api", tags=["cameras"])
    app.include_router(clips.router, prefix="/api", tags=["clips"])
    app.include_router(visits.router, prefix="/api", tags=["visits"])
    app.include_router(settings_routes.router, prefix="/api", tags=["settings"])
    app.include_router(users.router, prefix="/api/users", tags=["users"])
    app.include_router(alerts.router, prefix="/api/alerts", tags=["alerts"])
    app.include_router(health.router, prefix="/api", tags=["health"])

    # WebSocket endpoint
    from fastapi import APIRouter
    from api.websocket import websocket_manager
    import json as _json

    ws_router = APIRouter()

    @ws_router.websocket("/ws")
    async def websocket_endpoint(websocket):
        await websocket_manager.connect(websocket)
        try:
            while True:
                data = await websocket.receive_text()
                msg = _json.loads(data) if data else {}
                await websocket_manager.handle_message(websocket, msg)
        except Exception:
            pass
        finally:
            await websocket_manager.disconnect(websocket)

    app.include_router(ws_router)

    return app
