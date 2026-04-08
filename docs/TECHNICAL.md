# InterviewCrew Technical Documentation

> 面向程序员的多 Agent 技术面试模拟器详细技术文档。

---

## 1. 项目定位与设计目标

### 1.1 核心场景
模拟真实"三面夹击"面试环境：
- **Tech-1 (JuniorCoder)**：基础算法与代码能力筛查。
- **Tech-2 (SeniorSkeptic)**：深度追问、找反例、边界条件施压。
- **SysDes (Architect)**：系统设计与架构权衡。
- **HR (CultureFit)**：行为面试、文化契合度、压力测试。
- **Scribe (Writer)**：汇总所有轮次输出，生成结构化面评报告。

### 1.2 设计目标
| 目标 | 实现方式 |
|------|----------|
| 角色隔离 | 每个 Agent 拥有独立的 `agent_history`，通过 `MemoryDistillate` 获取统一视角摘要 |
| 状态可观测 | `InterviewState` 是单数据源，所有中间产物（TransferPackage、competency_history、budget_consumed）均可追踪 |
| 成本控制 | `BudgetGuardian` 按轮次估算 token，超支时自动降级模型 |
| 评估一致性 | `ConflictArbitrator` 检测跨 Agent 对同一维度的评分方差，触发重新评估 |
| 协议化交接 | `TransferPackage` 封装每轮产出，形成可持久化的面试记录链 |
| 配额控制 | `TurnQuotaManager` 统一管理系统配额（global/agent/stage 三级），根治反复出现的 turn 限制 bug |

---

## 2. 架构全景

```
┌─────────────┐     HTTP/JSON      ┌─────────────────────────────────────┐
│ Web / CLI   │  ◄──────────────►  │        FastAPI Backend              │
│  客户端      │                    │  ┌───────────────────────────────┐  │
└─────────────┘                    │  │  /              ──Web UI       │  │
                                   │  │  /sessions      ──创建会话     │  │
                                   │  │  /step          ──单轮推进     │  │
                                   │  │  /health        ──健康检查     │  │
                                   │  └───────────────────────────────┘  │
                                   │                 │                    │
                                   │                 ▼                    │
                                   │      ┌──────────────────┐            │
                                   │      │ Orchestrator     │            │
                                   │      │ Engine           │            │
                                   │      └────────┬─────────┘            │
                                   │               │                      │
                                   │      ┌────────▼─────────┐            │
                                   │      │ Agent LCEL Chain │            │
                                   │      └──────────────────┘            │
                                   └─────────────────────────────────────┘
```

### 2.1 关键技术选型
- **LangChain Core**：仅使用 `RunnableSequence`、`RunnableLambda` 与消息抽象，不依赖 `langgraph`。
- **Pydantic**：所有跨模块数据结构（`MemoryDistillate`、`TransferPackage`、`BusinessContext`、`AgentOutput`）均通过 Pydantic 强校验。
- **模型路由**：`LLMClient` 采用工厂模式 `for_model(alias)`，支持 `qwen3.5-plus` / `qwen3.5-flash` / Ark fallback 三条路由。

---

## 3. 数据结构与协议

### 3.1 State Transfer Protocol (STP)
定义在 `interview_crew/protocol/schemas.py`。

#### `CompetencyTag`
```python
class CompetencyTag(BaseModel):
    dimension: Literal["coding", "system_design", "communication",
                       "pressure_resistance", "culture_fit"]
    score: float        # [0, 1]
    evidence: str
    confidence: float   # [0, 1]
```
这个是所有 Agent 共享的评估维度标签，Scribe 最终报告与 ConflictArbitrator 的方差计算都依赖它。

#### `MemoryDistillate`
```python
class MemoryDistillate(BaseModel):
    candidate_profile: Dict[str, str]
    competency_vector: List[CompetencyTag]
    doubt_list: List[str]
    contradiction_alerts: List[str]
    recommended_focus: str
```
每轮 `Orchestrator.step()` 都会先调用 `distill_memory()`，将最近 10 轮对话压缩成这个对象，再注入给当前 Agent 作为上下文。失败时会回退到一个安全的空对象，确保管道不中断。

#### `TransferPackage`
```python
class TransferPackage(BaseModel):
    session_id: str
    from_agent: str
    to_agent: str
    round_completed: int
    distillate: MemoryDistillate
    raw_digest: str
    budget_consumed: int
    challenge_flags: Optional[List[str]]
    agent_question: Optional[str]
    evaluation_score: Optional[float]
```
这是状态机中 Agent 与 Agent 之间的**标准交接信封**。所有 `TransferPackage` 按顺序追加到 `InterviewState.transfer_queue` 中，最终由 Scribe 消费生成面评。

### 3.2 状态容器
`interview_crew/state.py` 中的 `InterviewState` 是一个可变的 `@dataclass`（不再是旧版的 `TypedDict`），关键字段：

| 字段 | 说明 |
|------|------|
| `unified_history` | 全局对话记录，候选人与所有 Agent 的消息都在这里 |
| `agent_histories` | `Dict[str, List[Message]]`，每个 Agent 只看到自己参与的子集 |
| `transfer_queue` | `List[TransferPackage]`，持久化的轮次交接记录 |
| `competency_history` | 扁平化的 `CompetencyTag` 记录，用于冲突检测 |
| `conflict_flag` | 若 `ConflictArbitrator` 发现方差>0.4，则设为 True，下一轮强制路由到 `tech2` 重新评估 |
| `resume_text` / `jd_text` | 外部挂载的候选人简历与职位描述（Markdown 原文件） |
| `business_context` | 由 `JDParsingStrategy` 解析后的结构化 JD 信息 |
| `quota_consumed_agent` | 配额系统：记录每个 agent 已消费的配额 |
| `quota_consumed_stage` | 配额系统：记录每个 agent 的 sub-stage 消耗详情 |

---

## 4. 核心模块详解

### 4.1 Orchestrator Engine (`interview_crew/orchestrator/engine.py`)
`Orchestrator` 是整个系统的入口与调度器。

#### `step(candidate_response: str) -> StepResult`
这是 CLI 每轮循环唯一需要调用的方法，内部执行：
1. **初始化检查**：若 `current_agent` 为空，选择第一个启用的 agent。
2. **统一配额检查**：`_quota.check_and_consume()` 检查 global/agent/stage 三级配额（核心改进）。
3. **配额耗尽处理**：若配额耗尽，根据耗尽层级执行相应动作（FINISH/SWITCH_AGENT/ADVANCE_STAGE）。
4. **记录 turn**：更新 `turn` 计数器，追加回答到 `unified_history`。
5. **状态机推进**：`_next_agent()` 根据配额系统决定下一步（若 `conflict_flag=True`，则路由到 `tech2`）。
6. **映射 Agent**：将 agent 名映射为具体的 Agent 实例。
7. **记忆蒸馏**：调用 `distill_memory()` 生成 `MemoryDistillate`。
8. **预算检查**：`BudgetGuardian.check_and_downgrade()` 根据 token 估算返回实际使用的模型别名（可能降级为 `qwen-flash`）。
9. **Agent 调用**：通过 LCEL Chain 输出 `AgentOutput`。
10. **历史更新**：分别更新 `agent_histories[agent_name]` 与 `unified_history`。
11. **能力记录与冲突检测**：将本轮 `competency_vector` 扁平化存入 `competency_history`，并运行 `ConflictArbitrator.detect_conflict()`。
12. **构建 TransferPackage**：压入 `transfer_queue`。
13. **返回结果**：`StepResult(agent, question, finished)`。

#### 终态处理
当状态机到达 `finished` 或 `turn >= max_turns` 时，调用 `_generate_report()`：
- 将 `transfer_queue` 中的所有记录拼接成合成摘要；
- 注入 `ScribeAgent`，要求其生成 Markdown 格式的面评报告；
- 返回 `StepResult(finished=True, report=...) `。

### 4.2 Agent 基类与 LCEL 链 (`interview_crew/agents/base.py`)
所有具体 Agent 继承 `BaseAgent`，其内部封装了一个三段式 LCEL 链：

```python
self._chain = RunnableSequence(
    RunnableLambda(self._prepare_input),   # 组装 messages
    RunnableLambda(self._llm_call),        # 调用 LLM
    RunnableLambda(self._parse_output),    # 解析为 AgentOutput
)
```

#### `_prepare_input`
- 读取 `system_prompt`（来自对应 `prompts/{agent_name}.txt`）；
- 调用子类实现的 `build_context(distillate)` 将 `MemoryDistillate` 转换为 Agent 特定的文本摘要；
- 通过 `memory.agent_mailbox.build_agent_messages()` 拼接最终消息列表 `[system, business_context, private_history, candidate_response]`。

#### `_llm_call`
- 模型选择优先级：`forced_model`（预算降级） > `self.preferred_model` > `policy.get_models()[0]`。
- 直接调用 `llm.invoke(messages, model_name=..., temperature=...)`。

#### `_parse_output`
- 期望 LLM 返回合法 JSON，解析为 `AgentOutput`；
- 解析失败时回退：`question=raw_text`，`evaluation_score=0.5`，确保下游不因格式错误崩溃。

### 4.3 Memory 子系统

#### Distiller (`interview_crew/memory/distiller.py`)
`distill_memory(raw_dialogue, session_id, turn) -> MemoryDistillate`
- 仅取 `raw_dialogue` 最后 10 条，降低成本；
- 使用 `qwen-flash`（低成本模型）+ system prompt 要求输出 JSON；
- 任何异常都会返回一个带空向量的安全对象，避免阻塞主流程。

#### Agent Mailbox (`interview_crew/memory/agent_mailbox.py`)
`build_agent_messages(private_history, system_prompt, candidate_response, business_context)`
- 简单的消息拼接函数，确保 `private_history` 隔离；
- `business_context` 若存在，以 system message 形式插入，优先级次于主 system prompt。

### 4.4 治理组件

#### BudgetGuardian (`interview_crew/orchestrator/budget_guardian.py`)
- 每个 Agent 拥有独立的 `budget_{agent_name}`（配置在 `config.py`）；
- `check_and_downgrade(agent_name, estimated_tokens)`：当估算 token 超过预算时，返回 `qwen-flash`，否则返回 `qwen-plus`；
- `consume(tokens)`：累计总消耗，写入 `InterviewState.total_budget_consumed`。

**注意**：token 估算是本地启发式 `sum(len(content)) // 4`，不精确但零成本，适合用来做预算门控。

#### TurnQuotaManager (`interview_crew/orchestrator/quota.py`)
统一的三级配额管理系统，根治 turn 限制相关的反复 bug。

```python
class TurnQuotaManager:
    def check(agent, sub_stage) -> QuotaCheckResult    # 检查配额（不消费）
    def consume(agent, sub_stage) -> QuotaCheckResult  # 消费配额
    def get_remaining(agent, sub_stage) -> Dict[str, int]  # 获取剩余配额
```

**配额层级**：
| 层级 | 配置项 | 默认值 | 耗尽动作 |
|------|--------|--------|----------|
| Global | `total_max_turns` | 30 | FINISH (结束面试) |
| Agent | `max_turns` | 6 | SWITCH_AGENT |
| Sub-Stage | `stage_turn_limits` | - | ADVANCE_STAGE |

**配额检查顺序**：
1. 先检查所有层级是否还有配额
2. 从低到高消费（stage → agent → global）
3. 任一层级耗尽触发相应动作

**向后兼容**：
- 支持从旧格式 `round_turn_counts` 恢复配额
- 保留 `max_chat_turns`/`max_coding_turns`/`max_reflect_turns` 作为快捷配置

#### ConflictArbitrator (`interview_crew/orchestrator/conflict_arbitrator.py`)
`detect_conflict(evaluations) -> Optional[str]`
- 将 `competency_history` 按 `dimension` 分组；
- 若某维度存在 ≥2 个评分，且 `max - min > 0.4`，则返回冲突描述；
- Orchestrator 收到冲突后设置 `state.conflict_flag = True`，并将冲突信息追加到 `contradiction_alerts`，下一轮强制进入 `tech2` 重新深挖。

### 4.5 Tool 权限与路由 (`interview_crew/tools/registry.py`)

所有工具均使用 **LLM 实现**（位于 `tools/stubs.py`），通过 `LLMClient` 调用模型生成结果，具备 fallback 机制确保稳定性。

| Agent | 可用 Tools | 最大调用次数/轮 | 模型降级池 |
|-------|-----------|----------------|-----------|
| tech1 | `rag_query`, `code_judge` | 2 | qwen-plus |
| tech2 | `rag_query`, `deep_search`, `counter_example_gen`, `stress_trigger` | 4 | qwen-plus / qwen-flash |
| sysdes | `whiteboard_sim`, `tradeoff_analyzer`, `cross_ref_checker` | 3 | qwen-plus / qwen-flash |
| hr | `consistency_checker`, `red_flag_detector` | 2 | qwen-plus |
| scribe | (无) | 0 | qwen-flash |

**工具实现详情**：

| 工具名 | 实现方式 | 功能说明 |
|--------|---------|---------|
| `rag_query` | LLM 模拟知识库查询 | 生成技术主题的知识点、常见考点、易错点 |
| `code_judge` | LLM 代码分析 | 评估时间/空间复杂度、边界条件、潜在 bug |
| `deep_search` | LLM 模拟实时搜索 | 返回技术查询的最新信息 |
| `counter_example_gen` | LLM 反例生成 | 针对候选方案生成边界测试用例 |
| `stress_trigger` | 随机+LLM 判断 | 决定是否激活压力面试模式 |
| `whiteboard_sim` | LLM 生成图表 | 将架构描述转换为 Mermaid 代码 |
| `tradeoff_analyzer` | LLM 权衡分析 | 对比两个架构选项的优缺点 |
| `cross_ref_checker` | difflib+LLM | 检测前后陈述是否矛盾 |
| `consistency_checker` | LLM 一致性判断 | 分析多轮陈述的逻辑一致性 |
| `red_flag_detector` | 规则+LLM 检测 | 识别候选人回答中的风险信号 |

`ToolPolicy` 提供：
- `check_permission(tool_name)`：结合 `max_calls_per_round` 做粗粒度限流；
- `downgrade_model()`：返回该 Agent 允许的最便宜模型。

如需添加真实外部能力（如代码执行器、向量数据库），可在 `tool_registry.register(name, fn)` 注册新实现覆盖现有 LLM 版本。

### 4.6 LLM Client 工厂 (`interview_crew/llm/client.py`)
```python
class LLMClient:
    def for_model(self, model_name: str, temperature: float) -> ChatOpenAI
    def invoke(self, messages: List[dict], model_name=None, temperature=0.7) -> str
```

`_resolve_model_params(alias)` 的映射逻辑：
- `qwen3.5-flash` → DashScope (`settings.dashscope_model`/`api_key`/`base_url`)
- `qwen3.5-plus` → DashScope (直接透传模型名，复用同一 base_url)
- 其他不明别名 → Ark fallback

当前实例为全局单例 `llm = LLMClient()`，测试时通过 `monkeypatch.setattr(llm, "invoke", fake_fn)` 即可 Mock。

---

## 5. 工程入口与使用方式

### 5.1 环境准备
```bash
# 必须在 agentEnv conda 环境中运行
conda activate agentEnv

# 安装依赖（requirements.txt 已移除 langgraph）
pip install -r requirements.txt
```

需要配置 `.env` 文件（基于 `pydantic-settings` 自动读取）：
```bash
ARK_API_KEY=...
DASHSCOPE_API_KEY=...
```
其他字段均有默认值（`config.py` 中的 `BaseSettings`）。

### 5.2 启动 FastAPI 后端
```bash
python -m interview_crew.server
# 默认监听 0.0.0.0:8000，带 auto-reload
```

后端内存维护 `session_id -> Orchestrator` 映射（与当前无持久化设计一致）。核心路由：
- `GET /` — Web UI 入口（`index.html`）
- `GET /static/*` — Web 静态资源（CSS/JS）
- `POST /sessions` — 创建面试会话
- `POST /sessions/{session_id}/step` — 推进一轮
- `GET /sessions/{session_id}` — 查询当前会话完整状态
- `POST /sessions/{session_id}/submit-code` — 提交代码运行测试
- `GET /sessions/{session_id}/coding-task` — 获取当前代码题目
- `GET /health` — 健康检查

### 5.3 Web UI 前端运行
Web UI 是一个内嵌在后端中的单页应用，零额外构建步骤。启动后端后直接访问根路由即可：

```bash
python -m interview_crew.server
# 浏览器打开 http://localhost:8000/
```

Web UI 功能：
- **面试配置**：选择启用/禁用轮次、设置总回合数、填写岗位与简历
- **实时对话**：左侧聊天区展示各 agent 的问题与候选人回复，带 agent 标签着色
- **代码考核**：进入 `coding` sub-stage 时自动加载题目，支持在线编辑、选择语言、运行测试并查看结果
- **状态面板**：右侧实时显示当前面试官、回合数、Token 消耗统计
- **面评报告**：面试结束后展示 Scribe 生成的结构化报告

前端通过原生 `fetch` 直接调用后端的 JSON API，与 CLI 共享同一套接口。

### 5.4 CLI 前端运行
CLI 现已改造为 HTTP 客户端，通过 `httpx` 调用本地后端：

```bash
# 先确保后端已启动（5.2）
python -m interview_crew.cli --turns 5
# 挂载外部简历与 JD
python -m interview_crew.cli --turns 6 --resume ./candidate.md --jd ./jd.md
# 指定自定义后端地址
python -m interview_crew.cli --api-url http://127.0.0.1:8000 --turns 4
```

CLI 逻辑在 `interview_crew/cli.py` 中：
1. 解析参数，读取 `position` 与 `resume`（交互式输入）；
2. `POST /sessions` 创建会话，获得 `session_id`；
3. 循环 `POST /sessions/{id}/step` 直到 `finished=True`；
4. 打印最终 `report`。

### 5.5 纯 API 调用示例

#### 基础示例（向后兼容）
```bash
# 1. 创建会话（老接口，仍然有效）
curl -X POST http://127.0.0.1:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{"max_turns":4,"candidate_response":"岗位：后端。简历：3年Python。"}'
# 返回 {"session_id":"...","status":"ongoing"}

# 2. 推进一轮（接口不变）
curl -X POST http://127.0.0.1:8000/sessions/<session_id>/step \
  -H "Content-Type: application/json" \
  -d '{"candidate_response":"熟悉 Django 和 FastAPI。"}'
# 返回 {"agent":"tech1","question":"...","finished":false,"report":""}

# 3. 查询状态
curl http://127.0.0.1:8000/sessions/<session_id>
```

### 5.6 API 兼容性说明

#### 新老接口共存机制

配额系统重构后，API 保持**完全向后兼容**。新老接口的共存机制如下：

| 配置方式 | 优先级 | 说明 |
|----------|--------|------|
| `stage_turn_limits` (新) | 最高 | 如果提供，完全覆盖其他配置 |
| `max_chat_turns`/`max_coding_turns`/`max_reflect_turns` (旧) | 中等 | 自动映射到对应 sub-stage |
| `max_turns` (Agent 总限制) | 基础 | 跨所有 sub-stages 的累计限制 |

#### 老接口的行为

**场景 1：只使用老接口字段**
```json
{
    "total_max_turns": 30,
    "rounds_config": {
        "tech1": {
            "enabled": true,
            "max_turns": 6,
            "max_chat_turns": 2,
            "max_coding_turns": 5,
            "max_reflect_turns": 1
        }
    }
}
```
**行为**：系统内部自动创建对应的 `stage_turn_limits`，效果与之前完全一致。

**场景 2：混合使用新旧字段**
```json
{
    "rounds_config": {
        "tech1": {
            "enabled": true,
            "max_turns": 6,
            "max_chat_turns": 2,  // 旧字段
            "stage_turn_limits": [  // 新字段（优先）
                {"stage_name": "deep_dive", "max_turns": 3}
            ]
        }
    }
}
```
**行为**：`stage_turn_limits` 中未定义的 stage（如 chat）使用旧字段值，已定义的 stage 使用新配置。

#### 可能的非预期行为

1. **max_turns 语义变化**
   - **旧语义**：`max_turns` 表示"完整 rounds"数（chat→coding→reflect→done 算 1 round）
   - **新语义**：`max_turns` 表示该 agent 的**总 turns**（跨所有 sub-stages）
   - **影响**：如果之前依赖 `max_turns=4` 执行 4 个完整 rounds（约 12-16 turns），现在只会执行 4 turns
   - **缓解**：系统尝试向后兼容估算，但建议显式增加 `max_turns` 值或细化配置

2. **coding stage 默认限制**
   - 新增 `max_coding_turns=5` 防止无限等待
   - 如果候选人需要更多尝试次数，需显式配置更高值

3. **旧会话恢复**
   - 从 `round_turn_counts` 恢复到 `quota_consumed_agent` 是估算值
   - 极端情况下可能分配比预期更多/更少的回合

#### 最佳实践建议

1. **新开发**：使用 `stage_turn_limits` 进行细粒度控制
```json
{
    "stage_turn_limits": [
        {"stage_name": "chat", "max_turns": 2},
        {"stage_name": "coding", "max_turns": 10},
        {"stage_name": "reflect", "max_turns": 1}
    ]
}
```

2. **老系统迁移**：先增加 `max_turns` 值以适应新语义
```json
{
    "max_turns": 12,  // 原为 4，现在需要覆盖 4 rounds × 3 stages
    "max_chat_turns": 2,
    "max_coding_turns": 5,
    "max_reflect_turns": 1
}
```

3. **向后兼容测试**：迁移后运行 `test_orchestrator.py` 验证行为

### 5.7 测试运行
```bash
# 运行全部测试（pytest 19/19 通过）
conda activate agentEnv && pytest tests/ -v
```

当前测试覆盖：
- `test_budget_guardian.py`：预算超限降级、预算内使用 plus、token 累计。
- `test_conflict_arbitrator.py`：高方差触发冲突、低方差不触发、单条记录忽略。
- `test_distiller.py`：Mock LLM 验证 `MemoryDistillate` 字段解析。
- `test_orchestrator.py`：状态机流转、transfer_queue 增长、冲突标记设置、配额耗尽处理。
- `test_quota.py`：配额初始化、检查、消费、持久化、向后兼容恢复、边界条件。
- `test_tools_registry.py`：Agent 权限矩阵、最大调用次数限制、模型降级逻辑。
- `test_api.py`：FastAPI 路由测试（创建会话、单步推进、终态结束、404 处理、健康检查）。

**Mock 策略**：所有涉及 LLM 调用的测试都通过 `monkeypatch.setattr(llm, "invoke", fake_invoke)` 拦截，不发起真实网络请求。

---

## 6. 扩展指南

### 6.1 添加新 Agent
1. 在 `interview_crew/agents/` 下新建文件（如 `security.py`）；
2. 继承 `BaseAgent`，实现 `build_context()`，定义 `name`、`prompt_path`、`preferred_model`；
3. 在 `interview_crew/prompts/security.txt` 中写入 prompt（要求输出与 `AgentOutput` 同构的 JSON）；
4. 在 `interview_crew/agents/__init__.py` 中导出，并在 `orchestrator/engine.py` 的 `self.agents` 与 `_state_order` / `_state_to_agent` 中注册。

### 6.2 添加新 Tool
1. 在 `interview_crew/tools/stubs.py` 中实现工具函数（推荐使用 LLM + fallback 模式）；
2. 在 `interview_crew/tools/registry.py` 的 `_TOOL_POLICIES` 中为相关 Agent 分配权限与调用次数；
3. 在 `interview_crew/tools/__init__.py` 中执行 `tool_registry.register("tool_name", fn)`；
4. 在 Agent LCEL 链中通过 `RunnableLambda` 或 Tool Binding 调用（当前基类尚未接入 tool calling，需自行扩展 `_llm_call` 逻辑）。

**工具实现模板**：
```python
def my_tool(input_data: str) -> str:
    """工具功能说明。"""
    messages = [
        {"role": "system", "content": "你是一个..."},
        {"role": "user", "content": f"输入：{input_data}"}
    ]
    try:
        result = llm.invoke(messages, model_name="qwen3.5-flash")
        return result
    except Exception:
        return "fallback 结果"  # 确保工具不崩溃
```

### 6.3 替换 JD 解析器
`JDParsingStrategy` 是一个抽象基类：
```python
class JDParsingStrategy(ABC):
    @abstractmethod
    def parse(self, jd_markdown: str) -> BusinessContext: ...
```

默认实现 `LLMJDParser` 使用 `qwen-flash` 做 LLM-based 提取。若你想用规则引擎或更复杂的 NLP pipeline：
1. 实现新的 `JDParsingStrategy` 子类；
2. 在初始化 `Orchestrator` 时注入：`Orchestrator(state, jd_parser=MyParser())`。

---

## 7. Single Agent Baseline

为支持 MAS vs SAS 的量化对比研究，项目内置了 **Single Agent Baseline**。

### 7.1 架构对比

| 维度 | Multi-Agent System | Single-Agent Baseline |
|------|-------------------|----------------------|
| **架构** | 5 位专业 Agent + Orchestrator | 1 位全能 Agent |
| **记忆** | 每位 Agent 独立历史 | 统一历史记录 |
| **模型策略** | 每轮独立预算控制 + 自动降级 | 主面试用 Plus，报告用 Flash |
| **代码面试** | 完整支持（coding → reflect） | 不支持（简化设计） |
| **阶段切换** | `_next_state()` 代码控制 | **相同的硬编码工作流** |
| **配置** | 支持按 Agent 启用/禁用 | 仅支持总轮数配置 |

### 7.2 SAS 的"角色切换"实现

SAS 最大的挑战是**如何用单个 Agent 模拟多个专家**。实现方式：

#### 阶段定义（与 MAS 完全一致）

```python
STAGES = ["tech1", "tech2", "sysdes", "leader", "hr"]

STAGE_DESCRIPTIONS = {
    "tech1": "技术一面 - 基础算法与代码能力筛查",
    "tech2": "技术二面 - 深度追问、找反例、边界条件施压",
    "sysdes": "系统设计 - 系统设计与架构权衡",
    "leader": "Leader面 - 项目深挖与技术领导力",
    "hr": "HR面 - 行为面试与文化契合度"
}
```

#### 动态 Prompt 拼接（每次调用都重新构建）

```python
def _build_messages_with_stage(self, current_stage: str):
    # 1. 基础 Prompt（来自 single_agent.txt）
    base_prompt = self.system_prompt

    # 2. 动态注入当前阶段信息
    stage_desc = self.STAGE_DESCRIPTIONS[current_stage]
    stage_prompt = f"""{base_prompt}

【当前阶段】你现在正在进行：{stage_desc}

重要提醒：
1. 你是一位面试官，现在正在扮演"{current_stage}"的角色
2. 请确保你的问题符合当前阶段的定位
3. 你可以看到之前的全部对话历史，但要注意维持当前阶段的角色一致性
4. 在阶段切换时，要主动调整提问风格和关注点
"""
    messages = [{"role": "system", "content": stage_prompt}]

    # 3. 添加全部对话历史（与 MAS 的隔离形成对比）
    messages.extend(self.state.unified_history)

    return messages
```

#### 阶段切换逻辑（代码控制，与 MAS 相同）

```python
def step(self, candidate_response: str):
    # 1. 确定当前阶段
    current_stage = self._get_current_stage()  # 如 "tech1"
    self.stage_turn_counts[current_stage] += 1

    # 2. 检查是否需要切换阶段
    stage_config = self._get_stage_config(current_stage)
    if self.stage_turn_counts[current_stage] >= stage_config["max_turns"]:
        self.current_stage_index += 1  # 切换到下一阶段
        current_stage = self._get_current_stage()

    # 3. 构建阶段专属 Prompt 并调用 LLM
    messages = self._build_messages_with_stage(current_stage)
    response = llm.invoke(messages, model_name="qwen3.5-plus")

    return StepResult(agent=current_stage, question=response, ...)
```

### 7.3 SAS 的固有挑战

SAS 的设计**故意**保留了单 Agent 的局限，以便公平对比：

| 挑战 | 原因 | 预期表现 |
|------|------|---------|
| **角色串戏** | 同一模型实例，只是改了 Prompt 前缀 | 可能在 HR 阶段还保持 tech2 的追问风格 |
| **记忆污染** | 看到全部 15+ 轮历史 | Tech-2 的追问可能影响 HR 对候选人的印象 |
| **上下文过长** | 无记忆蒸馏，全量传递 | Token 消耗可能高于 MAS |
| **无冲突仲裁** | 单 Agent 自说自话 | 可能出现前后评估矛盾 |

### 7.4 Token 统计设计

Baseline 和 MAS 使用相同的 `StepResult` 结构，支持按模型级别细分的 Token 统计：

```python
@dataclass
class StepResult:
    agent: str
    question: str
    finished: bool
    report: str = ""
    # Token 统计（总计）
    token_consumed_this_turn: int = 0
    total_token_consumed: int = 0
    # 按模型级别细分
    plus_token_consumed_this_turn: int = 0      # qwen-plus（完整模型）
    flash_token_consumed_this_turn: int = 0     # qwen-flash（降级模型）
    total_plus_token_consumed: int = 0
    total_flash_token_consumed: int = 0
```

### 7.4 Baseline 的模型策略

Single Agent Baseline 采用成本优化的模型选择策略：

1. **主面试对话**：使用 `qwen3.5-plus`（完整模型，确保面试质量）
2. **最终报告生成**：使用 `qwen3.5-flash`（降级模型，节省成本）
3. **错误降级**：Plus 调用失败时自动降级到 Flash

这种策略在保持面试质量的同时，将报告生成等低频任务使用低成本模型，实现成本效益平衡。

---

## 8. 已知局限与未来方向

1. **Token 估算不精确**：当前使用字符数/4，未考虑中文与特殊 token，后续可接入 tiktoken。
2. **工具依赖 LLM 而非真实外部能力**：当前工具通过 LLM 模拟实现（如代码分析、搜索、RAG），尚未对接真实外部系统（代码执行器、搜索引擎、向量数据库）。如需生产级精度，可将 `tool_registry.register()` 替换为真实实现。
3. **Agent 链无内置 Retry**：LLM 输出 JSON 解析失败时仅做 soft fallback，未做结构性 retry。
4. **Memory 仅内存持久化**：`InterviewState` 当前在内存中，重启即丢失。如需会话恢复，需将 `transfer_queue` 与 `agent_histories` 序列化到磁盘/数据库。
5. **状态机为线性管道**：当前状态转移是固定的顺序队列。后续若需动态调度（如根据回答质量跳回某 Agent），需扩展 `_next_agent()` 为条件图或评分门控。
6. **配额预估恢复**：从旧会话恢复时，`round_turn_counts` 到 `quota_consumed_agent` 的转换采用直接映射，可能与实际消耗有偏差。

---

## 9. 目录结构速查

```
interview_crew/
├── __init__.py
├── api.py                  # FastAPI 后端路由与内存会话管理
├── server.py               # Uvicorn 启动入口
├── cli.py                  # CLI 入口（HTTP 客户端）
├── static/                 # Web UI (index.html)
├── config.py               # Pydantic Settings (.env 读取)
├── state.py                # InterviewState dataclass
├── baseline/               # 单 Agent Baseline（对比测试用）
│   ├── __init__.py
│   ├── single_agent_orchestrator.py
│   ├── single_agent.py
│   └── prompts/
│       └── single_agent.txt
├── protocol/
│   └── schemas.py          # STP: TransferPackage / MemoryDistillate / ...
├── llm/
│   └── client.py           # LLMClient 工厂 + token 估算
├── memory/
│   ├── agent_mailbox.py    # 隔离消息拼接
│   └── distiller.py        # 记忆蒸馏 (qwen-flash)
├── agents/
│   ├── base.py             # BaseAgent + LCEL Chain
│   ├── tech1.py
│   ├── tech2.py
│   ├── sysdes.py
│   ├── hr.py
│   └── scribe.py
├── orchestrator/
│   ├── engine.py           # Orchestrator + State Machine
│   ├── quota.py            # TurnQuotaManager 三级配额系统
│   ├── budget_guardian.py
│   ├── conflict_arbitrator.py
│   └── jd_parser.py        # JDParsingStrategy
├── tools/
│   ├── registry.py         # ToolPolicy / ToolRegistry
│   └── stubs.py            # 10 个 LLM 实现工具（code_judge、rag_query等）
└── prompts/
    ├── tech1.txt
    ├── tech2.txt
    ├── sysdes.txt
    ├── hr.txt
    └── scribe.txt

docs/
└── TECHNICAL.md            # 本技术文档

tests/
├── test_api.py
├── test_budget_guardian.py
├── test_conflict_arbitrator.py
├── test_distiller.py
├── test_orchestrator.py
├── test_quota.py           # TurnQuotaManager 单元测试
└── test_tools_registry.py
```

---

## 10. 配额系统配置指南

### 10.1 基础配置

使用 `InterviewConfig` 可以精确控制面试流程的配额分配：

```python
from interview_crew.protocol.schemas import InterviewConfig, InterviewRoundConfig

# 基础配置
config = InterviewConfig(
    total_max_turns=30,  # 全局总轮数限制
    rounds={
        "tech1": InterviewRoundConfig(max_turns=6),
        "tech2": InterviewRoundConfig(max_turns=6),
        "sysdes": InterviewRoundConfig(max_turns=4),
        "leader": InterviewRoundConfig(max_turns=3),
        "hr": InterviewRoundConfig(max_turns=3),
    }
)
```

### 10.2 详细 Sub-stage 配置

使用 `stage_turn_limits` 可以灵活定义任意数量的 sub-stages：

```python
from interview_crew.protocol.schemas import StageTurnLimit

config = InterviewConfig(
    rounds={
        "tech1": InterviewRoundConfig(
            max_turns=12,  # tech1 总轮数（跨所有 sub-stages）
            stage_turn_limits=[
                StageTurnLimit(stage_name="chat", max_turns=2,
                              description="技术交流阶段"),
                StageTurnLimit(stage_name="deep_dive", max_turns=3,
                              description="深入追问阶段"),
                StageTurnLimit(stage_name="coding", max_turns=5,
                              description="编程考核阶段"),
                StageTurnLimit(stage_name="reflect", max_turns=1,
                              description="反思总结阶段"),
            ]
        )
    }
)
```

### 10.3 向后兼容配置

保留旧版配置方式，自动转换为新格式：

```python
# 旧版配置仍然有效
config = InterviewConfig(
    rounds={
        "tech1": InterviewRoundConfig(
            max_turns=6,
            max_chat_turns=2,      # 自动映射到 chat stage
            max_coding_turns=5,    # 自动映射到 coding stage
            max_reflect_turns=1,   # 自动映射到 reflect stage
        )
    }
)
```

### 10.4 配额层级说明

| 层级 | 作用域 | 配置参数 | 说明 |
|------|--------|----------|------|
| Global | 整个面试 | `total_max_turns` | 所有 agent 的回合总和上限 |
| Agent | 单个 agent | `max_turns` | 该 agent 跨所有 sub-stages 的总回合数 |
| Stage | sub-stage | `stage_turn_limits` | 特定 sub-stage 的回合限制 |

**消费顺序**：stage → agent → global（细粒度优先）

**耗尽动作**：
- Global 耗尽 → 面试结束（FINISH）
- Agent 耗尽 → 切换到下一个 agent（SWITCH_AGENT）
- Stage 耗尽 → 推进到下一个 sub-stage（ADVANCE_STAGE）
