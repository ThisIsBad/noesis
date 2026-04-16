from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field
import uuid

from .certificates import ProofCertificate


class MemoryType(str, Enum):
    EPISODIC = "episodic"   # what happened when
    SEMANTIC = "semantic"   # what is known/believed


class Memory(BaseModel):
    memory_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    content: str
    memory_type: MemoryType
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    accessed_at: Optional[datetime] = None
    certificate: Optional[ProofCertificate] = None
    proven: bool = False
    tags: list[str] = Field(default_factory=list)
    source: Optional[str] = None
