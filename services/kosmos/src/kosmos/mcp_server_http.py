from fastapi import FastAPI
from pydantic import BaseModel
from typing import Any, Optional
from .core import KosmosCore

app = FastAPI(title="Kosmos", description="Causal world model for the Noesis AGI stack")
_core = KosmosCore()


class CausalEdgeRequest(BaseModel):
    cause: str
    effect: str
    strength: float = 1.0


class InterventionRequest(BaseModel):
    variable: str
    value: Any


class CounterfactualRequest(BaseModel):
    cause: str
    effect: str


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/tools/add_causal_edge")
def add_causal_edge(req: CausalEdgeRequest):
    _core.add_edge(req.cause, req.effect, req.strength)
    return {"added": f"{req.cause} -> {req.effect}"}


@app.post("/tools/compute_intervention")
def compute_intervention(req: InterventionRequest):
    return _core.compute_intervention(req.variable, req.value)


@app.post("/tools/counterfactual")
def counterfactual(req: CounterfactualRequest):
    return {"strength": _core.counterfactual(req.cause, req.effect)}


@app.get("/tools/query_causes/{effect}")
def query_causes(effect: str):
    return {"causes": _core.query_causes(effect)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
