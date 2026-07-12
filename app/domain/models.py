from typing import Literal

from pydantic import BaseModel, Field

DIM_VIEWER = "dim_viewer"


class Viewer(BaseModel):
    viewer_id: str
    age_bracket: str = "unknown"
    gender: str = "unknown"
    country: str = "unknown"


DIM_CREATIVE = "dim_creative"


class Creative(BaseModel):
    creative_id: str
    title: str = "unknown"
    brand: str = "unknown"
    duration_ms: int | None = None


DIM_SESSION = "dim_session"


class Session(BaseModel):
    session_id: str
    viewer_id: str
    creative_id: str
    started_at: str = "unknown"


FACT_EXPRESSION = "fact_expression"


class Expression(BaseModel):
    session_id: str
    viewer_id: str
    creative_id: str
    timestamp: int            # ms from creative start, pre-normalized upstream
    channel: Literal["face", "voice"]
    expression: str
    score: float = Field(ge=0.0, le=1.0)
