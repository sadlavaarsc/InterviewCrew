from pathlib import Path
from interview_crew.agents.base import BaseAgent
from interview_crew.protocol.schemas import MemoryDistillate
from interview_crew.config import settings


class Tech1Agent(BaseAgent):
    name = "tech1"
    prompt_path = Path(__file__).parent.parent / "prompts" / "tech1.txt"
    preferred_model = settings.qwen_plus_model
    default_temperature = 0.7

    def build_context(self, distillate: MemoryDistillate) -> str:
        lines = [
            f"推荐追问方向：{distillate.recommended_focus}",
        ]
        if distillate.candidate_profile:
            for k, v in distillate.candidate_profile.items():
                lines.append(f"- {k}：{v}")
        return "\n".join(lines)
