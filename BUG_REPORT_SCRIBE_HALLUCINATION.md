# InterviewCrew Bug 排查报告：Scribe 面评幻觉

**受访对象**: 匿名用户
**测试场景**: Agent JD 专业面试
**Session ID**: 7c2ede1c-3c55-4b53-9bae-a973febcabe6
**排查时间**: 2026-04-03
**对应代码版本**: `be9e025` (main)

---

## 1. 执行摘要

| 项 | 结论 |
|---|---|
| **Bug 真实性** | **确认存在**。Scribe 报告中的 RAG/RL/MCP/熔断等评判点，与实际面试内容（asyncio/阻塞 IO/线程池隔离）完全无关。 |
| **核心根因** | `_generate_report()` 方法对 Scribe 的**输入上下文极度压缩且构造错误**，导致 Scribe Agent 看不到实际 Q&A，只能基于贫乏摘要 + JD 关键词进行幻觉生成。 |
| **次要根因** | 各 Agent 的 `business_context` 仅包含 JD 结构化摘要，**完整简历原文 (`resume_text`) 从未注入任何 Agent 的消息列表**，导致前几轮 Agent 也无法基于项目经历提问。 |
| **轮数影响** | `max_turns=4` 确实跳过了 `hr` 轮，但这只是减少了追问深度，**不是 Scribe 幻觉的直接原因**。 |

---

## 2. 异常现象逐项确认

### 2.1 实际面试内容 vs Scribe 评判内容

从 `TEST_LOG_AGENT_JD.md` 提取的面试实录：

| 轮次 | Agent | 实际提问 | 实际回答主题 |
|---|---|---|---|
| 1 | tech1 | `async def` 调用返回什么？事件循环如何恢复协程？ | asyncio 基础、coroutine、`__await__` |
| 2 | tech2 | 阻塞同步 IO / CPU 计算无 `await` 时，事件循环会怎样？ | 阻塞 IO 会卡住事件循环、`run_in_executor` |
| 3 | sysdes | 高并发 RAG 下 CPU/IO 混合负载的线程池隔离策略 | 双线程池隔离、semaphore、ProcessPoolExecutor |

Scribe 报告（节选）中的评判点：

- "RAG项目缺乏深入细节" → **未涉及 RAG 实现细节的讨论**（只讨论了通用线程池隔离，未涉及 RAG 项目的 API 延迟优化、缓存策略）
- "强化学习未提供缓解措施" → **未涉及任何强化学习问题**
- "MCP协议理解停留在理论" → **未涉及 MCP 协议**
- "熔断策略回答空洞" → **面试中根本未提问熔断机制**

**结论：Scribe 报告属于典型的"基于简历关键词的期望型幻觉"。**

---

## 3. 根因分析：对三个推测的代码级验证

### 3.1 推测 1：Scribe Prompt / 输入构造缺陷——确认，且是主要原因

#### 3.1.1 Scribe Prompt 本身未预设维度，但过于笼统

`interview_crew/prompts/scribe.txt` 内容：

```
你是一位客观中立的面试记录员（Scribe），负责根据多轮面试记录生成结构化面评报告。
规则：
- 基于所有轮次的 Transfer Packages 和关键 Q&A 生成面评。
- 结论必须有证据支撑。
- 输出必须是指定格式的 JSON。
```

问题：**Prompt 要求"基于 Transfer Packages 和关键 Q&A"，但代码实现完全没有把这些内容以可读形式喂给 Scribe。**

#### 3.1.2 `_generate_report()` 的输入构造存在严重缺陷

关键代码路径：`interview_crew/orchestrator/engine.py:210-243`

```python
def _generate_report(self) -> str:
    ...
    combined = "\n".join(
        f"Round {p.round_completed} [{p.from_agent}]: score={p.evaluation_score}, focus={p.distillate.recommended_focus}"
        for p in self.state.transfer_queue
    )
    synthetic_distillate = MemoryDistillate(
        candidate_profile={"summary": combined},
        competency_vector=[],
        doubt_list=[],
        contradiction_alerts=[],
        recommended_focus="生成最终面评报告",
    )
    output = scribe.invoke(
        synthetic_distillate,
        candidate_response=combined,
        history=self.state.get_agent_history("scribe"),
        business_context=self._business_context_text(),
    )
```

**缺陷证据链：**

| 缺失项 | 影响 |
|---|---|
| **未传入 `unified_history`** | Scribe 完全看不到任何 Q&A 原文，无法基于实际对话评估。 |
| **严重压缩 `TransferPackage` 信息** | `combined` 仅包含每轮的 `score` + `recommended_focus`，丢弃了 `TransferPackage` 中丰富的 `distillate.candidate_profile`、`doubt_list`、`contradiction_alerts` 和 `agent_question`。 |
| **`competency_vector=[]` 被清空** | Scribe 看不到任何能力维度标签。 |
| **`history` 为空** | `scribe_history` 在终态前从未被写入（scribe 只在 finished 时被调用），所以 `history=[]`。 |
| **Scribe 的 `build_context` 几乎为空** | `ScribeAgent.build_context()` 只返回 `"全局面评摘要：{distillate.recommended_focus}"`，即 `"全局面评摘要：生成最终面评报告"`，未提供任何额外上下文。 |

**最终导致 Scribe 收到的 messages 列表近似为：**

```python
[
  {"role": "system", "content": "你是一位客观中立的面试记录员... \n\n【记忆摘要】\n全局面评摘要：生成最终面评报告"},
  {"role": "system", "content": "【业务背景】\n业务领域：...\n技术栈：..."},
  {"role": "user", "content": "Round 1 [tech1]: score=0.0, focus=...\nRound 2 [tech2]: score=0.8, focus=...\nRound 3 [sysdes]: score=0.75, focus=..."}
]
```

在这个输入下，LLM 被要求生成一份"有证据支撑"的详细技术评估，但它**没有任何一轮的问答原文**。它只能：
1. 从 `business_context`（JD 解析结果）中看到 "AIGC、机器学习、深度学习、**强化学习**" 等关键词；
2. 从训练先验中知道 Resume 里含有 "RAG / MCP / RL"；
3. 基于这些碎片信息**脑补**出一篇"看似合理"但实际与面试内容无关的面评。

**结论：推测 1 成立，且是本次 bug 的首要根因。**

---

### 3.2 推测 2：上下文缺失（完整简历未挂载或未注入 Agent）——部分确认，是次要根因

#### 3.2.1 API 层面确实传递了 resume/jd 路径

`api.py:74-87` 在创建 session 时传递了 `resume_path` 和 `jd_path`：

```python
state = InterviewState(
    ...
    resume_path=req.resume_path,
    jd_path=req.jd_path,
)
orchestrator = Orchestrator(state)
```

#### 3.2.2 Orchestrator 确实读取了文件内容

`engine.py:64-70`：

```python
def _maybe_load_files(self) -> None:
    if self.state.resume_path and Path(self.state.resume_path).exists():
        self.state.resume_text = Path(self.state.resume_path).read_text(encoding="utf-8")
    if self.state.jd_path and Path(self.state.jd_path).exists():
        self.state.jd_text = Path(self.state.jd_path).read_text(encoding="utf-8")
        if not self.state.business_context:
            self.state.business_context = self.jd_parser.parse(self.state.jd_text)
```

所以 `resume_text` 和 `jd_text` **确实被挂载到了 `InterviewState`**。

#### 3.2.3 但完整简历从未进入任何 Agent 的消息列表——这是真正的问题

查看 `BaseAgent._prepare_input()`（`base.py:42-52`）：

```python
def _prepare_input(self, inputs: dict) -> dict:
    ...
    messages = build_agent_messages(history, full_system, candidate_response, business_context)
    return {"messages": messages, "meta": inputs}
```

`build_agent_messages()`（`agent_mailbox.py:5-22`）的输入只有：
- `system_prompt`（Agent 的系统提示 + `build_context` 产出的摘要）
- `business_context`（JD 解析后的结构化文本）
- `private_history`（该 Agent 自己的历史）
- `candidate_response`（本轮候选人的回答）

**`resume_text` 从未作为 system message 或 context 插入到 messages 中。**

这意味着：
- Tech1/2/SysDes 只能看到候选人的简短自我介绍（第一轮 `candidate_response` 中的简历简述）和 JD 摘要；
- 它们**看不到 `resume.md` 中详细的 RepoMind、CueZero、DiabEyeDet 项目描述**；
- 因此 Agent 没有基于项目经历提问，而是基于通用技术栈（Python/FastAPI）提问，这是完全符合代码行为的。

**对 Scribe 报告的影响：**

由于前几轮 Agent 没有基于项目追问，面试记录中自然也不会出现 RAG/MCP/RL 的问答。但 Scribe 在缺乏真实上下文的情况下，**可能从 `business_context` 的 "强化学习" 关键词和自身训练数据中的简历项目先验**出发，强行把这些项目写进了报告。

**结论：推测 2 部分成立。文件已挂载到 state，但未注入 Agent 上下文，是导致前几轮提问偏离简历、以及 Scribe 进一步幻觉的深层原因。**

---

### 3.3 推测 3：轮数压缩导致流程畸形——确认存在流程跳过，但与 Scribe 幻觉无直接因果关系

#### 3.3.1 轮数映射验证

`_state_order` 定义为：
```python
["screening", "tech1", "tech2", "system", "hr", "finished"]
```

当 `max_turns=4` 时，执行流程如下：

| Step | `turn` | `_next_state()` 返回值 | Agent | 说明 |
|---|---|---|---|---|
| 1 | 1 | screening | tech1 | screening 映射到 tech1 |
| 2 | 2 | tech1 | tech2 | |
| 3 | 3 | tech2 | sysdes | |
| 4 | 4 | system | **finished**（因 `turn >= max_turns`） | 直接触发 Scribe |

确实：
- `hr` 轮被跳过。
- `screening` 名存实亡（它本身就是 tech1 的别名）。
- 没有专门的 "项目面试官"（ProjectAgent）轮次，当前系统只有 tech1/tech2/sysdes/hr/scribe 五个 Agent。

#### 3.3.2 轮数压缩是否导致了 Scribe 幻觉？

**没有直接因果关系。** 即使 `max_turns=6` 完整跑了 hr 轮，只要 `_generate_report()` 的输入构造方式不变，Scribe 仍然看不到 Q&A 原文，仍然会产生类似的幻觉（可能只是多了一段 hr 行为评估）。

但轮数压缩**放大了问题的可见性**：因为 Tech1/2/SysDes 在 3 轮内只讨论了通用 asyncio 问题，完全没有涉及简历项目，这使得 Scribe 报告中强行出现的 "RAG/RL/MCP" 显得格外突兀和不可接受。

**结论：推测 3 的"轮数压缩"现象确实存在，但它是暴露 bug 的放大镜，而非产生 bug 的根因。**

---

## 4. 关键代码路径汇总

| 文件 | 行号 | 问题描述 |
|---|---|---|
| `interview_crew/orchestrator/engine.py` | 210-243 | `_generate_report()` 严重丢失上下文：未传入 `unified_history`，仅压缩 `transfer_queue` 为 score+focus 纯文本。 |
| `interview_crew/agents/scribe.py` | 13-15 | `ScribeAgent.build_context()` 几乎为空，未提取 `candidate_profile` 或 `doubt_list`。 |
| `interview_crew/agents/base.py` | 42-52 | `_prepare_input()` 未将 `resume_text` / `jd_text` / `unified_history` 注入 messages。 |
| `interview_crew/memory/agent_mailbox.py` | 5-22 | `build_agent_messages()` 缺乏对简历全文或统一历史的支持。 |
| `interview_crew/orchestrator/engine.py` | 50-56, 92-97 | `_state_order` + `max_turns` 约束导致 `hr` 轮被跳过（当 max_turns=4 时）。 |

---

## 5. 结论与后续修复建议（优先级排序）

### P0：修复 Scribe 的输入上下文（直接根因）

`_generate_report()` 必须把 **实际可验证的上下文** 喂给 Scribe，包括但不限于：
- 将 `unified_history` 全文（或最近 N 轮摘要）传入 Scribe 的 `candidate_response` 或 `history`。
- 将每个 `TransferPackage` 的 `distillate`（`candidate_profile`、`doubt_list`、`competency_vector`）结构化拼接进 `synthetic_distillate`，而不是只取 `recommended_focus`。
- 禁止 Scribe 在没有对应 Q&A 证据的情况下评判某个技术点。

### P1：将完整简历注入 Agent 消息（次要根因）

在 `BaseAgent._prepare_input` 或 `build_agent_messages` 中增加可选的 `resume_context` 注入：
- 若 `state.resume_text` 非空，以 system message 形式附加到 messages 中。
- 确保 Tech1/2/SysDes 能基于简历项目提问，否则面试将永远停留在通用技术栈表层。

### P2：优化短轮数下的状态机映射（体验优化）

当 `max_turns` 较小时，应优先保证核心业务面试官出场，或允许 Scribe 根据实际参与的轮次动态调整评估维度。但此优化必须在 **P0 修复**之后才有意义，否则 Scribe 仍然会因上下文缺失而幻觉。
