import json
import uuid
import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Literal, Union, AsyncGenerator

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from interview_crew.state import InterviewState
from interview_crew.orchestrator.engine import Orchestrator, StepResult
from interview_crew.baseline.single_agent_orchestrator import SingleAgentOrchestrator
from interview_crew.services.code_sandbox import code_sandbox
from interview_crew.protocol.schemas import InterviewConfig, InterviewRoundConfig, StageTurnLimit
from interview_crew.llm.metrics import (
    get_metrics_text,
    get_metrics_content_type,
    set_active_sessions,
    record_turn,
)
from interview_crew.storage.session_store import get_session_store
from interview_crew.middleware.rate_limiter import RateLimitMiddleware

# Type alias for orchestrator
OrchestratorType = Union[Orchestrator, SingleAgentOrchestrator]

app = FastAPI(title="InterviewCrew API", version="0.2.0")
app.add_middleware(RateLimitMiddleware)

# In-memory session storage (orchestrator cache)
_sessions: Dict[str, OrchestratorType] = {}
_session_store = get_session_store()


class StageLimitInput(BaseModel):
    """Input for sub-stage turn limit configuration."""
    stage_name: str = Field(..., description="Sub-stage name (e.g., 'chat', 'deep_dive', 'coding')")
    max_turns: int = Field(default=2, ge=1, le=50, description="Max turns for this sub-stage")
    description: str = Field(default="", description="Optional description")


class RoundConfigInput(BaseModel):
    """Input for per-round configuration."""
    enabled: bool = True
    max_turns: int = Field(default=6, ge=1, le=30, description="Total turns for this agent across all sub-stages")
    # Legacy sub-stage limits (backward compatible)
    max_chat_turns: int = Field(default=2, ge=1, le=10)
    max_coding_turns: int = Field(default=5, ge=1, le=20, description="Max turns in coding sub-stage")
    max_reflect_turns: int = Field(default=1, ge=1, le=5)
    # New: detailed sub-stage configuration
    stage_turn_limits: Optional[List[StageLimitInput]] = Field(
        default=None,
        description="Detailed sub-stage turn limits (overrides legacy fields if provided)"
    )


class CreateSessionRequest(BaseModel):
    """Request to create a new interview session.

    Examples:
        # Default full interview (all rounds, ~20-30 turns)
        {}

        # Single agent baseline mode
        {"mode": "single_agent"}

        # Only tech rounds (quick technical screening)
        {
            "total_max_turns": 10,
            "rounds_config": {
                "tech1": {"enabled": true, "max_turns": 6},
                "tech2": {"enabled": true, "max_turns": 6},
                "sysdes": {"enabled": false},
                "leader": {"enabled": false},
                "hr": {"enabled": false}
            }
        }

        # Skip sysdes, only tech1+tech2+leader+hr
        {
            "rounds_config": {
                "sysdes": {"enabled": false}
            }
        }

        # Quick screening (minimal rounds)
        {
            "total_max_turns": 5,
            "rounds_config": {
                "tech1": {"enabled": true, "max_turns": 3, "max_chat_turns": 1},
                "hr": {"enabled": true, "max_turns": 2}
            }
        }

        # Detailed sub-stage configuration (new)
        {
            "total_max_turns": 20,
            "rounds_config": {
                "tech1": {
                    "enabled": true,
                    "max_turns": 10,
                    "stage_turn_limits": [
                        {"stage_name": "chat", "max_turns": 2, "description": "技术交流"},
                        {"stage_name": "deep_dive", "max_turns": 3, "description": "深入追问"},
                        {"stage_name": "coding", "max_turns": 5, "description": "编程考核"},
                        {"stage_name": "reflect", "max_turns": 1, "description": "反思总结"}
                    ]
                }
            }
        }
    """
    # Mode selection: multi_agent (default) or single_agent (baseline)
    mode: Literal["multi_agent", "single_agent"] = Field(
        default="multi_agent",
        description="Interview mode: multi_agent (specialist agents) or single_agent (baseline)"
    )

    # Legacy field (deprecated, use config.total_max_turns)
    max_turns: int = Field(default=6, ge=1, le=50)

    # New configuration
    total_max_turns: int = Field(default=30, ge=1, le=100, description="Global max turns across all rounds")
    rounds_config: Optional[Dict[str, RoundConfigInput]] = Field(
        default=None,
        description="Per-round configuration (enable/disable, max turns per round)"
    )

    candidate_response: str = ""
    resume_path: str | None = None
    jd_path: str | None = None


class CreateSessionResponse(BaseModel):
    session_id: str
    status: str
    mode: str = "multi_agent"


class StepRequest(BaseModel):
    candidate_response: str


class StepResponse(BaseModel):
    agent: str
    question: str
    finished: bool
    report: str = ""
    # Token statistics for comparison testing
    token_consumed_this_turn: int = 0
    total_token_consumed: int = 0
    # Detailed breakdown by model tier
    plus_token_consumed_this_turn: int = 0  # premium/quality model
    flash_token_consumed_this_turn: int = 0  # default/economy model
    total_plus_token_consumed: int = 0
    total_flash_token_consumed: int = 0


class SessionStateResponse(BaseModel):
    session_id: str
    turn: int
    max_turns: int  # Legacy field
    total_max_turns: int  # New: from config
    status: str
    current_agent: str
    enabled_rounds: list  # New: list of enabled rounds
    last_question: str
    candidate_response: str
    resume_text: str
    jd_text: str
    unified_history: list
    transfer_queue: list
    competency_history: list
    total_budget_consumed: int
    # Mode and statistics for comparison testing
    mode: str = "multi_agent"  # multi_agent or single_agent
    llm_call_count: int = 0
    token_consumed: int = 0
    # Detailed breakdown by model tier
    plus_call_count: int = 0
    flash_call_count: int = 0
    total_plus_token_consumed: int = 0
    total_flash_token_consumed: int = 0


class SubmitCodeRequest(BaseModel):
    code: str
    language: str = Field(default="python", pattern="^(python|javascript|java|go)$")


class TestResult(BaseModel):
    case_id: int
    input_data: str
    expected: str
    actual: str
    passed: bool
    error_message: str = ""


class SubmitCodeResponse(BaseModel):
    compile_success: bool
    compile_output: str
    test_results: List[TestResult]
    overall_passed: bool
    execution_time_ms: float
    next_question: str
    current_sub_stage: str = ""
    ast_analysis: dict = Field(default_factory=dict, description="AST static analysis results")


class CodingTaskResponse(BaseModel):
    has_active_task: bool
    title: str = ""
    description: str = ""
    difficulty: str = ""
    starter_code: str = ""
    current_agent: str = ""
    sub_stage: str = ""


def _state_to_dict(state: InterviewState, orchestrator: OrchestratorType = None) -> dict:
    """Serialize InterviewState to a JSON-friendly dict."""
    # Get enabled rounds from orchestrator if available
    enabled_rounds = []
    if orchestrator and hasattr(orchestrator, '_enabled_rounds'):
        enabled_rounds = orchestrator._enabled_rounds
    elif state.config:
        enabled_rounds = state.config.get_enabled_rounds()

    # Get mode and statistics from orchestrator
    mode = "multi_agent"
    llm_call_count = 0
    token_consumed = 0
    plus_call_count = 0
    flash_call_count = 0
    total_plus_token_consumed = 0
    total_flash_token_consumed = 0
    if orchestrator:
        if isinstance(orchestrator, SingleAgentOrchestrator):
            mode = "single_agent"
            stats = orchestrator.get_stats()
            llm_call_count = stats.get("llm_call_count", 0)
            token_consumed = stats.get("token_consumed", 0)
            plus_call_count = stats.get("plus_call_count", 0)
            flash_call_count = stats.get("flash_call_count", 0)
            total_plus_token_consumed = stats.get("total_plus_token_consumed", 0)
            total_flash_token_consumed = stats.get("total_flash_token_consumed", 0)
        # For multi-agent, budget consumed is tracked in state

    return {
        "session_id": state.session_id,
        "turn": state.turn,
        "max_turns": state.max_turns,
        "total_max_turns": state.config.total_max_turns if state.config else state.max_turns,
        "status": state.status,
        "current_agent": state.current_agent,
        "enabled_rounds": enabled_rounds,
        "last_question": state.last_question,
        "candidate_response": state.candidate_response,
        "resume_text": state.resume_text,
        "jd_text": state.jd_text,
        "unified_history": state.unified_history,
        "transfer_queue": [pkg.model_dump() for pkg in state.transfer_queue],
        "competency_history": state.competency_history,
        "total_budget_consumed": state.total_budget_consumed,
        # Mode and statistics for comparison testing
        "mode": mode,
        "llm_call_count": llm_call_count,
        "token_consumed": token_consumed,
        # Detailed breakdown by model tier
        "plus_call_count": plus_call_count,
        "flash_call_count": flash_call_count,
        "total_plus_token_consumed": total_plus_token_consumed,
        "total_flash_token_consumed": total_flash_token_consumed,
    }


@app.post("/sessions", response_model=CreateSessionResponse)
def create_session(req: CreateSessionRequest) -> CreateSessionResponse:
    session_id = str(uuid.uuid4())

    # Build interview config from request
    # When rounds_config is provided, total_max_turns defaults to sum of enabled round max_turns
    if req.rounds_config:
        effective_total_turns = sum(
            r.max_turns for r in req.rounds_config.values() if r.enabled
        )
    else:
        effective_total_turns = req.total_max_turns if req.total_max_turns != 30 else req.max_turns
    config = InterviewConfig(total_max_turns=effective_total_turns)

    if req.rounds_config:
        for round_name, round_input in req.rounds_config.items():
            # Build stage_turn_limits if provided
            stage_limits = None
            if round_input.stage_turn_limits:
                stage_limits = [
                    StageTurnLimit(
                        stage_name=s.stage_name,
                        max_turns=s.max_turns,
                        description=s.description
                    )
                    for s in round_input.stage_turn_limits
                ]

            round_config = InterviewRoundConfig(
                enabled=round_input.enabled,
                max_turns=round_input.max_turns,
                max_chat_turns=round_input.max_chat_turns,
                max_coding_turns=round_input.max_coding_turns,
                max_reflect_turns=round_input.max_reflect_turns,
                stage_turn_limits=stage_limits if stage_limits else None
            )

            if round_name in config.rounds:
                config.rounds[round_name] = round_config
            else:
                # Add new custom round config
                config.rounds[round_name] = round_config

    state = InterviewState(
        session_id=session_id,
        turn=0,
        max_turns=req.max_turns,  # Legacy field
        config=config,
        candidate_response=req.candidate_response,
        resume_path=req.resume_path,
        jd_path=req.jd_path,
    )

    # Create orchestrator based on mode
    if req.mode == "single_agent":
        orchestrator = SingleAgentOrchestrator(state)
    else:
        orchestrator = Orchestrator(state)

    _sessions[session_id] = orchestrator
    # Save to persistent store
    try:
        _session_store.save(session_id, state.to_json())
    except Exception:
        pass
    return CreateSessionResponse(session_id=session_id, status=state.status, mode=req.mode)


@app.post("/sessions/{session_id}/step", response_model=StepResponse)
def step(session_id: str, req: StepRequest) -> StepResponse:
    orchestrator = _sessions.get(session_id)
    if orchestrator is None:
        raise HTTPException(status_code=404, detail="Session not found")
    result: StepResult = orchestrator.step(req.candidate_response)
    record_turn(result.agent)
    # Persist session state
    try:
        _session_store.save(session_id, orchestrator.state.to_json())
    except Exception:
        pass
    return StepResponse(
        agent=result.agent,
        question=result.question,
        finished=result.finished,
        report=result.report,
        token_consumed_this_turn=result.token_consumed_this_turn,
        total_token_consumed=result.total_token_consumed,
        # Detailed breakdown by model tier
        plus_token_consumed_this_turn=result.plus_token_consumed_this_turn,
        flash_token_consumed_this_turn=result.flash_token_consumed_this_turn,
        total_plus_token_consumed=result.total_plus_token_consumed,
        total_flash_token_consumed=result.total_flash_token_consumed,
    )


async def _stream_step_internal(session_id: str, candidate_response: str):
    """Internal stream logic shared by GET (SSE) and POST endpoints."""
    orchestrator = _sessions.get(session_id)
    if orchestrator is None:
        raise HTTPException(status_code=404, detail="Session not found")

    async def event_generator():
        result: StepResult = orchestrator.step(candidate_response)
        record_turn(result.agent)

        # Persist state
        try:
            _session_store.save(session_id, orchestrator.state.to_json())
        except Exception:
            pass

        text = result.question
        chunk_size = 2
        for i in range(0, len(text), chunk_size):
            chunk = text[i:i + chunk_size]
            yield {
                "event": "token",
                "data": json.dumps({
                    "token": chunk,
                    "agent": result.agent,
                    "finished": result.finished,
                })
            }
            await asyncio.sleep(0.015)

        yield {
            "event": "done",
            "data": json.dumps({
                "agent": result.agent,
                "question": result.question,
                "finished": result.finished,
                "report": result.report,
                "token_consumed_this_turn": result.token_consumed_this_turn,
                "total_token_consumed": result.total_token_consumed,
            })
        }

    return EventSourceResponse(event_generator())


@app.post("/sessions/{session_id}/stream")
async def stream_step_post(session_id: str, req: StepRequest):
    """Stream interview turn response via SSE (POST)."""
    return await _stream_step_internal(session_id, req.candidate_response)


@app.get("/sessions/{session_id}/stream")
async def stream_step_get(session_id: str, candidate_response: str = ""):
    """Stream interview turn response via SSE (GET for EventSource compatibility)."""
    return await _stream_step_internal(session_id, candidate_response)


@app.get("/sessions/{session_id}", response_model=SessionStateResponse)
def get_session(session_id: str) -> SessionStateResponse:
    orchestrator = _sessions.get(session_id)
    if orchestrator is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionStateResponse(**_state_to_dict(orchestrator.state, orchestrator))


@app.post("/sessions/{session_id}/submit-code", response_model=SubmitCodeResponse)
def submit_code(session_id: str, req: SubmitCodeRequest) -> SubmitCodeResponse:
    """提交代码执行并获取结果和追问"""
    orchestrator = _sessions.get(session_id)
    if orchestrator is None:
        raise HTTPException(status_code=404, detail="Session not found")

    # Single agent mode does not support code submission
    if isinstance(orchestrator, SingleAgentOrchestrator):
        raise HTTPException(
            status_code=400,
            detail="Code submission not supported in single_agent mode"
        )

    # 获取当前代码任务
    task = orchestrator.state.current_coding_task
    if not task:
        raise HTTPException(status_code=400, detail="No active coding task")

    # 执行代码
    from interview_crew.protocol.schemas import TestCase
    test_cases = [TestCase(**tc) for tc in task.get("test_cases", [])]
    result = code_sandbox.execute(req.code, [tc.model_dump() for tc in test_cases], req.language)

    # 获取当前 Agent 生成追问
    agent_name = orchestrator.state.current_agent
    if agent_name not in ["tech1", "tech2"]:
        raise HTTPException(status_code=400, detail="Not in coding stage")

    agent = orchestrator.agents[agent_name]

    # 构建追问
    if result.overall_passed:
        follow_up = (
            f"代码执行通过！耗时 {result.execution_time_ms:.0f}ms。\n"
            f"请分析这段代码的时间复杂度和空间复杂度。"
            f"如果数据量扩大 100 倍，你会如何优化？"
        )
    else:
        failed_tests = [t for t in result.test_results if not t.passed][:2]
        fail_msgs = "\n".join([
            f"- 测试用例 {t.case_id}: 期望 {t.expected}, 实际 {t.actual}"
            for t in failed_tests
        ])
        follow_up = (
            f"代码执行失败。\n"
            f"失败的测试用例:\n{fail_msgs}\n\n"
            f"请分析错误原因并说明修复思路（无需重写代码）。"
        )

    # 记录 Agent 追问到历史
    assistant_msg = {
        "role": "assistant",
        "name": agent_name,
        "content": follow_up,
    }
    orchestrator.state.append_agent_history(agent_name, assistant_msg)
    orchestrator.state.append_unified(assistant_msg)

    # 推进 sub_stage: coding -> reflect
    new_sub_stage = orchestrator.state.advance_sub_stage(agent_name)

    # 如果进入 reflect 阶段，自动触发 reflect 阶段的问题生成
    if new_sub_stage == "reflect":
        from interview_crew.memory.distiller import distill_memory
        from interview_crew.memory.agent_mailbox import build_agent_messages
        from interview_crew.llm.client import llm

        # 蒸馏记忆
        memory_distillate = distill_memory(
            orchestrator.state.unified_history,
            orchestrator.state.session_id,
            orchestrator.state.turn,
        )

        # 构建 reflect 阶段上下文
        reflect_context = agent.build_reflect_context(memory_distillate, orchestrator.state)

        # 构建消息
        messages = build_agent_messages(
            orchestrator.state.get_agent_history(agent_name),
            f"{agent.system_prompt}\n\n{reflect_context}",
            "",  # candidate_response 为空，因为这是自动触发
            orchestrator._business_context_text(),
            orchestrator.state.resume_text,
        )

        # 调用 LLM 生成 reflect 阶段问题
        raw = llm.invoke(messages, model_name=agent.preferred_model, temperature=agent.default_temperature)

        # 解析输出
        try:
            import json
            data = json.loads(raw.strip())
            from interview_crew.protocol.schemas import AgentOutput
            reflect_output = AgentOutput(**data)
        except Exception:
            from interview_crew.protocol.schemas import AgentOutput
            reflect_output = AgentOutput(
                question="请总结一下今天面试的表现，包括：1) 你觉得自己回答得最好的地方；2) 有哪些可以改进的地方；3) 有什么想补充的？",
                evaluation_score=0.5,
                key_weaknesses=[],
                follow_up_candidates=[],
                reasoning="parse error, using default reflect question",
            )

        # 记录 reflect 问题到历史
        reflect_msg = {
            "role": "assistant",
            "name": agent_name,
            "content": reflect_output.question,
        }
        orchestrator.state.append_agent_history(agent_name, reflect_msg)
        orchestrator.state.append_unified(reflect_msg)

        # 更新 sub_stage turn counter
        orchestrator.state.increment_stage_turns(agent_name)

        return SubmitCodeResponse(
            compile_success=result.success,
            compile_output=result.compile_output,
            test_results=[TestResult(**t) for t in result.test_results],
            overall_passed=result.overall_passed,
            execution_time_ms=result.execution_time_ms,
            next_question=follow_up + "\n\n" + reflect_output.question,
            current_sub_stage=new_sub_stage,
            ast_analysis=result.ast_analysis,
        )

    return SubmitCodeResponse(
        compile_success=result.success,
        compile_output=result.compile_output,
        test_results=[TestResult(**t) for t in result.test_results],
        overall_passed=result.overall_passed,
        execution_time_ms=result.execution_time_ms,
        next_question=follow_up,
        current_sub_stage=orchestrator.state.get_sub_stage(agent_name),
        ast_analysis=result.ast_analysis,
    )


@app.get("/sessions/{session_id}/coding-task", response_model=CodingTaskResponse)
def get_coding_task(session_id: str) -> CodingTaskResponse:
    """获取当前代码题目（如果处于 coding 阶段）"""
    orchestrator = _sessions.get(session_id)
    if orchestrator is None:
        raise HTTPException(status_code=404, detail="Session not found")

    # Single agent mode does not support coding tasks
    if isinstance(orchestrator, SingleAgentOrchestrator):
        return CodingTaskResponse(has_active_task=False)

    task = orchestrator.state.current_coding_task
    agent_name = orchestrator.state.current_agent
    sub_stage = orchestrator.state.get_sub_stage(agent_name)

    if not task or sub_stage != "coding":
        return CodingTaskResponse(
            has_active_task=False,
            current_agent=agent_name,
            sub_stage=sub_stage,
        )

    return CodingTaskResponse(
        has_active_task=True,
        title=task.get("title", ""),
        description=task.get("description", ""),
        difficulty=task.get("difficulty", ""),
        starter_code=task.get("starter_code", ""),
        current_agent=agent_name,
        sub_stage=sub_stage,
    )


@app.get("/health")
def health() -> dict:
    set_active_sessions(len(_sessions))
    return {
        "status": "ok",
        "sessions": len(_sessions),
        "version": "0.2.0",
        "features": ["async_streaming", "tiktoken", "metrics", "rate_limiting", "session_persistence"],
    }


@app.get("/metrics")
def metrics():
    """Prometheus-style metrics endpoint."""
    set_active_sessions(len(_sessions))
    return Response(
        content=get_metrics_text(),
        media_type=get_metrics_content_type(),
    )


# Mount static files for the web frontend
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
def root() -> FileResponse:
    return FileResponse(str(static_dir / "index.html"))


# ===== Startup: recover active sessions from persistent store =====

@app.on_event("startup")
def startup_event():
    """Recover active sessions from persistent store on startup."""
    try:
        active_ids = _session_store.list_active()
        recovered = 0
        for sid in active_ids:
            try:
                data = _session_store.load(sid)
                if data:
                    state = InterviewState.from_json(data)
                    if state.status == "ongoing":
                        if hasattr(state, "mode") and state.mode == "single_agent":
                            orch = SingleAgentOrchestrator(state)
                        else:
                            orch = Orchestrator(state)
                        _sessions[sid] = orch
                        recovered += 1
            except Exception:
                continue
        if recovered > 0:
            print(f"[Startup] Recovered {recovered} active sessions from store")
    except Exception as e:
        print(f"[Startup] Session recovery skipped: {e}")
