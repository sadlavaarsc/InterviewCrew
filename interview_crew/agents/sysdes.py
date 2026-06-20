from pathlib import Path
from interview_crew.agents.base import BaseAgent
from interview_crew.protocol.schemas import MemoryDistillate
from interview_crew.config import settings


class SysDesAgent(BaseAgent):
    name = "sysdes"
    prompt_path = Path(__file__).parent.parent / "prompts" / "sysdes.txt"
    preferred_model = settings.premium_model
    default_temperature = 0.7

    def build_context(self, distillate: MemoryDistillate) -> str:
        lines = [f"推荐追问方向：{distillate.recommended_focus}"]
        lines.append("能力标签：")
        for tag in distillate.competency_vector:
            lines.append(f"- {tag.dimension}: {tag.score} ({tag.evidence})")
        if distillate.contradiction_alerts:
            lines.append("需澄清的矛盾点：")
            for alert in distillate.contradiction_alerts:
                lines.append(f"- {alert}")
        return "\n".join(lines)
