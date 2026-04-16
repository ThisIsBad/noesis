from fastapi import FastAPI
from noesis_schemas import GoalContract
from .core import TelosCore

app = FastAPI(title="Telos", description="Goal stability monitoring for the Noesis AGI stack")
_core = TelosCore()


class CheckRequest:
    pass


from pydantic import BaseModel


class AlignmentRequest(BaseModel):
    action_description: str


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/tools/register_goal")
def register_goal(contract: GoalContract):
    return _core.register(contract).model_dump()


@app.post("/tools/check_action_alignment")
def check_action_alignment(req: AlignmentRequest):
    result = _core.check_alignment(req.action_description)
    return {"aligned": result.aligned, "drift_score": result.drift_score, "reason": result.reason}


@app.get("/tools/get_drift_score")
def get_drift_score(window: int = 20):
    return {"drift_score": _core.get_drift_score(window)}


@app.get("/tools/list_active_goals")
def list_active_goals():
    return [g.model_dump() for g in _core.list_active()]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
