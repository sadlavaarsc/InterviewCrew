# InterviewCrew — 开发回顾与技术决策

## 项目背景与目标

InterviewCrew 是一个面向程序员的多 Agent 技术面试模拟器。与常见的单 Agent 聊天机器人不同，它模拟了真实技术面试中"多人围攻"的场景——5 位面试官（算法筛查、深度追问、系统设计、HR 行为面、面评汇总）各自拥有独立的记忆和评估维度，通过编排器协同推进。

项目的核心假设是：**多个专业 Agent 分工协作，效果会优于一个 Agent 换 prompt 强行扮演多个角色**。为了验证这个假设，我们不仅实现了 Multi-Agent System（MAS），还同步实现了一套 Single-Agent Baseline（SAS）作为对照组——两者使用完全相同的 API、相同的工作流、相同的模型，唯一的区别是 MAS 用 5 个独立 Agent 实例，SAS 用一个 Agent 动态拼接 prompt 来切换角色。

A/B 测试的结果验证了我们的假设：MAS 综合评分 86.2，SAS 52.5，领先 64%。最关键的差异在"角色一致性"和"记忆隔离"两个维度——SAS 在 14 轮对话中有 6 轮是 placeholder（57% 的轮次没有实质内容），且出现了严重的 topic drift（候选人换了项目，面试官没跟上）。

但 MAS 架构也引入了新的工程挑战：
- 多 Agent 之间的状态如何流转？如何避免一个 Agent 看到不该看的内容？
- 面试流程涉及多轮次、多阶段（Tech Agent 内部还有 chat→coding→reflect 的 sub-stage），状态机复杂
- 成本如何控制？5 个 Agent 同时调用 LLM，账单容易失控
- 代码考核环节如何从"Mock 猜测"进化到真实执行与评估

所以整个项目的发展脉络是：**先验证 MAS 架构的可行性，再围绕 Agent 编排、记忆管理、成本控制、代码执行四个维度做工程化落地**。

---

## 技术选型与 Trade-off

### 为什么不选 LangGraph，只用 LangChain Core

**背景**：项目启动时 LangGraph 已经很流行，它的状态机和节点流转看起来很契合 Multi-Agent 场景。

**候选方案对比**：

| 方案 | 优点 | 缺点 |
|------|------|------|
| LangGraph | 内置状态机、节点流转可视化、生态成熟 | 状态机定义在编译期，我们的面试流程需要运行时动态配置（启用/禁用某些轮次、调整轮次上限）；LangGraph 的循环逻辑在复杂 sub-stage 场景下不够灵活 |
| **LangChain Core (RunnableSequence)** | 轻量，只依赖 RunnableLambda 和消息抽象；完全自己控制状态流转逻辑；没有额外的学习成本 | 需要手写编排逻辑，没有现成的可视化 |

**最终决策**：选 LangChain Core。原因是面试流程的状态机有很强的业务特殊性——Tech Agent 内部有 chat→coding→reflect→done 的 sub-stage 流转，coding 阶段需要等待候选人主动提交代码（不是简单的轮次推进），且用户需要运行时配置哪些轮次启用、每个轮次多少 turn。LangGraph 的图结构在编译期固定，对这种动态性支持不佳。我们用 `RunnableSequence` 封装每个 Agent 的调用链路，自己手写 `Orchestrator` 做上层编排，灵活性更高。

**代价**：没有 LangGraph 内置的状态可视化，调试复杂流程时需要靠日志和 `InterviewState` 的 JSON 快照。

### MAS vs SAS：为什么要自己造一个"对手"

**背景**：做 MAS 架构时，内部最大的争议是"多个 Agent 真的比一个 Agent 强吗？"常见的反驳是"你用更好的 prompt 工程，单 Agent 也能做到差不多"。

**决策**：与其争论，不如直接实现一套 SAS 作为对照组，用完全相同的输入跑 A/B 测试。SAS 的设计刻意保留了单 Agent 的固有缺陷——它能看到全部对话历史，每次轮次切换时通过 prompt 拼接告诉它"你现在扮演 tech2"，但无法真正"遗忘"之前轮次的 persona。

**结果**：A/B 测试数据成了项目最有说服力的证据。MAS 在角色一致性上领先 64%，记忆隔离领先 113%，技术覆盖度领先 35%。而且 MAS 的成本反而更低（41%）——因为 BudgetGuardian 可以按 Agent 粒度做模型降级，SAS 只能全局降级。

### Memory 隔离方案：独立 History vs 全局 History + Prompt 过滤

**背景**：多 Agent 场景下，每个 Agent 应该看到多少上下文？最理想的是每个 Agent 只看到自己参与的对话 + 前面轮次的摘要。但如果简单地把所有历史广播给所有人，就会出现角色混淆。

**候选方案对比**：

| 方案 | 优点 | 缺点 |
|------|------|------|
| 全局历史 + 系统 prompt 过滤 | 实现简单，所有 Agent 共享一份数据 | 依赖 LLM 的"遵守指令"能力，实测中经常失效；context length 爆炸 |
| **独立 agent_history + MemoryDistillate 摘要** | 物理隔离，不可能泄露；摘要压缩后 context 更短；每个 Agent 的视角可以定制 | 需要维护多份历史；摘要质量依赖蒸馏模型 |

**最终决策**：独立 `agent_history` + `MemoryDistillate`。`InterviewState` 中为每个 Agent 维护独立的 history 列表，`build_agent_messages()` 时只注入该 Agent 的 private history。同时每轮调用 `distill_memory()` 将最近 10 轮对话压缩成结构化摘要（候选人画像、能力标签、疑点、推荐追问方向），注入给下一轮 Agent 作为上下文。

**关键设计**：`TransferPackage` 作为 Agent 之间的标准交接信封，包含 `MemoryDistillate`、`budget_consumed`、`challenge_flags` 等字段。所有 `TransferPackage` 按顺序存入 `transfer_queue`，形成可持久化的面试记录链。

---

## 关键设计与实现

### 1. Agent 编排引擎与状态机

这是整个系统的核心。`Orchestrator` 不只是一个简单的轮询器，它需要处理：
- 多 Agent 的顺序执行（tech1 → tech2 → sysdes → leader → hr → scribe）
- Tech Agent 内部的 sub-stage 流转（chat → coding → reflect → done）
- 冲突仲裁后的回退路由（tech2 重新评估）
- 配额控制（每个 Agent、每个 sub-stage 的 turn 上限）

**Turn Quota System** 是反复迭代后才稳定的。从 git history 可以看到，早期版本出现了多次 turn limit 相关的 bug（BUG-001、BUG-002）：
- sub-stage 内的 turn 限制没有被正确执行
- Tech Agent 完成 sub-stage 后，全局 max_turns 没有正确扣除
- 使用 `rounds_config` 时 MAS 提前终止

最终的设计是三层配额：`global`（全局总 turn）→ `agent`（单个 Agent 总 turn）→ `stage`（sub-stage 内 turn）。`TurnQuotaManager` 在 `step()` 的入口统一做配额检查和消费，而不是分散在各个分支逻辑中。

```python
class TurnQuotaManager:
    def check_and_consume(self, agent: str, sub_stage: str) -> QuotaCheckResult:
        # 1. 检查 global 配额
        # 2. 检查 agent 配额
        # 3. 检查 stage 配额
        # 4. 消费并返回结果
```

**sub-stage 状态机**：Tech Agent 的 coding 阶段不是自动推进的，需要等待候选人主动提交代码。这意味着状态机中有一个"等待外部事件"的节点，不能用简单的轮次计数来驱动。我们在 `InterviewState` 中为每个 Tech Agent 维护了 `sub_stage` 和 `stage_turns`，`should_advance_stage()` 判断是否需要推进，但 coding→reflect 的切换由代码提交事件触发。

### 2. Memory 隔离与蒸馏

每个 Agent 的上下文由三部分组成：
1. **System prompt**：该 Agent 的角色定义（从文件加载）
2. **Business context + Resume**：JD 解析后的业务背景和候选人简历
3. **Private history**：该 Agent 自己参与的对话记录

`build_agent_messages()` 的构建顺序是经过设计的：system prompt → business context → resume → private history → candidate response。这样确保角色定义在最前面，业务背景其次，对话历史最后，符合 LLM 的注意力衰减规律。

**Memory Distiller** 使用轻量级模型（flash）做对话摘要，而不是把完整历史传给下一个 Agent。这有两个好处：
- 显著降低 token 消耗（50% context reduction）
- 强制"信息过滤"——只有被蒸馏模型认为重要的内容才会进入下一轮

蒸馏失败时的 fallback 设计也很重要：返回一个最小有效的 `MemoryDistillate`，包含低置信度的默认评分，确保管道不中断。

**ConflictArbitrator** 检测跨 Agent 对同一维度的评分方差。比如 tech1 给 coding 打了 0.8，tech2 给了 0.4，方差超过 0.4 时触发冲突标志，下一轮强制路由到 tech2 重新评估。这比简单的取平均更符合真实面试流程——当两位面试官意见不一致时，需要有人做二次确认。

### 3. BudgetGuardian：按 Agent 粒度的模型降级

MAS 架构天然有成本优势，因为不同 Agent 对模型能力的需求不同：
- tech1/tech2（技术面试）：需要强推理能力，用 plus
- sysdes（系统设计）：需要长上下文，用 plus
- hr（行为面）：用 flash 足够
- scribe（生成报告）：长文本生成，用 flash 降本

`BudgetGuardian` 为每个 Agent 设置独立的 token 预算，超支时自动降级到 flash。这比 SAS 的全局降级更精细——SAS 只能统一用一个模型，而 MAS 可以在"该省的地方省，该花的地方花"。

实测成本：单次完整面试约 ¥4（MAS with cost controls），而 SAS 约 ¥17。

### 4. 代码考核：从 Mock 到真实执行 + AST 分析

代码考核是技术面试的核心环节。早期版本只有 Mock——检查代码里有没有 `def ` 或 `class `，然后假设通过。这显然不够。

最终的方案是三级 fallback：
1. **Docker 容器执行**：隔离性最强，cgroups 限制资源，网络禁用
2. **Subprocess 执行**：速度更快，正则黑名单过滤危险代码
3. **Mock**：兜底，语法检查 + 启发式判断

更重要的是引入了 **AST 静态分析**，作为"执行正确性"之外的第二维度评估：
- 时间/空间复杂度推断（基于循环嵌套、递归模式）
- 反模式检测（深度嵌套、超长函数、缺少异常处理）
- 圈复杂度和代码行数统计

这让代码考核从"能不能跑通"进化到"代码质量如何"，更接近真实面试官的评估维度。

**踩过的坑**：Two Sum 测试持续失败，排查后发现是输入解析的正则 `nums=([^,]+)` 遇到数组 `[2,7,11,15]` 时匹配到第一个逗号就截断。修复为懒惰匹配 `nums=(\[.*?\])`。

### 5. 工程化落地：让 Agent 系统能稳定运行

Agent 的核心逻辑完成后，为了让系统能真正承载用户流量，我们做了以下工程化改造：

| 改造项 | 动机 | 方案 |
|--------|------|------|
| **AsyncIO + SSE** | 同步阻塞调用导致并发极低，Web UI 白等 | 全局 AsyncOpenAI 单例 + 连接池复用，SSE 流式推送 Agent 输出 |
| **tiktoken 精确计数** | `len//4` 启发式在中文场景误差 57%，BudgetGuardian 降级决策失准 | cl100k_base 编码器，误差降到 <2% |
| **Redis 会话持久化** | 纯内存存储，服务重启丢所有面试状态 | SessionStore 抽象，Redis + 内存 fallback，TTL=24h |
| **Token Bucket 限流** | 无流控，突发请求可能压垮 | 全局 + 单会话两级限流 |
| **Prometheus 风格 /metrics** | 无运行时观测能力 | Histogram/Counter/Gauge 指标，按 model/agent 维度拆分 |

这些不是"后端项目"的核心，而是"Agent 工程化"的必要基础设施——没有它们，Agent 逻辑跑得再漂亮也无法对外提供服务。

---

## 已知问题与改进方向

### 1. Scribe 幻觉问题（已修复）

Scribe Agent 负责汇总所有轮次生成面评报告。早期版本出现过"编造对话内容"的问题——在候选人没有提到某段经历的情况下，Scribe 为了生成"完整"的报告而推测补充。修复方式是在 Scribe 的 prompt 中增加严格约束：所有评估必须引用对话原文，禁止推测未提及信息。同时在 `MemoryDistillate` 的蒸馏 prompt 中也加入了同样的约束。

### 2. Turn Limit 反复出 Bug（已修复）

从 git history 可以看到，turn limit 相关的 bug 反复出现：
- BUG-001：sub-stage 内的 turn 限制没有被正确执行
- BUG-002：sub-stage 完成后全局 max_turns 没有正确扣除
- MAS 使用 `rounds_config` 时提前终止

根本原因是早期的 turn 检查逻辑分散在 engine.py 的多个分支中。最终通过引入 `TurnQuotaManager` 做统一入口，根治了这个问题。

### 3. 流式输出为"伪流式"

当前实现：`orchestrator.step()` 同步调用 LLM 获取完整回复，SSE 端点将结果逐字推送给前端，形成打字机视觉效果。用户体验上是流式的，但后端的 LLM 调用仍是阻塞的。真正的 `async_llm.astream()` 已写好，但 engine.py 接入需要把整条 LCEL Chain 改成 async，改动量大，留到后续迭代。

### 4. AST 空间复杂度推断准确率有待提升

时间复杂度推断 100%（3/3），但空间复杂度 67%（2/3）。Valid Parentheses 的栈操作被误判为 O(1)，因为 AST 只看到局部变量赋值，没有理解栈深度随输入线性增长。

---

## 总结与后续方向

这个项目验证了一个核心假设：**在专业分工明确的场景中，Multi-Agent 架构的效果显著优于单 Agent prompt 工程，且成本更低**。

几个关键收获：
- **Agent 之间的协议化交接**（TransferPackage）比简单的消息广播更可靠，它强制了信息的标准化和可追溯
- **按 Agent 粒度的资源控制**（BudgetGuardian + Turn Quota）是 MAS 成本优势的关键，SAS 无法做到这么精细的降级
- **Memory 蒸馏**不仅是省钱手段，更是一种"信息过滤"机制，防止低质量上下文污染下游 Agent
- **Agent 工程化**的核心不是后端技术栈多复杂，而是让 Agent 逻辑能稳定、可观测、可控制地运行

后续迭代方向：
1. **engine.py 接入真正的 astream()**：实现 token-by-token 真流式，降低首字延迟
2. **RAG 知识库增强**：让 Agent 能参考特定技术文档或公司技术栈生成更精准的面试问题
3. **多语言沙箱**：当前仅支持 Python，扩展 Go/Java/JavaScript
4. **Agent 自我进化**：基于历史面试数据微调每个 Agent 的 prompt 和评估标准

---

## 🎤 面试可能被问到的点

- **为什么选择 LangChain Core 而不是 LangGraph？**——动态状态机 vs 编译期图结构的 trade-off
- **MAS 比 SAS 强在哪里？A/B 测试是怎么设计的？**——对照组的公平性保证（相同 API、相同模型、相同工作流）
- **MemoryDistillate 的设计思路是什么？为什么不用完整历史？**——信息过滤 + 成本 + 注意力衰减
- **TransferPackage 为什么要设计成标准交接信封？**——协议化交接在多 Agent 系统中的必要性
- **BudgetGuardian 的降级策略和 SAS 的全局降级有什么区别？**

---

## 附录：高频面试追问参考

下面两个问题在面试中几乎每次都被问到，整理成标准回答备忘。

### 1. 记忆蒸馏和消息传递是怎么做的？

> 我们设计的是一个多角色协作的面试流程，5 个 Agent 各自负责不同环节。关键问题是：如果每个 Agent 都看到全部对话历史，就会出现角色混淆——比如 HR 看到 tech2 的算法追问后，下一轮可能不自觉地继续问技术问题。
>
> 所以我们做了两层设计：
>
> **第一层是物理隔离的 private history**。每个 Agent 在 `InterviewState` 里有自己的 `agent_history`，`build_agent_messages()` 时只注入该 Agent 自己参与过的对话。这从机制上保证了它看不到其他 Agent 的完整对话。
>
> **第二层是 MemoryDistillate 跨轮摘要**。每轮结束后，用轻量级模型把最近 10 轮对话压缩成一个结构化对象，包括候选人画像、能力标签及证据、疑点列表、矛盾点、推荐追问方向。下一轮 Agent 拿到的是这个摘要，而不是原始对话。
>
> **Agent 的上下文构建顺序**也有讲究：system prompt → 业务背景 → 简历 → private history → 当前候选人回复。这样角色定义在最前面，受注意力衰减影响最小。
>
> **传递机制**我们叫 `TransferPackage`，是 Agent 之间的标准交接信封，包含摘要、已消耗预算、challenge flags 等。所有 `TransferPackage` 按顺序存在 `transfer_queue` 里，形成可追溯的面试记录链。
>
> **蒸馏失败**我们会 fallback 到一个最小有效的 `MemoryDistillate`，给一个中性的默认画像和低置信度评分，保证整个 pipeline 不会中断。

**核心要点**：不广播完整历史是为了防止角色混淆和记忆污染；MemoryDistillate 是压缩后的结构化上下文；TransferPackage 是协议化交接；有容错 fallback。

### 2. Benchmark 指标是怎么评估出来的？

> Benchmark 分两类：效果对比和工程指标。
>
> **效果对比是 MAS vs SAS 的 A/B 测试**。我们做了两个版本：
> - MAS：5 个独立 Agent 实例，各自有隔离记忆
> - SAS：1 个 Agent，每次轮次切换时通过 prompt 拼接告诉它"你现在扮演 tech2"
>
> 两者用完全相同的候选人简历、JD、模型、工作流。然后由一个独立的评估 Agent 从 6 个维度打分：角色一致性、记忆隔离、技术覆盖度、追问深度、事实准确性、综合评分。这样保证评估不是我自己拍脑袋。
>
> **工程指标**是根据实际运行需要定的：
> - **Token 计数精度**：100 条中英文混合消息，对比 chars/4 和 tiktoken，看误差率
> - **并发承载**：用 `asyncio.gather` 同时发送多个真实 API 请求，看成功率和延迟
> - **代码沙箱**：用 LeetCode 标准题验证执行正确率，用 6 组恶意代码验证安全拦截
> - **AST 复杂度推断**：用已知时间/空间复杂度的算法题做对比测试
>
> 效果数据来自独立 Agent 评估，工程数据来自真实运行和脚本测试。

**核心要点**：A/B 测试的关键是控制变量；评估者是独立 Agent 而非人工打分；工程指标都是为了解决实际问题而设计。
