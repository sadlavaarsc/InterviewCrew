import uuid
from typing import Dict, List

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from interview_crew.state import InterviewState
from interview_crew.orchestrator.engine import Orchestrator, StepResult
from interview_crew.services.code_sandbox import code_sandbox

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


class CodingTaskResponse(BaseModel):
    has_active_task: bool
    title: str = ""
    description: str = ""
    difficulty: str = ""
    starter_code: str = ""
    current_agent: str = ""
    sub_stage: str = ""


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


@app.post("/sessions/{session_id}/submit-code", response_model=SubmitCodeResponse)
def submit_code(session_id: str, req: SubmitCodeRequest) -> SubmitCodeResponse:
    """提交代码执行并获取结果和追问"""
    orchestrator = _sessions.get(session_id)
    if orchestrator is None:
        raise HTTPException(status_code=404, detail="Session not found")

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
            test_results=[TestResult(**t.__dict__) for t in result.test_results],
            overall_passed=result.overall_passed,
            execution_time_ms=result.execution_time_ms,
            next_question=follow_up + "\n\n" + reflect_output.question,
            current_sub_stage=new_sub_stage,
        )

    return SubmitCodeResponse(
        compile_success=result.success,
        compile_output=result.compile_output,
        test_results=[TestResult(**t.__dict__) for t in result.test_results],
        overall_passed=result.overall_passed,
        execution_time_ms=result.execution_time_ms,
        next_question=follow_up,
        current_sub_stage=orchestrator.state.get_sub_stage(agent_name),
    )


@app.get("/sessions/{session_id}/coding-task", response_model=CodingTaskResponse)
def get_coding_task(session_id: str) -> CodingTaskResponse:
    """获取当前代码题目（如果处于 coding 阶段）"""
    orchestrator = _sessions.get(session_id)
    if orchestrator is None:
        raise HTTPException(status_code=404, detail="Session not found")

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
    return {"status": "ok", "sessions": len(_sessions)}
