from pathlib import Path
from interview_crew.agents.base import BaseAgent
from interview_crew.protocol.schemas import MemoryDistillate
from interview_crew.config import settings


class HRAgent(BaseAgent):
    name = "hr"
    prompt_path = Path(__file__).parent.parent / "prompts" / "hr.txt"
    preferred_model = settings.qwen_plus_model
    default_temperature = 0.7

    def build_context(self, distillate: MemoryDistillate) -> str:
        lines = ["候选人画像摘要："]
        for k, v in distillate.candidate_profile.items():
            lines.append(f"- {k}：{v}")
        lines.append("能力标签：")
        for tag in distillate.competency_vector:
            lines.append(f"- {tag.dimension}: {tag.score}")
        if distillate.contradiction_alerts:
            lines.append("跨轮矛盾点（重点核查）：")
            for alert in distillate.contradiction_alerts:
                lines.append(f"- {alert}")
        return "\n".join(lines)
