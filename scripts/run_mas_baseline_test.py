#!/usr/bin/env python3
"""MAS Baseline Test - Automated runner for MAS mode interview.

This script automates the MAS baseline test described in docs/BASELINE_TEST_PLAN.md.
It creates a multi-agent interview session and runs through all 15 turns,
recording the results for later analysis.
"""

import json
from pathlib import Path
from datetime import datetime

from interview_crew.state import InterviewState
from interview_crew.orchestrator.engine import Orchestrator
from interview_crew.orchestrator.jd_parser import LLMJDParser
from interview_crew.protocol.schemas import InterviewConfig, InterviewRoundConfig


# 15-turn configuration matching BASELINE_TEST_PLAN.md
ROUNDS_CONFIG = {
    "tech1": InterviewRoundConfig(max_turns=4, max_chat_turns=2, max_reflect_turns=1),
    "tech2": InterviewRoundConfig(max_turns=4, max_chat_turns=2, max_reflect_turns=1),
    "sysdes": InterviewRoundConfig(max_turns=3, max_chat_turns=1, max_reflect_turns=1),
    "leader": InterviewRoundConfig(max_turns=2, max_chat_turns=1, max_reflect_turns=1),
    "hr": InterviewRoundConfig(max_turns=2, max_chat_turns=1, max_reflect_turns=1),
}

# Mock candidate responses based on resume content
CANDIDATE_RESPONSES = [
    # tech1 rounds (4 rounds × ~3 sub-stage turns, but coding requires manual trigger)
    "您好，我叫李文韬，上海交通大学 IEEE 试点班自动化专业在读。擅长 Python、C++，主要做 Agent 和 RAG 方向。",
    "我的 RepoMind 项目是一个代码感知 RAG 系统，使用 AST 多级分块策略，相比朴素 RAG 减少了约 88% 的 token 消耗。",
    "CueZero 是一个高性能台球 AI，使用 PyTorch 和强化学习训练策略网络，实现了实时物理模拟。",
    "我在项目中用 FastAPI 搭建了服务，Pydantic v2 做数据验证，FAISS 做向量检索。",
    # tech2 rounds
    "AST 分块的思路是把代码按 file/class/function/block 四级切片，保留结构化元数据比如 import 关系和调用图。",
    "RAG 检索流水线我设计了 Query 扩展 → 向量检索 → n-gram 关键词过滤 → MMR 多样性重排序。",
    "双模型路由是根据问题复杂度分类，简单问题用 flash 模型快速回答，复杂问题用 plus 模型深度推理。",
    "MCP 协议让 Claude Desktop 可以直接调用 RepoMind 的工具，实现了代码库的智能问答。",
    # sysdes rounds
    "如果 RepoMind 要支撑 10万+ 代码库，我会把 AST 解析和向量索引做成分布式服务，用消息队列解耦。",
    "缓存层我考虑用 Redis 缓存热点查询的检索结果，同时用 LRU 策略管理向量索引的内存占用。",
    "异步处理方面，大文件解析可以用 Celery 任务队列，避免阻塞主服务。",
    # leader rounds
    "技术选型上选择 FastAPI 是因为异步性能更好，Pydantic 的类型安全减少了大量运行时错误。",
    "AST 分块策略的设计灵感来自于编译器的前端分析，我花了两周时间调研了 tree-sitter 等工具。",
    # hr rounds
    "选择 Agent 方向是因为我相信 LLM 应用是未来趋势，希望能参与构建下一代智能系统。",
    "我的优势是工程能力强 + 有算法竞赛背景，能快速把想法落地成可运行的系统。",
]


def run_mas_baseline():
    """Run the MAS baseline test and save results."""
    print("=" * 60)
    print("MAS Baseline Test - Starting")
    print("=" * 60)

    # Build config
    config = InterviewConfig(total_max_turns=15, rounds=ROUNDS_CONFIG)

    # Create state
    state = InterviewState(
        session_id=f"baseline-mas-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        config=config,
        resume_path="data/samples/resume.md",
        jd_path="data/samples/jd_agent.md",
    )

    # Create orchestrator
    orch = Orchestrator(state, jd_parser=LLMJDParser())

    # Run interview
    results = []
    turn = 0

    while turn < 30:  # safety limit
        response = CANDIDATE_RESPONSES[min(turn, len(CANDIDATE_RESPONSES) - 1)]

        print(f"\n[Turn {turn + 1}] Agent: {state.current_agent or 'initial'}")
        print(f"  Candidate: {response[:60]}...")

        result = orch.step(response)

        record = {
            "turn": state.turn,
            "agent": result.agent,
            "question": result.question[:200] if result.question else "",
            "candidate_response": response,
            "finished": result.finished,
            "current_sub_stage": state.get_sub_stage(result.agent) if result.agent in ["tech1", "tech2"] else "",
            "round_turn_counts": dict(state.round_turn_counts),
            "current_round_index": state.current_round_index,
        }
        results.append(record)

        print(f"  Agent: {result.agent}, Finished: {result.finished}")
        if result.question:
            print(f"  Question: {result.question[:100]}...")

        if result.finished:
            print(f"\n  Report: {result.report[:300]}...")
            break

        turn += 1

    print("\n" + "=" * 60)
    print("MAS Baseline Test - Complete")
    print(f"Total turns: {state.turn}")
    print(f"Final agent: {state.current_agent}")
    print(f"Transfer queue length: {len(state.transfer_queue)}")
    print("=" * 60)

    # Save results
    date_str = datetime.now().strftime("%Y%m%d")

    # Raw state JSON
    raw_path = Path(f"data/records/BASELINE_RAW_MAS_{date_str}.json")
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump({
            "session_id": state.session_id,
            "turn": state.turn,
            "total_max_turns": config.total_max_turns,
            "status": state.status,
            "current_agent": state.current_agent,
            "enabled_rounds": orch._enabled_rounds,
            "round_turn_counts": dict(state.round_turn_counts),
            "current_round_index": state.current_round_index,
            "transfer_queue_count": len(state.transfer_queue),
            "results": results,
        }, f, ensure_ascii=False, indent=2)
    print(f"Saved raw state to: {raw_path}")

    # Dialog markdown
    dialog_path = Path(f"data/records/BASELINE_MULTI_DIALOG_{date_str}.md")
    with open(dialog_path, "w", encoding="utf-8") as f:
        f.write(f"# MAS Baseline Test Dialog - {date_str}\n\n")
        f.write(f"Session ID: {state.session_id}\n")
        f.write(f"Total turns: {state.turn}\n")
        f.write(f"Config: tech1×{ROUNDS_CONFIG['tech1'].max_turns} → tech2×{ROUNDS_CONFIG['tech2'].max_turns} → "
                f"sysdes×{ROUNDS_CONFIG['sysdes'].max_turns} → leader×{ROUNDS_CONFIG['leader'].max_turns} → "
                f"hr×{ROUNDS_CONFIG['hr'].max_turns} = 15\n\n")
        f.write("---\n\n")
        for r in results:
            f.write(f"## Turn {r['turn']} [{r['agent']}]\n\n")
            f.write(f"**Candidate**: {r['candidate_response']}\n\n")
            if r['question']:
                f.write(f"**Interviewer**: {r['question']}\n\n")
            if r['finished']:
                f.write(f"**Status**: Finished\n\n")
            f.write("---\n\n")
    print(f"Saved dialog to: {dialog_path}")

    # Scribe report
    if result.finished and result.report:
        report_path = Path(f"reports/SCRIBE_MULTI_REPORT_{date_str}.md")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(f"# MAS Scribe Report - {date_str}\n\n")
            f.write(result.report)
        print(f"Saved scribe report to: {report_path}")

    return state.turn, state.status == "finished"


if __name__ == "__main__":
    total_turns, finished = run_mas_baseline()
    if finished and total_turns >= 15:
        print("\n✅ MAS baseline test PASSED")
    else:
        print(f"\n❌ MAS baseline test FAILED (turns={total_turns}, finished={finished})")
