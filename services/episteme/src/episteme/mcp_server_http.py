from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
from .core import EpistemeCore

app = FastAPI(title="Episteme", description="Metacognition and calibration for the Noesis AGI stack")
_core = EpistemeCore()


class PredictionRequest(BaseModel):
    claim: str
    confidence: float
    domain: Optional[str] = None


class OutcomeRequest(BaseModel):
    prediction_id: str
    correct: bool


class EscalateRequest(BaseModel):
    confidence: float
    domain: Optional[str] = None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/tools/log_prediction")
def log_prediction(req: PredictionRequest):
    return _core.log_prediction(req.claim, req.confidence, req.domain).model_dump()


@app.post("/tools/log_outcome")
def log_outcome(req: OutcomeRequest):
    try:
        return _core.log_outcome(req.prediction_id, req.correct).model_dump()
    except KeyError:
        raise HTTPException(status_code=404, detail="Prediction not found")


@app.get("/tools/get_calibration")
def get_calibration(domain: Optional[str] = None):
    return _core.get_calibration(domain).model_dump()


@app.post("/tools/should_escalate")
def should_escalate(req: EscalateRequest):
    return {"escalate": _core.should_escalate(req.confidence, req.domain)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
