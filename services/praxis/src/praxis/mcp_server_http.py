import os
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .core import PraxisCore

app = FastAPI(title="Praxis", description="Hierarchical planning for the Noesis AGI stack")

_data_dir = os.getenv("PRAXIS_DATA_DIR", "/data")
_core = PraxisCore(db_path=os.path.join(_data_dir, "praxis.db"))


class DecomposeRequest(BaseModel):
    goal: str
    parent_plan_id: Optional[str] = None


class AddStepRequest(BaseModel):
    plan_id: str
    description: str
    tool_call: Optional[str] = None
    risk_score: float = 0.0
    parent_step_id: Optional[str] = None


class CommitStepRequest(BaseModel):
    plan_id: str
    step_id: str
    outcome: str
    success: bool


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/tools/decompose_goal")
def decompose_goal(req: DecomposeRequest):
    depth = 0
    if req.parent_plan_id:
        try:
            parent = _core.get_plan(req.parent_plan_id)
            depth = parent.depth + 1
        except KeyError:
            raise HTTPException(status_code=404, detail="Parent plan not found")
    return _core.decompose(req.goal, depth=depth, parent_plan_id=req.parent_plan_id).model_dump()


@app.post("/tools/evaluate_step")
def evaluate_step(req: AddStepRequest):
    """Propose a candidate step; returns the step with its computed ToT score."""
    try:
        return _core.add_step(
            req.plan_id, req.description, req.tool_call, req.risk_score, req.parent_step_id
        ).model_dump()
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/tools/get_next_step/{plan_id}")
def get_next_step(plan_id: str):
    try:
        step = _core.get_next_step(plan_id)
        return step.model_dump() if step else {"step": None, "message": "All steps completed"}
    except KeyError:
        raise HTTPException(status_code=404, detail="Plan not found")


@app.get("/tools/best_path/{plan_id}")
def best_path(plan_id: str, k: int = 1):
    try:
        paths = _core.best_path(plan_id, k=k)
        return {"paths": [[s.model_dump() for s in path] for path in paths]}
    except KeyError:
        raise HTTPException(status_code=404, detail="Plan not found")


@app.post("/tools/commit_step")
def commit_step(req: CommitStepRequest):
    try:
        return _core.commit_step(req.plan_id, req.step_id, req.outcome, req.success).model_dump()
    except KeyError:
        raise HTTPException(status_code=404, detail="Plan or step not found")


@app.post("/tools/backtrack/{plan_id}")
def backtrack(plan_id: str):
    try:
        alternatives = _core.backtrack(plan_id)
        return {"alternatives": [s.model_dump() for s in alternatives]}
    except KeyError:
        raise HTTPException(status_code=404, detail="Plan not found")


@app.get("/tools/verify_plan/{plan_id}")
def verify_plan(plan_id: str):
    try:
        ok, message = _core.verify_plan(plan_id)
        return {"verified": ok, "message": message}
    except KeyError:
        raise HTTPException(status_code=404, detail="Plan not found")


@app.get("/tools/get_plan/{plan_id}")
def get_plan(plan_id: str):
    try:
        return _core.get_plan(plan_id).model_dump()
    except KeyError:
        raise HTTPException(status_code=404, detail="Plan not found")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
