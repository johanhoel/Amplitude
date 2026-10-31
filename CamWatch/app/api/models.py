"""Pydantic models for API request/response validation."""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
import re


class CameraCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    rtsp_url: str = Field(..., description="RTSP stream URL")
    detect_url: Optional[str] = None
    enabled: bool = True

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        if not re.match(r"^[a-z0-9][a-z0-9_]{0,23}$", v):
            raise ValueError("Name must be lowercase alphanumeric with underscores, max 24 chars")
        return v

    @field_validator("rtsp_url")
    @classmethod
    def validate_rtsp(cls, v):
        if not v.startswith(("rtsp://", "rtsps://")):
            raise ValueError("URL must start with rtsp:// or rtsps://")
        return v


class CameraUpdate(BaseModel):
    name: Optional[str] = None
    rtsp_url: Optional[str] = None
    detect_url: Optional[str] = None
    enabled: Optional[bool] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        if v is not None and not re.match(r"^[a-z0-9][a-z0-9_]{0,23}$", v):
            raise ValueError("Name must be lowercase alphanumeric with underscores, max 24 chars")
        return v


class CameraResponse(BaseModel):
    slot: int
    name: str
    rtsp_url: str
    detect_url: Optional[str] = None
    enabled: bool
    online: bool = False


class ClipMetadata(BaseModel):
    day: str
    stem: str
    camera: str
    start: Optional[str] = None
    end: Optional[str] = None
    labels: Dict = {}
    zones: List = []
    loitering: bool = False
    test: bool = False
    plates: List = []
    vehicles: List = []
    faces_seen: int = 0
    unknown_faces: int = 0
    starred: bool = False


class ClipListResponse(BaseModel):
    clips: List[ClipMetadata]
    total: int
    page: int
    per_page: int


class VisitorInfo(BaseModel):
    kind: str
    name: Optional[str] = None
    source: str
    detail: Optional[str] = None


class VisitResponse(BaseModel):
    id: int
    camera: str
    day: str
    stem: str
    started_at: str
    ended_at: Optional[str] = None
    duration_s: Optional[int] = None
    direction: Optional[str] = None
    who: str
    visitors: List[VisitorInfo] = []
    clip_deleted: bool = False


class VisitListResponse(BaseModel):
    visits: List[VisitResponse]
    total: int
    page: int
    per_page: int


class NtfyConfig(BaseModel):
    url: str = ""
    topic: str = ""
    status_topic: str = ""
    token: str = ""
    user: str = ""
    password: str = ""
    priority: str = "high"


class IntegrationConfig(BaseModel):
    mqtt_host: str = ""
    mqtt_port: int = 1883
    mqtt_user: str = ""
    mqtt_password: str = ""
    ha_webhook_url: str = ""


class SettingsResponse(BaseModel):
    mode: str
    schedule: str = "22:00-07:00"
    loiter_seconds: int = 30
    zones: List = []
    plates: List = []
    lan_no_auth: bool = False
    trusted_networks: List = []
    ntfy: NtfyConfig = Field(default_factory=NtfyConfig)
    integration: IntegrationConfig = Field(default_factory=IntegrationConfig)
    cameras: List = []


class SettingsUpdate(BaseModel):
    mode: Optional[str] = None
    schedule: Optional[str] = None
    loiter_seconds: Optional[int] = None
    zones: Optional[List] = None
    plates: Optional[List] = None
    lan_no_auth: Optional[bool] = None


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=6)
    role: str = "viewer"

    @field_validator("role")
    @classmethod
    def validate_role(cls, v):
        if v not in ("admin", "operator", "viewer"):
            raise ValueError("Role must be admin, operator, or viewer")
        return v


class UserResponse(BaseModel):
    id: str
    username: str
    role: str
    created_at: str


class LoginRequest(BaseModel):
    username: str
    password: str


class AlertRuleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    enabled: bool = True
    conditions: Dict
    actions: Dict
    cooldown_seconds: int = 300


class AlertRuleResponse(BaseModel):
    id: str
    name: str
    enabled: bool
    conditions: Dict
    actions: Dict
    cooldown_seconds: int


class CameraHealth(BaseModel):
    camera: str
    online: bool
    recording: bool = False
    last_frame_at: Optional[str] = None
    health_score: int = 100


class HealthStatus(BaseModel):
    version: Dict = {}
    cameras: List[CameraHealth] = []
    disk: Dict = {}
    armed: bool = False
    mode: str = "armed"
