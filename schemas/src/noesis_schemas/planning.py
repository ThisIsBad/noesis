import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from .certificates import ProofCertificate
from .contracts import GoalContract


class StepStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class PlanStep(BaseModel):
    step_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    description: str
    tool_call: Optional[str] = None
    status: StepStatus = StepStatus.PENDING
    outcome: Optional[str] = None
    executed_at: Optional[datetime] = None
    risk_score: float = Field(ge=0.0, le=1.0, default=0.0)


class Plan(BaseModel):
    plan_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    goal: str
    steps: list[PlanStep] = Field(default_factory=list)
    contract: Optional[GoalContract] = None
    certificate: Optional[ProofCertificate] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    depth: int = 0
    parent_plan_id: Optional[str] = None
