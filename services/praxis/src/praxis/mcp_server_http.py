from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
from .core import PraxisCore

app = FastAPI(title="Praxis", description="Hierarchical planning for the Noesis AGI stack")
_core = PraxisCore()


class DecomposeRequest(BaseModel):
    goal: str
    parent_plan_id: Optional[str] = None


class AddStepRequest(BaseModel):
    plan_id: str
    description: str
    tool_call: Optional[str] = None
    risk_score: float = 0.0


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
    try:
        return _core.add_step(req.plan_id, req.description, req.tool_call, req.risk_score).model_dump()
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
        reset = _core.backtrack(plan_id)
        return [s.model_dump() for s in reset]
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
