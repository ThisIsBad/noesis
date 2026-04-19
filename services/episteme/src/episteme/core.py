from datetime import datetime
from typing import Optional

from noesis_schemas import CalibrationReport, Prediction


class EpistemeCore:
    def __init__(self) -> None:
        self._predictions: dict[str, Prediction] = {}

    def log_prediction(
        self,
        claim: str,
        confidence: float,
        domain: Optional[str] = None,
    ) -> Prediction:
        pred = Prediction(claim=claim, confidence=confidence, domain=domain)
        self._predictions[pred.prediction_id] = pred
        return pred

    def log_outcome(self, prediction_id: str, correct: bool) -> Prediction:
        pred = self._predictions[prediction_id]
        pred.correct = correct
        pred.resolved_at = datetime.utcnow()
        return pred

    def get_calibration(self, domain: Optional[str] = None) -> CalibrationReport:
        resolved = [
            p for p in self._predictions.values()
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
        brier = sum(
            (p.confidence - (1.0 if p.correct else 0.0)) ** 2 for p in resolved
        ) / n
        bias = sum(
            p.confidence - (1.0 if p.correct else 0.0) for p in resolved
        ) / n
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

    def should_escalate(
        self, confidence: float, domain: Optional[str] = None
    ) -> bool:
        report = self.get_calibration(domain)
        # Escalate on low confidence OR when the history shows systematic
        # overconfidence in this domain (bias > 0.2) at high confidence.
        return confidence < 0.5 or (report.bias > 0.2 and confidence > 0.7)
