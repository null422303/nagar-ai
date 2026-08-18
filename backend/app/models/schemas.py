from pydantic import BaseModel, Field
from typing import Optional, List


class VisionResult(BaseModel):
    category: str = "other"
    severity: int = Field(ge=1, le=5)
    extent: str = ""
    vision_fingerprint: str = ""
    location_text: str = ""
    category_label: Optional[str] = None
    category_color: Optional[str] = None
    tags: List[str] = []
    is_spam: bool = False


class ExtractedComplaint(BaseModel):
    category: str = "other"
    severity: int = Field(ge=1, le=5)
    location_text: str = ""
    clean_summary: str = ""
    urgent_hint: bool = False
    category_label: Optional[str] = None
    category_color: Optional[str] = None
    tags: List[str] = []
    is_spam: bool = False


class ComplaintIn(BaseModel):
    text: Optional[str] = None
    channel: str = "text"  # text | voice | photo | mix


class ComplaintOut(BaseModel):
    id: int
    channel: str
    category: str
    severity: int
    summary: str
    lat: Optional[float] = None
    lng: Optional[float] = None
    loc_source: str = "needs_geo"
    issue_id: Optional[int] = None
    notify_link: str = ""
    status: str = "open"
    created_at: str = ""


class IssueOut(BaseModel):
    id: int
    category: str
    severity: int
    summary: str
    affected_count: int
    priority_score: float
    priority_reason: dict = {}
    status: str = "open"
    dept: Optional[str] = None
    sla_deadline: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    members: List[dict] = []
