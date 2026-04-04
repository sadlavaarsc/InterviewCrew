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

---

## 2. 架构全景

```
┌─────────────┐     HTTP/JSON      ┌─────────────────────────────────────┐
│  CLI/前端   │  ◄──────────────►  │        FastAPI Backend              │
│  (cli.py)   │                    │  ┌───────────────────────────────┐  │
└─────────────┘                    │  │  /sessions      ──创建会话     │  │
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

---

## 4. 核心模块详解

### 4.1 Orchestrator Engine (`interview_crew/orchestrator/engine.py`)
`Orchestrator` 是整个系统的入口与调度器。

#### `step(candidate_response: str) -> StepResult`
这是 CLI 每轮循环唯一需要调用的方法，内部执行：
1. **接收回答**：追加到 `unified_history`。
2. **状态机推进**：`_next_state()` 按 `[screening, tech1, tech2, system, hr, finished]` 顺序推进。若 `conflict_flag=True`，则插入仲裁分支，路由到 `tech2`。
3. **映射 Agent**：`_state_to_agent` 字典将状态名映射为具体的 Agent 实例（如 `tech2` → `SysDesAgent`）。
4. **记忆蒸馏**：调用 `distill_memory()` 生成 `MemoryDistillate`。
5. **预算检查**：`BudgetGuardian.check_and_downgrade()` 根据 token 估算返回实际使用的模型别名（可能降级为 `qwen-flash`）。
6. **Agent 调用**：通过 LCEL Chain 输出 `AgentOutput`。
7. **历史更新**：分别更新 `agent_histories[agent_name]` 与 `unified_history`。
8. **能力记录与冲突检测**：将本轮 `competency_vector` 扁平化存入 `competency_history`，并运行 `ConflictArbitrator.detect_conflict()`。
9. **构建 TransferPackage**：压入 `transfer_queue`。
10. **返回结果**：`StepResult(agent, question, finished)`。

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
- `POST /sessions` — 创建面试会话
- `POST /sessions/{session_id}/step` — 推进一轮
- `GET /sessions/{session_id}` — 查询当前会话完整状态
- `GET /health` — 健康检查

### 5.3 CLI 前端运行
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

### 5.4 纯 API 调用示例
```bash
# 1. 创建会话
curl -X POST http://127.0.0.1:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{"max_turns":4,"candidate_response":"岗位：后端。简历：3年Python。"}'
# 返回 {"session_id":"...","status":"ongoing"}

# 2. 推进一轮
curl -X POST http://127.0.0.1:8000/sessions/<session_id>/step \
  -H "Content-Type: application/json" \
  -d '{"candidate_response":"熟悉 Django 和 FastAPI。"}'
# 返回 {"agent":"tech1","question":"...","finished":false,"report":""}

# 3. 查询状态
curl http://127.0.0.1:8000/sessions/<session_id>
```

### 5.5 测试运行
```bash
# 运行全部测试（pytest 19/19 通过）
conda activate agentEnv && pytest tests/ -v
```

当前测试覆盖：
- `test_budget_guardian.py`：预算超限降级、预算内使用 plus、token 累计。
- `test_conflict_arbitrator.py`：高方差触发冲突、低方差不触发、单条记录忽略。
- `test_distiller.py`：Mock LLM 验证 `MemoryDistillate` 字段解析。
- `test_orchestrator.py`：状态机流转、transfer_queue 增长、冲突标记设置。
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

## 7. 已知局限与未来方向

1. **Token 估算不精确**：当前使用字符数/4，未考虑中文与特殊 token，后续可接入 tiktoken。
2. **工具依赖 LLM 而非真实外部能力**：当前工具通过 LLM 模拟实现（如代码分析、搜索、RAG），尚未对接真实外部系统（代码执行器、搜索引擎、向量数据库）。如需生产级精度，可将 `tool_registry.register()` 替换为真实实现。
3. **Agent 链无内置 Retry**：LLM 输出 JSON 解析失败时仅做 soft fallback，未做结构性 retry。
4. **Memory 仅内存持久化**：`InterviewState` 当前在内存中，重启即丢失。如需会话恢复，需将 `transfer_queue` 与 `agent_histories` 序列化到磁盘/数据库。
5. **状态机为线性管道**：当前状态转移是固定的顺序队列。后续若需动态调度（如根据回答质量跳回某 Agent），需扩展 `_next_state()` 为条件图或评分门控。

---

## 8. 目录结构速查

```
interview_crew/
├── __init__.py
├── api.py                  # FastAPI 后端路由与内存会话管理
├── server.py               # Uvicorn 启动入口
├── cli.py                  # CLI 入口（HTTP 客户端）
├── config.py               # Pydantic Settings (.env 读取)
├── state.py                # InterviewState dataclass
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
└── test_tools_registry.py
```
