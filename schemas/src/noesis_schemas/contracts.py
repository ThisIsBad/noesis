import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from .certificates import ProofCertificate


class GoalConstraint(BaseModel):
    description: str
    formal: Optional[str] = None  # SMT-LIB / Z3 expression


class GoalContract(BaseModel):
    goal_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    description: str
    preconditions: list[GoalConstraint] = Field(default_factory=list)
    postconditions: list[GoalConstraint] = Field(default_factory=list)
    registered_at: datetime = Field(default_factory=datetime.utcnow)
    certificate: Optional[ProofCertificate] = None
    active: bool = True
