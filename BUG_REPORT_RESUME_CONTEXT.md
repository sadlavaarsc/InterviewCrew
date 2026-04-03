# InterviewCrew Bug Report：简历上下文未注入 Agent 消息

**报告人**：Kimi Claw  
**时间**：2026-04-03 10:58  
**版本**：`8f78d48` (main)  
**严重程度**：P1（功能缺陷）  
**影响范围**：面试问题与简历脱节

---

## 1. 问题概述

Scribe 幻觉问题修复后（P0），系统仍存在 **Agent 无法基于简历内容提问** 的缺陷。具体表现为：面试问题始终围绕通用技术栈（FastAPI/asyncio/线程池），未涉及候选人简历中的具体项目经历（RepoMind、CueZero、DiabEyeDet、MCP 协议等）。

---

## 2. 现象验证

**测试会话**：`9d03fde7-084a-4b72-a896-567f0999937c`  
**简历内容**：包含 RepoMind（RAG）、CueZero（RL）、DiabEyeDet（医学影像）、MCP 协议等详细项目描述

**实际面试问题**：
| 轮次 | Agent | 提问内容 | 与简历关联度 |
|------|-------|----------|-------------|
| 1 | Tech1 | FastAPI async/sync 区别 | ❌ 通用问题 |
| 2 | Tech2 | 线程池大小与阻塞 | ❌ 通用问题 |
| 3 | SysDes | 超时/熔断/压测 | ❌ 通用架构 |
| 4 | Scribe | 面评报告 | ✅ 基于问答评估 |

**缺失的简历关联问题**：
- ❌ RepoMind：AST 分块策略、MQE 查询扩展、MCP 协议集成细节
- ❌ CueZero：Ghost Ball 启发式、MCTS 剪枝、自对弈训练管道
- ❌ MCP 协议：分布式一致性、容错机制、实际落地挑战

---

## 3. 根因分析

**代码验证**（`interview_crew/agents/base.py:42-52`）：

```python
def _prepare_input(self, inputs: dict) -> dict:
    ...
    messages = build_agent_messages(
        history,           # Agent 私有历史
        full_system,       # System prompt + build_context
        candidate_response, # 本轮回答
        business_context   # JD 解析结果
    )
    # 注意：state.resume_text 从未传入
```

**关键缺陷**：
1. `InterviewState.resume_text` 已挂载（`engine.py:64-70` 确认）
2. 但 `BaseAgent._prepare_input()` 未将简历内容注入 messages
3. `build_agent_messages()` 无 `resume_context` 参数支持

**导致结果**：
- Tech1/2/SysDes 只能看到候选人首轮简述（"熟悉 Python/LangChain"）
- 无法读取 `resume.md` 中的详细项目描述
- 提问只能基于通用技术栈关键词，无法深挖项目经历

---

## 4. 修复建议

**方案 A：修改 `build_agent_messages`（推荐）**

在 `interview_crew/memory/agent_mailbox.py` 中：
```python
def build_agent_messages(
    history, 
    system_prompt, 
    candidate_response, 
    business_context,
    resume_context=None  # 新增
):
    messages = [...]
    if resume_context:
        messages.insert(1, {
            "role": "system", 
            "content": f"【候选人简历】\n{resume_context[:2000]}"
        })
    return messages
```

**方案 B：修改 `BaseAgent.build_context`**

各 Agent 子类在 `build_context()` 中主动提取 `state.resume_text` 并摘要。

**建议优先级**：P1（本周内修复）

---

## 5. 验证标准

修复后测试应验证：
- [ ] Tech1 提问涉及 RepoMind 的 RAG 策略细节
- [ ] Tech2 追问 CueZero 的 MCTS 剪枝逻辑
- [ ] SysDes 要求阐述 MCP 协议在 RepoMind 中的实际集成方案
- [ ] 面试问题与简历项目经历匹配度 > 70%

---

**附件**：
- 测试日志：`TEST_LOG_FIX_VERIFICATION.md`
- 简历原文：`resume.md`
- 相关代码：`interview_crew/agents/base.py`, `interview_crew/memory/agent_mailbox.py`
