from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
import uuid


class Prediction(BaseModel):
    prediction_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    claim: str
    confidence: float = Field(ge=0.0, le=1.0)
    domain: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = None
    correct: Optional[bool] = None


class CalibrationReport(BaseModel):
    domain: Optional[str] = None
    sample_size: int
    ece: float       # Expected Calibration Error
    brier_score: float
    bias: float      # positive = overconfident
    sharpness: float
    computed_at: datetime = Field(default_factory=datetime.utcnow)
