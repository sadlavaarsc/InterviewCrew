import uuid
from typing import Dict

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from interview_crew.state import InterviewState
from interview_crew.orchestrator.engine import Orchestrator, StepResult

app = FastAPI(title="InterviewCrew API", version="0.1.0")

# In-memory session storage
_sessions: Dict[str, Orchestrator] = {}


class CreateSessionRequest(BaseModel):
    max_turns: int = Field(default=6, ge=1, le=50)
    candidate_response: str = ""
    resume_path: str | None = None
    jd_path: str | None = None


class CreateSessionResponse(BaseModel):
    session_id: str
    status: str


class StepRequest(BaseModel):
    candidate_response: str


class StepResponse(BaseModel):
    agent: str
    question: str
    finished: bool
    report: str = ""


class SessionStateResponse(BaseModel):
    session_id: str
    turn: int
    max_turns: int
    status: str
    current_agent: str
    last_question: str
    candidate_response: str
    resume_text: str
    jd_text: str
    unified_history: list
    transfer_queue: list
    competency_history: list
    total_budget_consumed: int


def _state_to_dict(state: InterviewState) -> dict:
    """Serialize InterviewState to a JSON-friendly dict."""
    return {
        "session_id": state.session_id,
        "turn": state.turn,
        "max_turns": state.max_turns,
        "status": state.status,
        "current_agent": state.current_agent,
        "last_question": state.last_question,
        "candidate_response": state.candidate_response,
        "resume_text": state.resume_text,
        "jd_text": state.jd_text,
        "unified_history": state.unified_history,
        "transfer_queue": [pkg.model_dump() for pkg in state.transfer_queue],
        "competency_history": state.competency_history,
        "total_budget_consumed": state.total_budget_consumed,
    }


@app.post("/sessions", response_model=CreateSessionResponse)
def create_session(req: CreateSessionRequest) -> CreateSessionResponse:
    session_id = str(uuid.uuid4())
    state = InterviewState(
        session_id=session_id,
        turn=0,
        max_turns=req.max_turns,
        candidate_response=req.candidate_response,
        resume_path=req.resume_path,
        jd_path=req.jd_path,
    )
    orchestrator = Orchestrator(state)
    _sessions[session_id] = orchestrator
    return CreateSessionResponse(session_id=session_id, status=state.status)


@app.post("/sessions/{session_id}/step", response_model=StepResponse)
def step(session_id: str, req: StepRequest) -> StepResponse:
    orchestrator = _sessions.get(session_id)
    if orchestrator is None:
        raise HTTPException(status_code=404, detail="Session not found")
    result: StepResult = orchestrator.step(req.candidate_response)
    return StepResponse(
        agent=result.agent,
        question=result.question,
        finished=result.finished,
        report=result.report,
    )


@app.get("/sessions/{session_id}", response_model=SessionStateResponse)
def get_session(session_id: str) -> SessionStateResponse:
    orchestrator = _sessions.get(session_id)
    if orchestrator is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionStateResponse(**_state_to_dict(orchestrator.state))


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "sessions": len(_sessions)}
