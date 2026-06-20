"""
Benchmark: Multi-Agent Interview Runner.

Runs a fixed set of candidate answers through the multi-agent Orchestrator,
computes average evaluation_score per agent, and prints a summary.
No real API calls are made — LLM responses are mocked deterministically.
"""

import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from interview_crew.state import InterviewState
from interview_crew.protocol.schemas import InterviewConfig, InterviewRoundConfig
from interview_crew.orchestrator.engine import Orchestrator, StepResult
from interview_crew.llm.client import LLMClient


# ========== Mock LLM Responses ==========

class MockResponse:
    """Mock LangChain response object with .content attribute."""
    def __init__(self, content: str):
        self.content = content


MOCK_AGENT_RESPONSES = {
    "tech1": json.dumps({
        "question": "请实现一个反转二叉树的函数，并分析其时间复杂度。",
        "evaluation_score": 0.75,
        "key_weaknesses": ["对递归边界条件理解不够深入"],
        "follow_up_candidates": ["非递归实现方式", "空间复杂度优化"],
        "reasoning": "候选人基础扎实，但缺乏对边界条件的深入思考。"
    }),
    "tech2": json.dumps({
        "question": "你刚才提到使用哈希表优化，如果数据量达到10亿级别，内存不够怎么办？",
        "evaluation_score": 0.82,
        "key_weaknesses": ["未考虑大规模数据场景"],
        "follow_up_candidates": ["外排序", "分布式处理方案"],
        "reasoning": "候选人能给出基本方案，但缺乏对极端场景的考量。"
    }),
    "sysdes": json.dumps({
        "question": "设计一个支持每秒10万QPS的短链接服务。",
        "evaluation_score": 0.70,
        "key_weaknesses": ["未考虑缓存一致性"],
        "follow_up_candidates": ["读写分离策略", "缓存预热方案"],
        "reasoning": "候选人有基本设计思路，但缺乏对高并发细节的处理经验。"
    }),
    "leader": json.dumps({
        "question": "描述一次你带领团队解决技术债务的经历。",
        "evaluation_score": 0.65,
        "key_weaknesses": ["缺乏量化指标"],
        "follow_up_candidates": ["如何平衡业务需求与技术重构"],
        "reasoning": "候选人能描述经历，但缺乏数据支撑和系统性思考。"
    }),
    "hr": json.dumps({
        "question": "你对我们公司的技术文化有什么了解？",
        "evaluation_score": 0.60,
        "key_weaknesses": ["对公司了解不足"],
        "follow_up_candidates": ["职业规划", "期望的工作环境"],
        "reasoning": "候选人准备不够充分，对公司文化了解有限。"
    }),
    "scribe": "【面评报告】候选人技术基础扎实，算法能力良好，系统设计有一定经验但缺乏大规模场景实践。沟通表达清晰，团队协作意识较强。综合建议：通过（需补充系统设计经验）。",
}

MOCK_DISTILL_RESPONSE = json.dumps({
    "candidate_profile": {
        "strong_area": "算法基础",
        "weak_area": "大规模系统设计"
    },
    "competency_vector": [
        {"dimension": "coding", "score": 0.75, "evidence": "能正确实现二叉树反转", "confidence": 0.8},
        {"dimension": "system_design", "score": 0.70, "evidence": "有基本设计思路但缺乏细节", "confidence": 0.7},
        {"dimension": "communication", "score": 0.80, "evidence": "表达清晰，逻辑连贯", "confidence": 0.85}
    ],
    "doubt_list": ["是否真实参与过大规模项目"],
    "contradiction_alerts": [],
    "recommended_focus": "深入追问系统设计细节"
})


class MockLLM:
    """Mock LLM that returns deterministic responses based on message content."""

    def invoke(self, messages):
        # Extract content from messages (handle both dict and LangChain message objects)
        contents = []
        for msg in messages:
            if hasattr(msg, "content"):
                contents.append(str(msg.content))
            elif isinstance(msg, dict):
                contents.append(msg.get("content", ""))

        # First message is typically the system prompt — use it for agent identification
        system_prompt = contents[0] if contents else ""
        full_content = "".join(contents)

        # Check for distiller (memory distillation) — must be first
        if "萃取" in full_content or "候选人能力画像" in full_content:
            return MockResponse(MOCK_DISTILL_RESPONSE)

        # Check for scribe report generation
        if "面评" in full_content or "report" in full_content.lower() or "evaluation report" in full_content.lower():
            return MockResponse(MOCK_AGENT_RESPONSES["scribe"])

        # Determine agent from system prompt (first message) for accuracy
        sys_lower = system_prompt.lower()

        if "资深技术面试官" in system_prompt or "senior skeptic" in sys_lower:
            return MockResponse(MOCK_AGENT_RESPONSES["tech2"])
        if "基础技术面试官" in system_prompt or "junior coder" in sys_lower:
            return MockResponse(MOCK_AGENT_RESPONSES["tech1"])
        if "系统架构面试官" in system_prompt or "architect" in sys_lower:
            return MockResponse(MOCK_AGENT_RESPONSES["sysdes"])
        if "技术领导力" in system_prompt or "leader" in sys_lower:
            return MockResponse(MOCK_AGENT_RESPONSES["leader"])
        if "文化契合度" in system_prompt or "hr" in sys_lower:
            return MockResponse(MOCK_AGENT_RESPONSES["hr"])

        # Fallback: scan all content for agent indicators
        full_lower = full_content.lower()
        if "tech2" in full_lower or "senior skeptic" in full_lower:
            return MockResponse(MOCK_AGENT_RESPONSES["tech2"])
        if "tech1" in full_lower or "junior coder" in full_lower:
            return MockResponse(MOCK_AGENT_RESPONSES["tech1"])
        if "sysdes" in full_lower or "architect" in full_lower:
            return MockResponse(MOCK_AGENT_RESPONSES["sysdes"])
        if "leader" in full_lower:
            return MockResponse(MOCK_AGENT_RESPONSES["leader"])
        if "hr" in full_lower:
            return MockResponse(MOCK_AGENT_RESPONSES["hr"])

        # Ultimate fallback
        return MockResponse(MOCK_AGENT_RESPONSES["tech1"])


def _mock_for_model(self, model_name, temperature=0.7):
    """Mock LLMClient.for_model to return our MockLLM."""
    return MockLLM()


# ========== Predefined Candidate Answers ==========

CANDIDATE_ANSWERS = [
    "你好，我是候选人。我有5年后端开发经验，主要使用Java和Go。",
    "反转二叉树可以用递归实现，时间复杂度O(n)，空间复杂度O(h)。",
    "对于10亿数据，可以考虑分片存储，使用一致性哈希分配数据。",
    "短链接服务可以用Base62编码，配合Redis缓存和MySQL持久化。",
    "我曾经带领3人团队重构了订单模块，将接口延迟从200ms降到50ms。",
    "我了解到贵公司注重技术创新，有完善的技术分享机制。",
]


def run_benchmark():
    """Run multi-agent benchmark with mocked LLM and fixed candidate answers."""
    # Monkeypatch LLMClient.for_model to return our MockLLM
    original_for_model = LLMClient.for_model
    LLMClient.for_model = _mock_for_model

    try:
        # Create fixed InterviewConfig
        config = InterviewConfig(
            total_max_turns=12,
            rounds={
                "tech1": InterviewRoundConfig(enabled=True, max_turns=2),
                "tech2": InterviewRoundConfig(enabled=True, max_turns=2),
                "sysdes": InterviewRoundConfig(enabled=True, max_turns=2),
                "leader": InterviewRoundConfig(enabled=True, max_turns=2),
                "hr": InterviewRoundConfig(enabled=True, max_turns=2),
            }
        )

        # Create state
        state = InterviewState(
            session_id="benchmark-session-001",
            config=config,
            resume_text="5年Java/Go后端开发经验，熟悉微服务架构。",
            jd_text="招聘高级后端工程师，负责高并发系统设计与优化。",
        )

        # Create orchestrator
        orchestrator = Orchestrator(state)

        # Run turns
        results: list[StepResult] = []
        for i, answer in enumerate(CANDIDATE_ANSWERS):
            try:
                result = orchestrator.step(answer)
                results.append(result)
                print(f"  Turn {i+1}: [{result.agent}] {result.question[:50]}...")
                if result.finished:
                    print(f"  Interview finished. Report generated.")
                    break
            except Exception as e:
                print(f"  ERROR at turn {i+1}: {e}")
                break

        # Compute summary statistics
        print("\n" + "=" * 50)
        print("MULTI-AGENT BENCHMARK SUMMARY")
        print("=" * 50)

        agent_scores: dict[str, list[float]] = {}
        agent_turns: dict[str, int] = {}
        total_tokens = 0

        for r in results:
            agent = r.agent
            if agent not in agent_turns:
                agent_turns[agent] = 0
                agent_scores[agent] = []
            agent_turns[agent] += 1
            total_tokens += r.token_consumed_this_turn

        # Extract evaluation scores from transfer queue
        for pkg in state.transfer_queue:
            if pkg.evaluation_score is not None:
                agent = pkg.from_agent
                if agent not in agent_scores:
                    agent_scores[agent] = []
                agent_scores[agent].append(pkg.evaluation_score)

        print(f"\nTotal turns executed: {len(results)}")
        print(f"Total tokens consumed: {total_tokens}")
        print(f"\nPer-agent breakdown:")
        print(f"{'Agent':<10} {'Turns':<8} {'Avg Score':<12} {'Scores'}")
        print("-" * 50)

        for agent in ["tech1", "tech2", "sysdes", "leader", "hr", "scribe"]:
            turns = agent_turns.get(agent, 0)
            scores = agent_scores.get(agent, [])
            avg_score = sum(scores) / len(scores) if scores else 0.0
            score_str = f"[{', '.join(f'{s:.2f}' for s in scores)}]" if scores else "[]"
            print(f"{agent:<10} {turns:<8} {avg_score:<12.2f} {score_str}")

        print("\n" + "=" * 50)
        print("Benchmark completed successfully.")
        print("=" * 50)

        return results

    finally:
        # Restore original function
        LLMClient.for_model = original_for_model


def main():
    print("[Benchmark] Multi-Agent Interview Runner")
    print("=" * 50)
    print("Mocking LLM responses (no API calls)...")
    print()

    results = run_benchmark()

    if results:
        print(f"\nCollected {len(results)} step results.")
    else:
        print("\nNo results collected.")


if __name__ == "__main__":
    main()
