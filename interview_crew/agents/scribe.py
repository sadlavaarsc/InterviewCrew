from pathlib import Path
from interview_crew.agents.base import BaseAgent
from interview_crew.protocol.schemas import MemoryDistillate
from interview_crew.config import settings


class ScribeAgent(BaseAgent):
    name = "scribe"
    prompt_path = Path(__file__).parent.parent / "prompts" / "scribe.txt"
    preferred_model = settings.qwen_flash_model
    default_temperature = 0.3

    def build_context(self, distillate: MemoryDistillate) -> str:
        # Scribe receives a condensed summary of all transfer packages via the distillate
        return f"全局面评摘要：{distillate.recommended_focus}"
