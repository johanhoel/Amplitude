"""FastAPI server entry point for CamWatch API."""
import os, sys
from pathlib import Path

app_dir = Path(__file__).parent / "app"
if str(app_dir) not in sys.path:
    sys.path.insert(0, str(app_dir))

os.environ.setdefault("DATA_PATH", "/data")
os.environ.setdefault("RECORDINGS_PATH", "/recordings")
os.environ.setdefault("PHOTOS_PATH", "/photos")

from api import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("API_PORT", "8081"))
    print(f"Starting CamWatch API server on port {port}")
    import uvicorn
    uvicorn.run("api_server:app", host="0.0.0.0", port=port, reload=False, log_level="info")
