import json
from typing import List
from interview_crew.state import Message
from interview_crew.protocol.schemas import MemoryDistillate, CompetencyTag
from interview_crew.llm.client import llm, estimate_tokens
from interview_crew.config import settings


_DISTILL_PROMPT = """
你是一位面试记录萃取助手。请从以下对话中提取结构化信息：
1. 候选人能力画像（如强项、弱项）
2. 能力标签及评分（coding/system_design/communication/pressure_resistance/culture_fit）
3. 关键疑点（需后续验证的）
4. 矛盾点（如有）
5. 给下一轮的建议追问方向

请只输出合法的 JSON，不要包含其他文字：
{
  "candidate_profile": {"strong_area": "...", "weak_area": "..."},
  "competency_vector": [
    {"dimension": "coding", "score": 0.8, "evidence": "...", "confidence": 0.9}
  ],
  "doubt_list": ["..."],
  "contradiction_alerts": ["..."],
  "recommended_focus": "..."
}
"""


def distill_memory(raw_dialogue: List[Message], session_id: str, turn: int) -> MemoryDistillate:
    """使用轻量级模型做记忆蒸馏。"""
    # Only use last 10 messages to keep cost low
    recent = raw_dialogue[-10:]
    dialogue_text = "\n".join(
        f"[{m.get('role', 'user')}] {m.get('content', '')}" for m in recent
    )

    messages: List[Message] = [
        {"role": "system", "content": _DISTILL_PROMPT},
        {"role": "user", "content": f"对话记录（最近10轮）：\n{dialogue_text}"},
    ]

    try:
        raw = llm.invoke(messages, model_name=settings.qwen_flash_model, temperature=0.3)
        data = json.loads(raw.strip())
        return MemoryDistillate(**data)
    except Exception as e:
        # Fallback: return a minimal valid distillate so the pipeline never breaks
        return MemoryDistillate(
            candidate_profile={"note": f"distill failed: {e}"},
            competency_vector=[
                CompetencyTag(
                    dimension="coding",
                    score=0.5,
                    evidence="distillation fallback due to parsing error",
                    confidence=0.3,
                )
            ],
            doubt_list=[],
            contradiction_alerts=[],
            recommended_focus="继续按原流程提问",
        )
