from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
from noesis_schemas import MemoryType, ProofCertificate
from .core import MnemeCore

app = FastAPI(title="Mneme", description="Persistent memory for the Noesis AGI stack")
_core = MnemeCore()


class StoreRequest(BaseModel):
    content: str
    memory_type: MemoryType
    confidence: float = 0.5
    certificate: Optional[ProofCertificate] = None
    tags: list[str] = []
    source: Optional[str] = None


class RetrieveRequest(BaseModel):
    query: str
    k: int = 5
    min_confidence: float = 0.0


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/tools/store_memory")
def store_memory(req: StoreRequest):
    return _core.store(**req.model_dump()).model_dump()


@app.post("/tools/retrieve_memory")
def retrieve_memory(req: RetrieveRequest):
    return [m.model_dump() for m in _core.retrieve(req.query, req.k, req.min_confidence)]


@app.delete("/tools/forget/{memory_id}")
def forget(memory_id: str, reason: str = ""):
    if not _core.forget(memory_id, reason):
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"forgotten": memory_id}


@app.get("/tools/list_proven_beliefs")
def list_proven():
    return [m.model_dump() for m in _core.list_proven()]


@app.post("/tools/consolidate")
def consolidate():
    return {"consolidated": _core.consolidate()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
