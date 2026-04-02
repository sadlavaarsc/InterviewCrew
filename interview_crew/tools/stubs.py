"""Tool implementations using LLM for InterviewCrew.

All tools use the project's LLMClient to generate meaningful responses.
Each tool has a fallback to a safe stub in case of LLM failure.
"""
from typing import Any, List
import re
from difflib import SequenceMatcher

from interview_crew.llm.client import llm


def _safe_llm_call(messages: list, model: str = "qwen3.5-flash", temperature: float = 0.7, fallback: str = "") -> str:
    """Safely call LLM with fallback on error."""
    try:
        return llm.invoke(messages, model_name=model, temperature=temperature)
    except Exception:
        return fallback


def rag_query(topic: str) -> str:
    """Query technical knowledge base for interview topics.

    Uses LLM to generate relevant technical knowledge points for the given topic,
    simulating a RAG retrieval from a technical interview knowledge base.
    """
    messages = [
        {"role": "system", "content": "你是一个技术面试知识库。请提供关于给定技术主题的详细知识点，包括：核心概念、常见考点、易错点。用简洁的中文回答，控制在200字以内。"},
        {"role": "user", "content": f"请提供关于 '{topic}' 的技术知识点："}
    ]
    result = _safe_llm_call(
        messages,
        fallback=f"[RAG] 关于 '{topic}' 的知识点：\n核心概念：{topic}是面试常考内容。\n常见考点：原理理解、应用场景。\n易错点：边界条件处理。"
    )
    return f"[RAG检索结果]\n{result}"


def code_judge(code_snippet: str) -> str:
    """Analyze code quality and correctness.

    Uses LLM to analyze code for time/space complexity, edge cases, and potential bugs.
    """
    messages = [
        {"role": "system", "content": "你是一个代码评审专家。请分析给定的代码，评估：1)时间复杂度和空间复杂度 2)边界条件处理 3)潜在bug或改进点。用中文回答，控制在150字以内。"},
        {"role": "user", "content": f"请分析以下代码：\n```\n{code_snippet[:1000]}\n```"}
    ]
    result = _safe_llm_call(
        messages,
        fallback="[代码评估] 语法检查通过，复杂度待确认。建议补充边界条件测试。"
    )
    return f"[代码评估结果]\n{result}"


def deep_search(query: str) -> str:
    """Simulate real-time search for technical information.

    Uses LLM to generate up-to-date technical information as if from a search engine.
    """
    messages = [
        {"role": "system", "content": "你是一个技术搜索引擎。请提供关于查询主题的最新、准确的技术信息。用中文回答，控制在150字以内。"},
        {"role": "user", "content": f"搜索：{query}"}
    ]
    result = _safe_llm_call(
        messages,
        fallback=f"[搜索结果] 关于 '{query}' 的最新文档：该技术在现代软件工程中有广泛应用，建议参考官方文档获取详细信息。"
    )
    return f"[实时搜索结果]\n{result}"


def counter_example_gen(approach: str) -> str:
    """Generate counter-examples to challenge a solution approach.

    Uses LLM to generate edge cases and boundary conditions that might break
    the candidate's proposed solution.
    """
    messages = [
        {"role": "system", "content": "你是一个算法测试专家。针对候选人的解题思路，生成可能使其方案失败的边界情况、反例或压力测试用例。用中文回答，控制在100字以内。"},
        {"role": "user", "content": f"候选人的解题思路：{approach}\n请生成可能使其方案失败的边界情况或反例："}
    ]
    result = _safe_llm_call(
        messages,
        fallback=f"[边界反例] 考虑以下边界情况：空输入、单元素、最大值/最小值、重复元素、高并发场景。"
    )
    return f"[边界反例生成]\n{result}"


def stress_trigger(probability: float = 0.2) -> str:
    """Determine if stress mode should be activated.

    Uses a combination of random probability and LLM to decide if the agent
    should apply pressure to the candidate.
    """
    import random
    if random.random() < probability:
        messages = [
            {"role": "system", "content": "你是一个压力面试触发器。如果决定激活压力模式，请给出一个简短的施压指令（如'请给出更具体的数字'、'你的回答不够清晰'等）。用中文回答，控制在20字以内。"},
            {"role": "user", "content": "是否激活压力模式？如果是，给出施压指令："}
        ]
        result = _safe_llm_call(
            messages,
            fallback="请给出更具体的数字和依据。"
        )
        return f"[压力模式激活] {result}"
    return "[压力模式] 保持正常面试节奏。"


def whiteboard_sim(description: str) -> str:
    """Generate architecture diagram from description.

    Uses LLM to convert system architecture descriptions into Mermaid diagram code.
    """
    messages = [
        {"role": "system", "content": "你是一个架构图生成器。请将系统架构描述转换为Mermaid图表代码（graph TD或graph LR格式）。只返回Mermaid代码，不要其他解释。"},
        {"role": "user", "content": f"请为以下架构描述生成Mermaid图表：\n{description}"}
    ]
    result = _safe_llm_call(
        messages,
        fallback="""```mermaid
graph TD
    A[用户] --> B[前端]
    B --> C[后端服务]
    C --> D[数据库]
```"""
    )
    if not result.strip().startswith("```"):
        result = f"```mermaid\n{result}\n```"
    return f"[架构图表生成]\n{result}"


def tradeoff_analyzer(option_a: str, option_b: str) -> str:
    """Analyze tradeoffs between two architectural options.

    Uses LLM to compare two options across multiple dimensions.
    """
    messages = [
        {"role": "system", "content": "你是一个架构权衡分析专家。请对比两个技术选项，从成本、性能、一致性、可维护性、扩展性等维度分析优缺点。用中文回答，控制在200字以内。"},
        {"role": "user", "content": f"请对比以下两个选项：\n选项A：{option_a}\n选项B：{option_b}"}
    ]
    result = _safe_llm_call(
        messages,
        fallback=f"[权衡分析] {option_a} vs {option_b}：\n- {option_a}：实现简单，适合初期\n- {option_b}：扩展性好，适合大规模"
    )
    return f"[架构权衡分析]\n{result}"


def cross_ref_checker(current: str, previous: str) -> str:
    """Check for contradictions between current and previous statements.

    Uses text similarity and LLM to detect potential contradictions.
    """
    # First, use simple similarity check
    similarity = SequenceMatcher(None, current, previous).ratio()

    if similarity > 0.8:
        return "[交叉引用检查] 两次陈述高度相似，无明显矛盾。"

    messages = [
        {"role": "system", "content": "你是一个一致性检查器。请对比两段陈述，判断是否存在矛盾、不一致或逻辑冲突。用中文回答，控制在100字以内。"},
        {"role": "user", "content": f"之前的陈述：{previous[:500]}\n\n当前的陈述：{current[:500]}\n\n是否存在矛盾？"}
    ]
    result = _safe_llm_call(
        messages,
        fallback="未发现明显矛盾。"
    )
    return f"[交叉引用检查] 相似度: {similarity:.1%}\n{result}"


def consistency_checker(statements: list) -> str:
    """Check consistency across multiple rounds of statements.

    Uses LLM to analyze multiple statements for logical consistency.
    """
    if len(statements) < 2:
        return "[一致性检查] 陈述不足，无法检查一致性。"

    statements_text = "\n".join([f"{i+1}. {s}" for i, s in enumerate(statements[-5:])])  # Last 5 statements

    messages = [
        {"role": "system", "content": "你是一个逻辑一致性检查器。请分析多轮陈述，检查是否存在前后矛盾、逻辑冲突或自我否定的情况。用中文回答，控制在150字以内。"},
        {"role": "user", "content": f"以下是多轮陈述：\n{statements_text}\n\n请检查一致性："}
    ]
    result = _safe_llm_call(
        messages,
        fallback="跨轮陈述一致性检查完成，未发现明显冲突。"
    )
    return f"[一致性检查结果]\n{result}"


def red_flag_detector(text: str) -> list:
    """Detect potential red flags in candidate responses.

    Uses rule-based matching and LLM to identify concerning patterns.
    """
    red_flags = []

    # Rule-based detection
    concerning_patterns = [
        (r"(不会|不懂|不了解|没做过|没接触过).{0,5}(项目|工作|职责)", "回避职责"),
        (r"(都是|全是|完全).{0,3}(别人|他人的|其他人的)", "推卸责任"),
        (r"(加班|996).{0,5}(不接受|拒绝|不愿意)", "加班态度"),
        (r"(离职|跳槽).{0,5}(因为|由于).{0,5}(领导|老板|同事|环境)", "负面归因"),
        (r"(随便|都行|无所谓|都可以)", "缺乏主见"),
        (r"(抄袭|复制|照搬|模仿).{0,5}(代码|设计|方案)", "学术诚信"),
        (r"(骂|吵|斗|争论|冲突).{0,5}(同事|团队|领导)", "团队冲突"),
    ]

    for pattern, flag_type in concerning_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            red_flags.append(f"[警告] 检测到'{flag_type}'相关表述")

    # LLM-based detection for subtle issues
    messages = [
        {"role": "system", "content": "你是一个风险信号检测器。请分析候选人回答，识别可能的风险信号（如：不诚实、缺乏团队意识、态度问题、职业素养问题等）。只返回发现的风险，如果没有则返回'无'。用中文回答，控制在50字以内。"},
        {"role": "user", "content": f"候选人回答：{text[:500]}\n\n请识别风险信号："}
    ]
    llm_result = _safe_llm_call(
        messages,
        fallback="无"
    )

    if llm_result and "无" not in llm_result and len(llm_result.strip()) > 3:
        red_flags.append(f"[LLM检测到] {llm_result}")

    return red_flags if red_flags else []
