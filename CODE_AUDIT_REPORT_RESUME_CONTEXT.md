# InterviewCrew 代码审计报告：简历上下文注入验证

**审计时间**: 2026-04-03
**审计对象**: `BUG_REPORT_RESUME_CONTEXT.md` 中描述的 Bug
**审计结论**: **Bug 部分存在** - 代码已传递简历，但 Prompt 未指示 Agent 使用

---

## 1. 审计方法

1. 对比 Bug 报告版本 (`8f78d48`) 与当前版本代码
2. 追踪 `resume_text` 数据流：API → State → Engine → Agent → Messages
3. 审查各 Agent 的系统提示 (prompt) 是否包含简历利用指令
4. 分析实际测试日志验证现象

---

## 2. 数据流审计

### 2.1 代码修复状态

| 文件 | 行号 | 修复状态 | 说明 |
|------|------|---------|------|
| `state.py` | 18-20 | ✅ 已定义 | `resume_path` 和 `resume_text` 字段存在 |
| `engine.py` | 64-70 | ✅ 已加载 | `_maybe_load_files()` 读取简历内容到 `resume_text` |
| `engine.py` | 124, 135, 321 | ✅ 已传递 | 调用 Agent 时传入 `resume_context=self.state.resume_text` |
| `base.py` | 47, 52-54, 90, 110 | ✅ 已支持 | `invoke()` 和 `_prepare_input()` 支持 `resume_context` 参数 |
| `agent_mailbox.py` | 10, 20-26 | ✅ 已注入 | `build_agent_messages()` 添加 【候选人简历】system message |

### 2.2 数据流验证

```
CLI/API 输入 resume 路径
    ↓
InterviewState.resume_path (state.py:18)
    ↓
Orchestrator._maybe_load_files() (engine.py:64-70)
    ↓
InterviewState.resume_text (state.py:20)
    ↓
Orchestrator.step() / _generate_report() (engine.py:124, 135, 321)
    ↓
BaseAgent.invoke(resume_context=...) (base.py:83-102)
    ↓
BaseAgent._prepare_input() (base.py:42-55)
    ↓
build_agent_messages(resume_context=...) (agent_mailbox.py:5-30)
    ↓
Messages 列表中的 【候选人简历】system message
```

**结论**: 简历数据流完整，简历内容确实被传递到 LLM 的 messages 列表中。

---

## 3. Prompt 审计

### 3.1 各 Agent 系统提示检查

| Agent | Prompt 文件 | 简历相关指令 | 状态 |
|-------|------------|-------------|------|
| Tech1 | `prompts/tech1.txt` | ❌ 无任何提及 | **缺失** |
| Tech2 | `prompts/tech2.txt` | ❌ 无任何提及 | **缺失** |
| SysDes | `prompts/sysdes.txt` | ❌ 无任何提及 | **缺失** |
| HR | `prompts/hr.txt` | ❌ 无任何提及 | **缺失** |
| Scribe | `prompts/scribe.txt` | ❌ 无任何提及 | **缺失** |

### 3.2 Tech1 Prompt 原文

```
你是一位基础技术面试官（Junior Coder），风格严谨，关注代码细节和基础原理的准确性。

规则：
- 每次只提出 1 个问题。
- 问题聚焦算法基础、语言特性、常见八股或代码实现细节。
- 不能透露自己是 AI。
- 保持角色一致性。
```

**关键问题**: 规则第3条要求"问题聚焦算法基础、语言特性、常见八股"，完全没有提及应基于简历项目经历提问。

---

## 4. 实际测试验证

### 4.1 测试日志分析 (`TEST_LOG_FIX_VERIFICATION.md`)

| 轮次 | Agent | 实际提问 | 简历项目关联 |
|------|-------|---------|-------------|
| 1 | Tech1 | FastAPI async/sync 区别 | ❌ 通用八股 |
| 2 | Tech2 | 线程池大小与阻塞 | ❌ 通用架构 |
| 3 | SysDes | 超时/熔断/压测 | ❌ 通用设计 |

**缺失的简历关联问题**:
- ❌ RepoMind：AST 分块策略、MQE 查询扩展
- ❌ CueZero：Ghost Ball 启发式、MCTS 剪枝
- ❌ DiabEyeDet：医学影像处理经验
- ❌ MCP 协议：实际落地挑战

### 4.2 现象解释

虽然简历内容通过 `【候选人简历】` system message 被传递给 LLM，但：

1. **系统提示无指令**: Prompt 未要求 Agent "基于简历提问" 或 "深挖项目经历"
2. **角色定位偏通用**: Tech1 Prompt 明确要求"聚焦算法基础、语言特性、常见八股"
3. **缺乏简历利用机制**: 没有指示 Agent 如何从简历中提取技术点并转化为问题

**结果**: LLM 虽能看到简历，但未被指示使用它，因此提问基于通用技术栈（FastAPI/asyncio）。

---

## 5. 根因分析

### 5.1 Bug 报告描述 vs 实际情况

| Bug 报告声称 | 实际情况 | 结论 |
|-------------|---------|------|
| "简历上下文未注入 Agent 消息" | 简历已通过 `build_agent_messages` 注入 | ❌ 不准确 |
| "Agent 无法基于简历内容提问" | Agent 确实未基于简历提问 | ✅ 现象正确 |

### 5.2 真正根因

**表面原因**: 简历内容已传递，但 Agent 未利用
**深层原因**: **Prompt 工程缺失** - 各 Agent 的系统提示缺乏以下关键元素：

1. **简历利用指令**: 无 "请基于候选人简历中的项目经历提问"
2. **深挖策略**: 无 "针对简历中的技术关键词进行追问"
3. **首轮触发机制**: Tech1 作为首轮面试官，应从简历中选取切入点

---

## 6. 修复建议

### 6.1 方案 A：修改各 Agent Prompt（推荐）

在 `tech1.txt`, `tech2.txt`, `sysdes.txt` 中添加简历利用指令：

```
你是一位基础技术面试官（Junior Coder），风格严谨，关注代码细节和基础原理的准确性。

规则：
- 每次只提出 1 个问题。
- 优先基于【候选人简历】中的项目经历提问，深挖技术细节。
- 若简历提到具体项目（如 RAG/RL/分布式系统），要求候选人阐述设计思路和实现难点。
- 问题聚焦算法基础、语言特性、代码实现细节。
- 不能透露自己是 AI。
- 保持角色一致性。
```

### 6.2 方案 B：简历预处理 + 显式注入

在 `engine.py` 中对简历进行结构化提取，将关键项目/技术点显式传入 `build_context`：

```python
# 在 MemoryDistillate 或业务上下文中提取简历技术点
distillate.candidate_profile["key_projects"] = extract_projects(resume_text)
```

### 6.3 方案 C：专用项目面试官 (ProjectAgent)

新增专门深挖简历项目的 Agent，在流程中插入：

```python
_state_order = ["screening", "project", "tech1", "tech2", "system", "hr", "finished"]
# project → ProjectAgent 专门深挖简历项目
```

---

## 7. 结论

### 7.1 Bug 状态判定

| 检查项 | 状态 | 说明 |
|--------|------|------|
| 简历数据流 | ✅ 已修复 | 简历内容已传递到 LLM messages |
| Prompt 简历指令 | ❌ 缺失 | 各 Agent Prompt 未要求基于简历提问 |
| 实际面试问题 | ❌ 无关 | 问题仍为通用技术栈，未涉及简历项目 |

**最终判定**: Bug 报告描述的**现象确实存在**（Agent 未基于简历提问），但**根因分析不准确**（不是"未注入"，而是"注入后未被利用"）。

### 7.2 严重级别

建议调整为 **P2（体验优化）**：
- 面试功能正常（问题有效，Scribe 报告正确）
- 但面试深度受限（无法深挖项目经历）
- 修复成本较低（仅需修改 Prompt）

---

## 8. 验证修复的标准

修复后应满足：
- [ ] Tech1 首轮提问涉及简历中的具体项目（如 RepoMind RAG 策略）
- [ ] Tech2 追问项目技术细节（如 CueZero MCTS 剪枝逻辑）
- [ ] SysDes 要求阐述项目架构设计（如 MCP 协议集成方案）
- [ ] 面试问题与简历项目匹配度 > 70%

---

*审计者: Claude Code*
*时间: 2026-04-03*
