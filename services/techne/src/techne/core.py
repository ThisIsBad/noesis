from noesis_schemas import ProofCertificate, Skill


class TechneCore:
    def __init__(self) -> None:
        # Production: ChromaDB for semantic skill retrieval
        self._skills: dict[str, Skill] = {}

    def store(
        self,
        name: str,
        description: str,
        strategy: str,
        certificate: ProofCertificate | None = None,
        domain: str | None = None,
    ) -> Skill:
        skill = Skill(
            name=name,
            description=description,
            strategy=strategy,
            verified=certificate.verified if certificate else False,
            certificate=certificate,
            domain=domain,
        )
        self._skills[skill.skill_id] = skill
        return skill

    def retrieve(
        self,
        query: str,
        k: int = 5,
        verified_only: bool = False,
    ) -> list[Skill]:
        # Stub: substring match. Production: ChromaDB k-nearest.
        needle = query.lower()
        results = [
            skill for skill in self._skills.values()
            if (needle in skill.description.lower() or needle in skill.name.lower())
            and (not verified_only or skill.verified)
        ]
        return sorted(results, key=lambda skill: skill.success_rate, reverse=True)[:k]

    def record_use(self, skill_id: str, success: bool) -> Skill:
        skill = self._skills[skill_id]
        total = skill.use_count + 1
        delta = 1.0 if success else 0.0
        skill.success_rate = (
            skill.success_rate * skill.use_count + delta
        ) / total
        skill.use_count = total
        return skill
