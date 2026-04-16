from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
from noesis_schemas import ProofCertificate
from .core import TechneCore

app = FastAPI(title="Techne", description="Verified skill library for the Noesis AGI stack")
_core = TechneCore()


class StoreSkillRequest(BaseModel):
    name: str
    description: str
    strategy: str
    certificate: Optional[ProofCertificate] = None
    domain: Optional[str] = None


class RetrieveSkillRequest(BaseModel):
    query: str
    k: int = 5
    verified_only: bool = False


class RecordUseRequest(BaseModel):
    skill_id: str
    success: bool


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/tools/store_skill")
def store_skill(req: StoreSkillRequest):
    return _core.store(**req.model_dump()).model_dump()


@app.post("/tools/retrieve_skill")
def retrieve_skill(req: RetrieveSkillRequest):
    return [s.model_dump() for s in _core.retrieve(req.query, req.k, req.verified_only)]


@app.post("/tools/record_use")
def record_use(req: RecordUseRequest):
    try:
        return _core.record_use(req.skill_id, req.success).model_dump()
    except KeyError:
        raise HTTPException(status_code=404, detail="Skill not found")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
