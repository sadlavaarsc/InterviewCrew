from pathlib import Path
from typing import List
from interview_crew.agents.base import BaseAgent
from interview_crew.protocol.schemas import MemoryDistillate, CodingProblem
from interview_crew.config import settings
from interview_crew.state import InterviewState


class Tech1Agent(BaseAgent):
    """
    Tech1 Agent - 基础技术面试
    三阶段结构：chat (寒暄+八股) -> coding (简单算法) -> reflect (反思)
    """
    name = "tech1"
    prompt_path = Path(__file__).parent.parent / "prompts" / "tech1.txt"
    preferred_model = settings.premium_model
    default_temperature = 0.7
    has_sub_stages = True

    def build_context(self, distillate: MemoryDistillate) -> str:
        """chat 阶段上下文 - 项目简述和八股"""
        lines = [
            "【当前阶段】chat - 寒暄与八股问答",
            f"推荐追问方向：{distillate.recommended_focus}",
            "候选人画像：",
        ]
        if distillate.candidate_profile:
            for k, v in distillate.candidate_profile.items():
                lines.append(f"- {k}：{v}")

        lines.append("\n请先让候选人简述简历项目，然后问基础八股问题。")
        return "\n".join(lines)

    def build_coding_context(self, distillate: MemoryDistillate, state: InterviewState) -> str:
        """coding 阶段上下文 - 生成简单算法题"""
        tech_stack = self._extract_tech_stack(distillate)
        difficulty = "easy"

        lines = [
            "【当前阶段】coding - 简单算法题",
            f"候选人技术栈：{', '.join(tech_stack)}",
            f"推荐难度：{difficulty} (LeetCode Easy 级别)",
            "",
            "请生成一道简单的算法题，要求：",
            "1. 与候选人技术栈相关",
            "2. 提供 starter_code",
            "3. 提供 2-3 个测试用例",
            "4. 在 coding_problem 字段中返回题目信息",
        ]
        return "\n".join(lines)

    def build_reflect_context(self, distillate: MemoryDistillate, state: InterviewState) -> str:
        """reflect 阶段上下文 - 反思总结"""
        scores = [t.score for t in distillate.competency_vector]
        avg_score = sum(scores) / len(scores) if scores else 0.5

        lines = [
            "【当前阶段】reflect - 反思总结",
            f"前几轮平均评分：{avg_score:.2f}",
            "",
            "请询问：",
            "1. 候选人对自己表现的评价",
            "2. 或一个开放性技术问题",
            "3. 结束 Tech1 面试前的总结性问题",
        ]
        return "\n".join(lines)

    def generate_coding_problem(self, distillate: MemoryDistillate, difficulty: str = "easy") -> CodingProblem:
        """生成简单算法题"""
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
