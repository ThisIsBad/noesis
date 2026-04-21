from noesis_schemas import Lesson


class EmpiriaCore:
    def __init__(self) -> None:
        # Production: ChromaDB for semantic lesson retrieval.
        self._lessons: dict[str, Lesson] = {}

    def record(
        self,
        context: str,
        action_taken: str,
        outcome: str,
        success: bool,
        lesson_text: str,
        confidence: float = 0.5,
        domain: str | None = None,
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

    def retrieve(
        self,
        context: str,
        k: int = 5,
        domain: str | None = None,
    ) -> list[Lesson]:
        # Stub: substring match. Production: ChromaDB k-nearest on context embedding.
        needle = context.lower()
        results = [
            lesson
            for lesson in self._lessons.values()
            if needle in lesson.context.lower()
            and (domain is None or lesson.domain == domain)
        ]
        results.sort(key=lambda lesson: lesson.confidence, reverse=True)
        return results[:k]

    def successful_patterns(
        self, domain: str | None = None
    ) -> list[Lesson]:
        return [
            lesson
            for lesson in self._lessons.values()
            if lesson.success and (domain is None or lesson.domain == domain)
        ]
