from typing import Optional
from noesis_schemas import Lesson


class EmpiriaCore:
    def __init__(self) -> None:
        # Production: ChromaDB for semantic lesson retrieval
        self._lessons: dict[str, Lesson] = {}

    def record(
        self,
        context: str,
        action_taken: str,
        outcome: str,
        success: bool,
        lesson_text: str,
        confidence: float = 0.5,
        domain: Optional[str] = None,
    ) -> Lesson:
        lesson = Lesson(
            context=context,
            action_taken=action_taken,
            outcome=outcome,
            success=success,
            lesson_text=lesson_text,
            confidence=confidence,
            domain=domain,
        )
        self._lessons[lesson.lesson_id] = lesson
        return lesson

    def retrieve(self, context: str, k: int = 5, domain: Optional[str] = None) -> list[Lesson]:
        # Stub: substring match. Production: ChromaDB k-nearest on context embedding.
        results = [
            l for l in self._lessons.values()
            if context.lower() in l.context.lower() and (domain is None or l.domain == domain)
        ]
        return sorted(results, key=lambda l: l.confidence, reverse=True)[:k]

    def successful_patterns(self, domain: Optional[str] = None) -> list[Lesson]:
        return [
            l for l in self._lessons.values()
            if l.success and (domain is None or l.domain == domain)
        ]
