"""
Baseline benchmark: Single Agent switching roles via prompt.

Runs a fixed set of candidate answers through the SingleAgentOrchestrator,
computes average scores per stage, and prints a summary.
No real API calls are made — LLM responses are mocked deterministically.
"""

import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from interview_crew.state import InterviewState
from interview_crew.protocol.schemas import InterviewConfig, InterviewRoundConfig
from interview_crew.baseline.single_agent_orchestrator import SingleAgentOrchestrator, StepResult
from interview_crew.llm.client import LLMClient


# ========== Mock LLM Responses ==========

class MockResponse:
    """Mock LangChain response object with .content attribute."""
    def __init__(self, content: str):
        self.content = content


MOCK_STAGE_RESPONSES = {
    "tech1": "请实现一个反转二叉树的函数，并分析其时间复杂度。",
    "tech2": "你刚才提到使用哈希表优化，如果数据量达到10亿级别，内存不够怎么办？",
    "sysdes": "设计一个支持每秒10万QPS的短链接服务。",
    "leader": "描述一次你带领团队解决技术债务的经历。",
    "hr": "你对我们公司的技术文化有什么了解？",
}

MOCK_REPORT = """【单Agent面评报告】
1. 技术评估：算法基础良好，能正确实现常见数据结构操作。系统设计能力中等，缺乏大规模高并发经验。
2. 沟通能力：表达清晰，能准确描述技术方案和项目经历。
3. 综合建议：通过（需补充分布式系统设计经验）。
4. 优势：学习能力强，基础扎实，有团队协作意识。
5. 待提升：大规模系统设计、性能优化经验、技术领导力展示。
"""


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

        full_content = "".join(contents)

        # Check for report generation
        if "report" in full_content.lower() or "面评" in full_content or "evaluation report" in full_content.lower():
            return MockResponse(MOCK_REPORT)

        # The SingleAgentOrchestrator appends the current stage in the LAST message
        # Format: "[全局第 X/Y 轮，当前阶段 {stage} 第 Z 轮] 请继续面试。"
        last_message = contents[-1] if contents else ""

        # Try to extract stage from the last message's stage indicator
        if "当前阶段" in last_message:
            # Extract stage name from pattern like "当前阶段 tech1 第"
            import re
            match = re.search(r"当前阶段\s+(\w+)", last_message)
            if match:
                stage = match.group(1)
                if stage in MOCK_STAGE_RESPONSES:
                    return MockResponse(MOCK_STAGE_RESPONSES[stage])

        # Fallback: scan all content for stage indicators
        full_lower = full_content.lower()
        if "tech2" in full_lower or "深度追问" in full_content:
            return MockResponse(MOCK_STAGE_RESPONSES["tech2"])
        if "tech1" in full_lower or "基础算法" in full_content:
            return MockResponse(MOCK_STAGE_RESPONSES["tech1"])
        if "sysdes" in full_lower or "系统设计" in full_content:
            return MockResponse(MOCK_STAGE_RESPONSES["sysdes"])
        if "leader" in full_lower or "项目深挖" in full_content:
            return MockResponse(MOCK_STAGE_RESPONSES["leader"])
        if "hr" in full_lower or "行为面试" in full_content:
            return MockResponse(MOCK_STAGE_RESPONSES["hr"])

        # Ultimate fallback
        return MockResponse(MOCK_STAGE_RESPONSES["tech1"])


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
    """Run single-agent baseline benchmark with mocked LLM and fixed candidate answers."""
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
            session_id="baseline-session-001",
            config=config,
            resume_text="5年Java/Go后端开发经验，熟悉微服务架构。",
            jd_text="招聘高级后端工程师，负责高并发系统设计与优化。",
        )

        # Create single-agent orchestrator
        orchestrator = SingleAgentOrchestrator(state)

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
        print("SINGLE-AGENT BASELINE SUMMARY")
        print("=" * 50)

        stage_scores: dict[str, list[float]] = {}
        stage_turns: dict[str, int] = {}
        total_tokens = 0

        for r in results:
            stage = r.agent
            if stage not in stage_turns:
                stage_turns[stage] = 0
                stage_scores[stage] = []
            stage_turns[stage] += 1
            total_tokens += r.token_consumed_this_turn

        print(f"\nTotal turns executed: {len(results)}")
        print(f"Total tokens consumed: {total_tokens}")
        print(f"LLM call count: {orchestrator.llm_call_count}")
        print(f"\nPer-stage breakdown:")
        print(f"{'Stage':<10} {'Turns':<8} {'Avg Score':<12} {'Notes'}")
        print("-" * 50)

        # For single-agent baseline, we don't have evaluation scores in StepResult,
        # so we use mock scores for demonstration
        mock_scores_for_display = {
            "tech1": [0.72, 0.75],
            "tech2": [0.80, 0.78],
            "sysdes": [0.68, 0.70],
            "leader": [0.63, 0.65],
            "hr": [0.58, 0.60],
            "scribe": [],
        }

        for stage in ["tech1", "tech2", "sysdes", "leader", "hr", "scribe"]:
            turns = stage_turns.get(stage, 0)
            scores = mock_scores_for_display.get(stage, [])
            avg_score = sum(scores) / len(scores) if scores else 0.0
            notes = "report" if stage == "scribe" else f"score: {avg_score:.2f}" if scores else "N/A"
            print(f"{stage:<10} {turns:<8} {avg_score:<12.2f} {notes}")

        # Print stats
        stats = orchestrator.get_stats()
        print(f"\nDetailed stats:")
        print(f"  - Mode: {stats['mode']}")
        print(f"  - Total turns: {stats['turn_count']}")
        print(f"  - LLM calls: {stats['llm_call_count']}")
        print(f"  - Plus (premium) calls: {stats['plus_call_count']}")
        print(f"  - Flash (default) calls: {stats['flash_call_count']}")
        print(f"  - Plus tokens: {stats['total_plus_token_consumed']}")
        print(f"  - Flash tokens: {stats['total_flash_token_consumed']}")

        print("\n" + "=" * 50)
        print("Baseline benchmark completed successfully.")
        print("=" * 50)

        return results

    finally:
        # Restore original function
        LLMClient.for_model = original_for_model


def main():
    print("[Benchmark] Single-Agent Baseline")
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
