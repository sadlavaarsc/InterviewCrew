from pathlib import Path
from typing import List
from interview_crew.agents.base import BaseAgent
from interview_crew.protocol.schemas import MemoryDistillate, CompetencyTag
from interview_crew.config import settings


class ScribeAgent(BaseAgent):
    name = "scribe"
    prompt_path = Path(__file__).parent.parent / "prompts" / "scribe.txt"
    preferred_model = settings.default_model
    default_temperature = 0.3

    def build_context(self, distillate: MemoryDistillate) -> str:
        """构建完整的上下文信息供 Scribe 生成面评报告。

        充分利用 MemoryDistillate 的所有字段，确保 Scribe 有充足的证据支撑评判。
        """
        context_parts = []

        # 1. 候选人画像摘要
        if distillate.candidate_profile:
            context_parts.append("【候选人画像】")
            for key, value in distillate.candidate_profile.items():
                context_parts.append(f"- {key}: {value}")
            context_parts.append("")

        # 2. 能力维度向量（包含评分、证据、置信度）
        if distillate.competency_vector:
            context_parts.append("【能力维度评估】")
            for tag in distillate.competency_vector:
                context_parts.append(
                    f"- {tag.dimension}: 评分={tag.score:.2f}, "
                    f"置信度={tag.confidence:.2f}, 证据={tag.evidence}"
                )
            context_parts.append("")

        # 3. 质疑点列表
        if distillate.doubt_list:
            context_parts.append("【待澄清质疑点】")
            for i, doubt in enumerate(distillate.doubt_list, 1):
                context_parts.append(f"{i}. {doubt}")
            context_parts.append("")

        # 4. 冲突警告
        if distillate.contradiction_alerts:
            context_parts.append("【回答冲突警告】")
            for i, alert in enumerate(distillate.contradiction_alerts, 1):
                context_parts.append(f"{i}. {alert}")
            context_parts.append("")

        # 5. 推荐关注重点
        if distillate.recommended_focus:
            context_parts.append(f"【推荐关注重点】{distillate.recommended_focus}")

        return "\n".join(context_parts) if context_parts else "全局面评摘要：生成最终面评报告"
