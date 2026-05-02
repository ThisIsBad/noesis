import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class TraceSpan(BaseModel):
    trace_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    span_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    parent_span_id: Optional[str] = None
    service: str
    operation: str
    started_at: datetime = Field(default_factory=datetime.utcnow)
    ended_at: Optional[datetime] = None
    duration_ms: Optional[float] = None
    success: Optional[bool] = None
    metadata: dict[str, str] = Field(default_factory=dict)
