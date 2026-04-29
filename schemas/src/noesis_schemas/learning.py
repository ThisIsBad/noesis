import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from .certificates import ProofCertificate


class Lesson(BaseModel):
    lesson_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    context: str
    action_taken: str
    outcome: str
    success: bool
    lesson_text: str
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    domain: Optional[str] = None


class Skill(BaseModel):
    skill_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str
    strategy: str
    verified: bool = False
    certificate: Optional[ProofCertificate] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    success_rate: float = Field(ge=0.0, le=1.0, default=0.0)
    use_count: int = 0
    domain: Optional[str] = None
