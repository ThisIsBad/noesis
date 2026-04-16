from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
from .core import EmpiriaCore

app = FastAPI(title="Empiria", description="Experience accumulation for the Noesis AGI stack")
_core = EmpiriaCore()


class RecordRequest(BaseModel):
    context: str
    action_taken: str
    outcome: str
    success: bool
    lesson_text: str
    confidence: float = 0.5
    domain: Optional[str] = None


class RetrieveRequest(BaseModel):
    context: str
    k: int = 5
    domain: Optional[str] = None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/tools/record_experience")
def record_experience(req: RecordRequest):
    return _core.record(**req.model_dump()).model_dump()


@app.post("/tools/retrieve_lessons")
def retrieve_lessons(req: RetrieveRequest):
    return [l.model_dump() for l in _core.retrieve(req.context, req.k, req.domain)]


@app.get("/tools/successful_patterns")
def successful_patterns(domain: Optional[str] = None):
    return [l.model_dump() for l in _core.successful_patterns(domain)]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
