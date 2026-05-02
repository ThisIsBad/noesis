from datetime import datetime

from noesis_schemas import (
    CalibrationReport,
    CompetenceMap,
    DomainCompetence,
    Prediction,
)


class EpistemeCore:
    def __init__(self) -> None:
        self._predictions: dict[str, Prediction] = {}

    def log_prediction(
        self,
        claim: str,
        confidence: float,
        domain: str | None = None,
    ) -> Prediction:
        pred = Prediction(claim=claim, confidence=confidence, domain=domain)
        self._predictions[pred.prediction_id] = pred
        return pred

    def log_outcome(self, prediction_id: str, correct: bool) -> Prediction:
        pred = self._predictions[prediction_id]
        pred.correct = correct
        pred.resolved_at = datetime.utcnow()
        return pred

    def get_calibration(self, domain: str | None = None) -> CalibrationReport:
        resolved = [
            p
            for p in self._predictions.values()
            if p.correct is not None and (domain is None or p.domain == domain)
        ]
        if not resolved:
            return CalibrationReport(
                domain=domain,
                sample_size=0,
                ece=0.0,
                brier_score=0.0,
                bias=0.0,
                sharpness=0.0,
            )

        n = len(resolved)
        brier = (
            sum((p.confidence - (1.0 if p.correct else 0.0)) ** 2 for p in resolved) / n
        )
        bias = sum(p.confidence - (1.0 if p.correct else 0.0) for p in resolved) / n
        sharpness = sum(abs(p.confidence - 0.5) for p in resolved) / n

        # Simplified ECE: single bucket (avg confidence vs avg accuracy). The
        # MCP tool returns this directly; a bucketed ECE can be layered on
        # later without changing the schema.
        accuracy = sum(1 for p in resolved if p.correct) / n
        avg_conf = sum(p.confidence for p in resolved) / n
        ece = abs(avg_conf - accuracy)

        return CalibrationReport(
            domain=domain,
            sample_size=n,
            ece=ece,
            brier_score=brier,
            bias=bias,
            sharpness=sharpness,
        )

    def should_escalate(self, confidence: float, domain: str | None = None) -> bool:
        report = self.get_calibration(domain)
        # Escalate on low confidence OR when the history shows systematic
        # overconfidence in this domain (bias > 0.2) at high confidence.
        return confidence < 0.5 or (report.bias > 0.2 and confidence > 0.7)

    def get_competence_map(
        self,
        min_samples: int = 10,
        weakness_threshold: float = 0.15,
    ) -> CompetenceMap:
        resolved = [
            p
            for p in self._predictions.values()
            if p.correct is not None and p.domain is not None
        ]
        by_domain: dict[str, list[Prediction]] = {}
        for p in resolved:
            assert p.domain is not None  # narrowed above
            by_domain.setdefault(p.domain, []).append(p)

        domain_stats: list[DomainCompetence] = []
        for domain, preds in by_domain.items():
            n = len(preds)
            accuracy = sum(1 for p in preds if p.correct) / n
            avg_conf = sum(p.confidence for p in preds) / n
            brier = (
                sum((p.confidence - (1.0 if p.correct else 0.0)) ** 2 for p in preds)
                / n
            )
            domain_stats.append(
                DomainCompetence(
                    domain=domain,
                    sample_size=n,
                    accuracy=accuracy,
                    avg_confidence=avg_conf,
                    confidence_gap=avg_conf - accuracy,
                    brier_score=brier,
                )
            )

        # Only domains with enough signal are eligible for labels.
        eligible = [d for d in domain_stats if d.sample_size >= min_samples]
        weaknesses = [
            d.domain
            for d in sorted(eligible, key=lambda d: abs(d.confidence_gap), reverse=True)
            if abs(d.confidence_gap) >= weakness_threshold
        ]
        strengths = [
            d.domain
            for d in sorted(eligible, key=lambda d: d.accuracy, reverse=True)
            if abs(d.confidence_gap) < weakness_threshold and d.accuracy >= 0.7
        ]
        return CompetenceMap(
            total_predictions=len(resolved),
            domains=sorted(domain_stats, key=lambda d: d.domain),
            weaknesses=weaknesses,
            strengths=strengths,
        )
