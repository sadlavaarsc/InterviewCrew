from pathlib import Path
from typing import List
from interview_crew.agents.base import BaseAgent
from interview_crew.protocol.schemas import MemoryDistillate, CodingProblem
from interview_crew.config import settings
from interview_crew.state import InterviewState


class Tech2Agent(BaseAgent):
    """
    Tech2 Agent - 深度技术面试
    三阶段结构：chat (项目深挖) -> coding (中等算法) -> reflect (深度反思)
    """
    name = "tech2"
    prompt_path = Path(__file__).parent.parent / "prompts" / "tech2.txt"
    preferred_model = settings.premium_model
    default_temperature = 0.7
    has_sub_stages = True

    def build_context(self, distillate: MemoryDistillate) -> str:
        """chat 阶段上下文 - 项目深挖"""
        lines = [
            "【当前阶段】chat - 项目深挖",
            f"推荐追问方向：{distillate.recommended_focus}",
            "关键疑点（需验证）：",
        ]
        for doubt in distillate.doubt_list:
            lines.append(f"- {doubt}")

        if distillate.contradiction_alerts:
            lines.append("\n矛盾预警：")
            for alert in distillate.contradiction_alerts:
                lines.append(f"- {alert}")

        lines.append("\n请深挖候选人简历项目：")
        lines.append("- 具体做了什么？")
        lines.append("- 为什么这么做？")
        lines.append("- 技术细节和性能优化")
        return "\n".join(lines)

    def build_coding_context(self, distillate: MemoryDistillate, state: InterviewState) -> str:
        """coding 阶段上下文 - 生成中等算法题"""
        tech_stack = self._extract_tech_stack(distillate)
        difficulty = "medium"

        lines = [
            "【当前阶段】coding - 中等算法题",
            f"候选人技术栈：{', '.join(tech_stack)}",
            f"推荐难度：{difficulty} (LeetCode Medium 级别)",
            "",
            "请生成一道中等难度的算法题，要求：",
            "1. 与候选人技术栈或系统设计相关",
            "2. 提供 starter_code",
            "3. 提供 3+ 测试用例（含边界情况）",
            "4. 在 coding_problem 字段中返回题目信息",
            "5. 代码通过后，可追问时间/空间复杂度优化",
        ]
        return "\n".join(lines)

    def build_reflect_context(self, distillate: MemoryDistillate, state: InterviewState) -> str:
        """reflect 阶段上下文 - 深度反思"""
        scores = [t.score for t in distillate.competency_vector]
        avg_score = sum(scores) / len(scores) if scores else 0.5

        lines = [
            "【当前阶段】reflect - 深度反思",
            f"前几轮平均评分：{avg_score:.2f}",
            "",
            "请深入探讨：",
            "1. 如果重来一次，会如何改进项目？",
            "2. 技术选型的 Trade-off 思考",
            "3. 数据量扩大 100 倍时的优化思路",
        ]
        return "\n".join(lines)

    def generate_coding_problem(self, distillate: MemoryDistillate, difficulty: str = "medium") -> CodingProblem:
        """生成中等算法题"""
        tech_stack = self._extract_tech_stack(distillate)
        from interview_crew.services.code_sandbox import code_sandbox
        return code_sandbox.generate_problem(tech_stack, difficulty)

    def _extract_tech_stack(self, distillate: MemoryDistillate) -> List[str]:
        """从简历和画像中提取技术栈"""
        tech_stack = []
        profile = distillate.candidate_profile

        if "tech_stack" in profile:
            tech_stack = [t.strip() for t in profile["tech_stack"].split(",")]
        elif "skills" in profile:
            tech_stack = [t.strip() for t in profile["skills"].split(",")]

        return tech_stack or ["Python", "Java"]
