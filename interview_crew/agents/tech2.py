from pathlib import Path
from interview_crew.agents.base import BaseAgent
from interview_crew.protocol.schemas import MemoryDistillate
from interview_crew.config import settings


class Tech2Agent(BaseAgent):
    name = "tech2"
    prompt_path = Path(__file__).parent.parent / "prompts" / "tech2.txt"
    preferred_model = settings.qwen_plus_model
    default_temperature = 0.7

    def build_context(self, distillate: MemoryDistillate) -> str:
        lines = [
            f"推荐追问方向：{distillate.recommended_focus}",
            "关键疑点：",
        ]
        for doubt in distillate.doubt_list:
            lines.append(f"- {doubt}")
        if distillate.contradiction_alerts:
            lines.append("矛盾预警：")
            for alert in distillate.contradiction_alerts:
                lines.append(f"- {alert}")
        return "\n".join(lines)
