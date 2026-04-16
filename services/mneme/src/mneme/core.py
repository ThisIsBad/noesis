from typing import Optional
from noesis_schemas import Memory, MemoryType, ProofCertificate


class MnemeCore:
    def __init__(self) -> None:
        # Production: replace with ChromaDB + SQLite persistence
        self._memories: dict[str, Memory] = {}

    def store(
        self,
        content: str,
        memory_type: MemoryType,
        confidence: float = 0.5,
        certificate: Optional[ProofCertificate] = None,
        tags: Optional[list[str]] = None,
        source: Optional[str] = None,
    ) -> Memory:
        mem = Memory(
            content=content,
            memory_type=memory_type,
            confidence=confidence,
            certificate=certificate,
            proven=certificate.proven if certificate else False,
            tags=tags or [],
            source=source,
        )
        self._memories[mem.memory_id] = mem
        return mem

    def retrieve(self, query: str, k: int = 5, min_confidence: float = 0.0) -> list[Memory]:
        # Stub: naive substring match. Production: ChromaDB k-nearest.
        results = [
            m for m in self._memories.values()
            if query.lower() in m.content.lower() and m.confidence >= min_confidence
        ]
        return results[:k]

    def forget(self, memory_id: str, reason: str) -> bool:
        if memory_id in self._memories:
            del self._memories[memory_id]
            return True
        return False

    def list_proven(self) -> list[Memory]:
        return [m for m in self._memories.values() if m.proven]

    def consolidate(self) -> int:
        # Stub: returns number of consolidated entries
        return 0
