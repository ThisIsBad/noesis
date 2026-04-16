from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field
import uuid


class ProofCertificate(BaseModel):
    certificate_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    claim: str
    proven: bool
    method: Literal["z3", "lean4", "argument", "assumption"]
    issued_at: datetime = Field(default_factory=datetime.utcnow)
    proof_detail: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
