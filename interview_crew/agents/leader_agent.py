from pathlib import Path
from typing import List
from interview_crew.agents.base import BaseAgent
from interview_crew.protocol.schemas import MemoryDistillate
from interview_crew.config import settings


class LeaderAgent(BaseAgent):
    """
    Leader Agent - 技术团队 Manager 面试
    评估项目 Ownership、团队协作、商业敏感度与文化匹配度
    """
    name = "leader"
    prompt_path = Path(__file__).parent.parent / "prompts" / "leader.txt"
    preferred_model = settings.qwen_plus_model
    default_temperature = 0.5

    def build_context(self, distillate: MemoryDistillate) -> str:
        """构建 Leader 面上下文"""
        context_parts = []

        # 1. 候选人画像
        if distillate.candidate_profile:
            context_parts.append("【候选人画像】")
            for k, v in distillate.candidate_profile.items():
                context_parts.append(f"- {k}: {v}")

        # 2. 能力维度评分
        if distillate.competency_vector:
            context_parts.append("\n【技术能力评估】")
            for tag in distillate.competency_vector:
                context_parts.append(
                    f"- {tag.dimension}: {tag.score:.2f} (置信度: {tag.confidence:.2f})"
                )
                context_parts.append(f"  证据: {tag.evidence}")

        # 3. 需要核查的矛盾点
        if distillate.contradiction_alerts:
            context_parts.append("\n【需核查的矛盾点】")
            for i, alert in enumerate(distillate.contradiction_alerts, 1):
                context_parts.append(f"{i}. {alert}")

        # 4. 前几轮疑点
        if distillate.doubt_list:
            context_parts.append("\n【前几轮疑点】")
            for i, doubt in enumerate(distillate.doubt_list, 1):
                context_parts.append(f"{i}. {doubt}")

        # 5. 推荐关注重点
        if distillate.recommended_focus:
            context_parts.append(f"\n【推荐关注重点】{distillate.recommended_focus}")

        return "\n".join(context_parts) if context_parts else "请评估候选人的项目 Ownership 和团队协作能力。"
