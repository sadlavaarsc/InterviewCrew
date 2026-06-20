import json
from abc import ABC, abstractmethod
from typing import Optional
from interview_crew.protocol.schemas import BusinessContext
from interview_crew.llm.client import llm
from interview_crew.llm.model_resolver import get_default_model


class JDParsingStrategy(ABC):
    @abstractmethod
    def parse(self, jd_markdown: str) -> BusinessContext:
        raise NotImplementedError


_LLM_JD_PROMPT = """
你是一位 JD 解析助手。请将以下职位描述（Markdown 格式）解析为结构化的 JSON。
不要包含任何其他文字，只返回合法 JSON：
{
  "domain": "业务领域",
  "team_size": "团队规模描述（可选）",
  "tech_stack": ["技术栈1", "技术栈2"],
  "core_challenges": ["核心业务挑战1", "核心业务挑战2"],
  "growth_stage": "初创/成长期/成熟期（可选）",
  "key_performance_metrics": ["关键绩效指标1", "关键绩效指标2"]
}
"""


class LLMJDParser(JDParsingStrategy):
    def parse(self, jd_markdown: str) -> BusinessContext:
        messages = [
            {"role": "system", "content": _LLM_JD_PROMPT},
            {"role": "user", "content": jd_markdown},
        ]
        try:
            raw = llm.invoke(messages, model_name=get_default_model(), temperature=0.3)
            data = json.loads(raw.strip())
            return BusinessContext(**data)
        except Exception as e:
            # Fallback: return minimal context
            return BusinessContext(
                domain="未知",
                core_challenges=[f"JD 解析失败: {e}"],
            )
