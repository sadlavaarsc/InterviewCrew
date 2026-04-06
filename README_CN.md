<h1 align="center">InterviewCrew</h1>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-blue.svg" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/LangChain-Core-green.svg" alt="LangChain">
  <img src="https://img.shields.io/badge/FastAPI-✓-009688.svg" alt="FastAPI">
  <img src="https://img.shields.io/badge/Multi--Agent-5_roles-purple.svg" alt="5 Agents">
  <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="MIT License">
</p>

<p align="center">
  <a href="README.md">English</a> •
  <b>中文</b>
</p>

<p align="center">
  <b>多 Agent 技术面试模拟器</b><br>
  <i>别再和可预测的机器人练习了，来感受真正的"三面夹击"。</i>
</p>

<p align="center">
  <a href="#-亮点">亮点</a> •
  <a href="#-演示">演示</a> •
  <a href="#-快速开始">快速开始</a> •
  <a href="#-架构">架构</a> •
  <a href="#-配置">配置</a> •
  <a href="docs/TECHNICAL.md">技术文档</a>
</p>

---

## 🔥 亮点

- **🎭 5 位专业面试官**：Tech-1（算法）、Tech-2（深度追问）、SysDes（架构设计）、HR（行为面试）、Scribe（面评生成）——每位都有独立记忆和专属人设
- **🧠 上下文隔离**：每位面试官只能看到自己的对话历史，彻底解决单 Agent "角色串戏" 的痛点
- **📊 结构化评估**：基于能力维度的评分体系，配备冲突仲裁机制——当两位面试官对同一维度评分差异过大时，自动触发 Tech-2 重新评估
- **💰 生产级成本控制**：**单次面试 ¥4-20**（对比单 Agent ¥17-34）—— 70% 调用使用更便宜的 Flash 模型，通过 BudgetGuardian + Memory Distiller 双重降本
- **🔬 A/B 测试验证**：MAS 综合评分 **86.2/100** 对比 SAS **52.5/100**，领先 **64%**（角色一致性、记忆隔离、技术覆盖全面领先）
- **🔌 灵活配置**：可自由启用/禁用任意面试轮次，自定义每轮最大回合数
- **⚡ 双模型容错**：Ark + DashScope 自动故障转移，确保服务稳定性
- **🧪 单 Agent Baseline**：内置量化对比基线 —— 相同 API、公平对比、数据说话

---

## 🧪 单 Agent Baseline

InterviewCrew 提供**单 Agent 基线**用于与多 Agent 系统进行量化对比。两种模式暴露完全相同的 API，并遵循相同的面试流程，便于进行公平的 A/B 测试。

### 快速对比

| 特性 | 多 Agent (MAS) | 单 Agent (SAS Baseline) |
|------|---------------|------------------------|
| **架构** | 5 位专业面试官 + 编排器 | 1 位全能面试官 |
| **面试流程** | `tech1 → tech2 → sysdes → leader → hr` | 相同的硬编码工作流 |
| **记忆** | 每位面试官独立 | **统一历史（所有阶段可见）** |
| **角色切换** | 更换 Agent 实例 | **动态 Prompt 拼接** |
| **模型策略** | 每轮独立预算与降级 | 主面试用 Plus，报告用 Flash |
| **核心挑战** | 协调开销 | **角色串戏与记忆污染** |

### SAS 如何"切换角色"

与 MAS 加载不同 Agent 实例不同，SAS 通过每次调用时动态构建 System Prompt 来"换角色"：

```python
# 每次调用前，SAS 构建阶段专属提示词
stage_prompt = f"""{base_prompt}

【当前阶段】你现在正在进行：{stage_desc}

重要提醒：
1. 你是一位面试官，现在正在扮演"{current_stage}"的角色
2. 你可以看到之前的全部对话历史，但要注意维持当前阶段的角色一致性
3. 阶段切换时主动调整提问风格和关注点
"""
```

**这故意给 SAS 制造了挑战**：
- **上下文长度**：必须处理 15+ 轮完整历史
- **角色串戏**：很难"忘记"前一阶段的人设
- **记忆污染**：Tech-2 的问题可能影响 HR 的评估

### 使用方式

```bash
# 多 Agent 模式（默认）- 真正的专家，记忆隔离
curl -X POST http://localhost:8000/sessions \
  -d '{"mode": "multi_agent", "total_max_turns": 15}'

# 单 Agent 基线 - 一个 Agent 扮演 5 个角色，全量历史可见
curl -X POST http://localhost:8000/sessions \
  -d '{"mode": "single_agent", "total_max_turns": 15}'
```

两种模式返回相同的响应格式，`agent` 字段都是 `tech1` / `tech2` / ...。

---

## 📊 基线评估：多 Agent vs 单 Agent

我们在相同候选人、相同简历、相同 JD 的条件下进行了严格的 A/B 测试对比：

### 量化结果

| 评估维度 | MAS (多 Agent) | SAS (单 Agent) | 领先幅度 |
|---------|---------------|---------------|---------|
| **角色一致性** | 90/100 | 55/100 | **+64%** |
| **记忆隔离效果** | 85/100 | 40/100 | **+113%** |
| **技术覆盖度** | 88/100 | 65/100 | **+35%** |
| **追问深度** | 82/100 | 50/100 | **+64%** |
| **事实准确性** | 85/100 | 75/100 | **+13%** |
| **综合评分** | **86.2** | **52.5** | **+64%** |

*评估方法：独立 Subagent 基于完整对话记录进行 6 维度量化评估*

### 核心发现

**1. 记忆隔离有效**
- MAS 各阶段 Agent 仅接收前一阶段 Summary，防止对话污染
- SAS 出现严重话题漂移（候选人从 RepoMind 跳转到 CueZero，面试官未纠正）
- 追问连续性：MAS 平均 1.9 轮/主题，SAS 因占位符无法有效评估

**2. 角色边界清晰**
- tech1/tech2/sysdes/leader/hr 各 Agent 严格遵循阶段定位
- SAS 阶段切换混乱，14 轮中 6 轮为占位符（内容完整度仅 57%）

**3. 技术覆盖全面**
- MAS 覆盖 JD 要求的 6 大知识域（LLM 应用、Agent 框架、RAG、强化学习、系统设计、工程化）
- SAS 未考察 RAG 多级检索、Agent 框架、MCP 协议等核心要求

---

## 💰 成本分析

> 模型定价：qwen-plus 输入¥0.8/Mtokens 输出¥4.8/Mtokens | qwen-flash 输入¥0.15/Mtokens 输出¥1.5/Mtokens

### 降本架构设计

| 降本措施 | 实现方式 | 效果 |
|---------|---------|------|
| **BudgetGuardian** | Token 超预算自动降级到 Flash | 70% 调用使用 Flash |
| **Memory Distiller** | Flash 模型压缩对话历史 | 上下文减少 50% |
| **Scribe 报告** | 使用 Flash 模型生成长报告 | 报告成本降低 |
| **Agent 预算限制** | tech1:2000/sysdes:4000 等 | 强制成本控制 |

### 成本对比

| 场景 | MAS | SAS | 说明 |
|------|-----|-----|------|
| **无缓存理论估算** | ~¥20 | ~¥34 | 用于公平对比架构效率 |
| **实际测试消耗** | **~¥4/次** | ~¥17/次 | 考虑缓存命中后的真实成本 |

**结论：MAS 架构在无缓存条件下仍比 SAS 便宜 41%，且随着缓存建立，后续单次成本可降至约 ¥4，远低于 SAS 的首次运行成本。**

---

## 🎬 演示

### 真实面试流程（14 轮，5 个阶段）

以下是一次完整测试运行的多 Agent 协作演示：

<details>
<summary><b>🔹 阶段 1：Tech-1 技术一面（算法筛查）</b></summary>

**面试官（Tech-1）**：
*"在你的 RepoMind 项目中，你提到了基于 AST 的多级分块策略。你们具体是用 Python 内置的 `ast` 模块还是第三方库（如 `tree-sitter`）来处理跨文件调用关系的？"*

**候选人**：
*"我们采用了混合方案：Python 代码用标准 `ast` 模块，Java/C++/Go 等 12 种语言用 tree-sitter，封装了统一的 AST 遍历接口来抹平差异..."*

**面试官（Tech-1）**：
*"你刚才提到了多线程并发解析，是如何避免符号表的并发写入冲突的？"*

**候选人**：
*"我们采用'缓存优先+乐观锁'策略：每个线程解析前先查全局缓存，符号表写入使用 16 个分段锁，按文件路径哈希分散锁竞争..."*

**→ 随后进入 Coding 环节：在不修改原数组的前提下，用 O(n) 时间、O(1) 空间找出重复元素**

</details>

<details>
<summary><b>🔹 阶段 2：Tech-2 技术二面（深度追问）</b></summary>

**面试官（Tech-2）**：
*"如果文件 A 修改了一个被文件 B 引用的函数签名，但文件 B 本身没有代码变动，你的全局符号表如何感知到 B 的索引已失效？这种传递性依赖的失效追踪会不会在极端情况下退化成全量重建？"*

**候选人**：
*"我们通过反向依赖索引解决：每个符号维护一个'被引用文件列表'。当 A 修改签名时，将列表中的文件标记为待更新，只重新解析受影响文件..."*

**面试官（Tech-2）**：
*"那如果是 A→B→C 的链式调用，C 修改了函数签名导致 B 的返回结构变化，但 B 的接口签名没变，这种情况你们的反向索引就检测不到了吧？"*

**候选人**：
*"确实检测不到。我们通过三种方式补偿：(1) 签名包含返回值类型结构，(2) 静态类型分析，(3) 单元测试门禁触发重建..."*

</details>

<details>
<summary><b>🔹 阶段 3：系统设计面（架构设计）</b></summary>

**面试官（架构师）**：
*"'层级剪枝控制在 1 层'在性能上很有吸引力，但从架构正确性考虑：如果存在 A→B→C 的调用链，C 的变更导致 B 的对外签名也发生变化，理论上 A 也需要更新。只标记直接引用，是否会漏掉这种传递性签名变更？在'性能优化'与'索引完备性'的 Trade-off 中，你们的降级策略是什么？"*

**候选人**：
*"我们通过三重补偿机制平衡：
1. **兜底全量校验**：每天凌晨低峰期运行一次全量依赖校验，修复白天可能遗漏的传递性变更，确保索引最终一致性；
2. **变更影响分析预警**：核心路径的符号修改会触发全量依赖分析，标记所有潜在受影响文件；
3. **用户主动触发**：提供强制全量重建接口。

1 层剪枝覆盖了 99% 的场景，剩余 1% 通过上述机制兜底。"*

</details>

<details>
<summary><b>🔹 阶段 4：HR 行为面</b></summary>

**面试官（HR）**：
*"你提到的'1 层剪枝覆盖 99% 场景'，这个数据是基于实际测试集统计还是理论估算？如果兜底机制频繁触发拖慢整体节奏，你会如何权衡'重构优化'与'业务交付'的压力？请结合一个你曾因现实约束而放弃'完美设计'的具体例子谈谈。"*

**候选人**：
*"99% 的数据来自上线前 3 个真实项目的测试集统计。如果兜底频繁触发，我会做灰度上线：先针对新用户启用 2 层剪枝版本，观察一周触发频率。

**具体案例**：RepoMind V1 时我设计了完美的分布式缓存架构，但业务要求两周内上线演示。我权衡后放弃分布式方案，先用本地缓存快速上线，第二个迭代再重构为分布式。既满足了业务交付节奏，也保证了最终架构的合理性。"*

**面试官（HR）**：
*"如果加入我们团队，发现现有技术栈比你之前用的落后很多，你会怎么推进技术升级？会不会觉得落差很大？"*

**候选人**：
*"技术栈只是工具，解决问题才是核心。我会采取小步迭代：先从非核心模块切入做试点，拿到实际收益数据后再逐步推广。业务稳定是第一位的，技术升级是为了更好支撑业务，不是为了技术而技术。"*

</details>

<details>
<summary><b>🔹 阶段 5：Scribe 最终面评</b></summary>

```markdown
# Final Evaluation Report (面评报告)

## 技术评估
候选人在代码感知 RAG 系统（RepoMind）中展现了深厚的技术积累，特别是在 AST 解析、
增量索引优化及依赖图构建方面具备全链路经验...

## 推荐
Strong Hire

## 证据链
- **系统设计能力**：提出混合式 AST 解析架构、反向依赖索引及三重补偿机制
- **工程权衡思维**：RepoMind V1 案例中，为满足两周上线 deadline，权衡后选择本地缓存方案
- **数据驱动决策**：剪枝策略基于真实测试集统计，而非纯理论估算
```

</details>

> 📄 **完整测试日志**：[data/records/FULL_TEST_DIALOG_20260404_FULL_FLOW.md](data/records/FULL_TEST_DIALOG_20260404_FULL_FLOW.md)

---

## 🚀 快速开始

### 环境准备

```bash
# 必须在 agentEnv conda 环境中运行
conda activate agentEnv
pip install -r requirements.txt
```

配置 `.env`：
```bash
ARK_API_KEY=your_ark_key
DASHSCOPE_API_KEY=your_dashscope_key
```

### 运行 CLI 演示

```bash
# 启动后端
python -m interview_crew.server

# 另开终端，运行 CLI
python -m interview_crew.cli --turns 6 --resume ./candidate.md --jd ./jd.md
```

### API 调用示例

```bash
# 创建会话（自定义配置）
curl -X POST http://localhost:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "total_max_turns": 15,
    "rounds_config": {
        "tech1": {"enabled": true, "max_turns": 4},
        "tech2": {"enabled": true, "max_turns": 4},
        "sysdes": {"enabled": true, "max_turns": 3},
        "leader": {"enabled": false},
        "hr": {"enabled": false}
    }
  }'

# 推进面试
curl -X POST http://localhost:8000/sessions/{session_id}/step \
  -H "Content-Type: application/json" \
  -d '{"candidate_response": "你的回答"}'
```

### API 参考

**创建会话** — `POST /sessions`
```json
// 请求
{
  "mode": "multi_agent",           // "multi_agent" (默认) 或 "single_agent"
  "total_max_turns": 15,
  "candidate_response": "初始回答"
}

// 响应
{
  "session_id": "uuid",
  "status": "ongoing",
  "mode": "multi_agent"
}
```

**推进面试** — `POST /sessions/{id}/step`
```json
// 请求
{
  "candidate_response": "你的回答"
}

// 响应
{
  "agent": "tech1",
  "question": "下一个问题...",
  "finished": false,
  "report": "",
  // Token 统计
  "token_consumed_this_turn": 1250,
  "total_token_consumed": 8750,
  // 按模型级别细分
  "plus_token_consumed_this_turn": 1000,
  "flash_token_consumed_this_turn": 250,
  "total_plus_token_consumed": 7000,
  "total_flash_token_consumed": 1750
}
```

**获取会话状态** — `GET /sessions/{id}`
```json
{
  "session_id": "uuid",
  "status": "ongoing",
  "current_agent": "tech1",
  "turn": 5,
  // 模式和统计
  "mode": "single_agent",
  "llm_call_count": 10,
  "token_consumed": 8750,
  // 详细细分
  "plus_call_count": 8,
  "flash_call_count": 2,
  "total_plus_token_consumed": 7000,
  "total_flash_token_consumed": 1750
}
```

---

## 🏗️ 架构

```
┌─────────────┐     HTTP/JSON      ┌─────────────────────────────────────┐
│   CLI/API   │  ◄──────────────►  │        FastAPI 后端                 │
│   客户端     │                    │  ┌───────────────────────────────┐  │
└─────────────┘                    │  │  /sessions      ──创建会话     │  │
                                   │  │  /step          ──推进面试     │  │
                                   │  │  /health        ──健康检查     │  │
                                   │  └───────────────────────────────┘  │
                                   │                 │                    │
                                   │                 ▼                    │
                                   │      ┌──────────────────┐            │
                                   │      │   编排器引擎      │            │
                                   │      │  Orchestrator    │            │
                                   │      └────────┬─────────┘            │
                                   │               │                      │
                                   │      ┌────────▼─────────┐            │
                                   │      │  Agent LCEL 链   │            │
                                   │      └──────────────────┘            │
                                   └─────────────────────────────────────┘
```

**核心组件**：
- **编排器（Orchestrator）**：状态机管理面试流程
- **5 位专业面试官**：每位都有独立记忆和专属工具
- **预算守护者（Budget Guardian）**：每轮 Token 预算与自动降级
- **冲突仲裁者（Conflict Arbitrator）**：检测评分差异，触发重新评估
- **记忆蒸馏器（Memory Distiller）**：压缩对话历史，提供上下文

---

## ⚙️ 配置

### 面试轮次配置

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `total_max_turns` | int | 30 | 全局最大轮次（所有面试官累计） |
| `rounds.{agent}.enabled` | bool | true | 是否启用该面试官 |
| `rounds.{agent}.max_turns` | int | 视角色而定 | 该面试官最大轮次 |
| `rounds.{agent}.max_chat_turns` | int | 2 | 对话子阶段最大轮次 |
| `rounds.{agent}.max_reflect_turns` | int | 1 | 反思子阶段最大轮次 |

### 预设配置方案

**完整面试（默认）**
```json
{
  "total_max_turns": 30,
  "rounds": {
    "tech1": {"enabled": true, "max_turns": 4},
    "tech2": {"enabled": true, "max_turns": 4},
    "sysdes": {"enabled": true, "max_turns": 3},
    "leader": {"enabled": true, "max_turns": 2},
    "hr": {"enabled": true, "max_turns": 2}
  }
}
```

**仅技术面（跳过 HR/Leader）**
```json
{
  "total_max_turns": 15,
  "rounds": {
    "tech1": {"enabled": true, "max_turns": 4},
    "tech2": {"enabled": true, "max_turns": 4},
    "sysdes": {"enabled": true, "max_turns": 4},
    "leader": {"enabled": false},
    "hr": {"enabled": false}
  }
}
```

**快速筛选（Tech1 + HR）**
```json
{
  "total_max_turns": 8,
  "rounds": {
    "tech1": {"enabled": true, "max_turns": 5},
    "tech2": {"enabled": false},
    "sysdes": {"enabled": false},
    "leader": {"enabled": false},
    "hr": {"enabled": true, "max_turns": 2}
  }
}
```

---

## 📊 测试结果

```bash
$ conda activate agentEnv && pytest tests/ -v

============================= 测试结果 ==============================
test_budget_guardian.py::test_budget_exceeded_downgrade PASSED
test_budget_guardian.py::test_budget_within_use_plus PASSED
test_conflict_arbitrator.py::test_high_variance_triggers_conflict PASSED
test_conflict_arbitrator.py::test_low_variance_no_conflict PASSED
test_distiller.py::test_memory_distillate_parsing PASSED
test_orchestrator.py::test_state_machine_transitions PASSED
test_orchestrator.py::test_conflict_flag_setting PASSED
test_tools_registry.py::test_agent_permission_matrix PASSED
test_api.py::test_create_session PASSED
test_api.py::test_full_interview_flow PASSED

19 passed in 2.34s
```

---

## 📁 项目结构

```
interview_crew/
├── api.py                  # FastAPI 路由
├── server.py               # Uvicorn 入口
├── cli.py                  # CLI 客户端
├── config.py               # Pydantic 配置
├── state.py                # InterviewState 数据类
├── protocol/schemas.py     # TransferPackage、MemoryDistillate
├── llm/client.py           # LLM 工厂与容错
├── memory/                 # 蒸馏器与面试官邮箱
├── agents/                 # 5 位专业面试官
├── orchestrator/           # 编排器、预算、冲突仲裁
├── tools/                  # 工具注册与实现
└── prompts/                # 面试官系统提示词

docs/
└── TECHNICAL.md            # 详细技术文档

tests/                      # 测试套件（19 项测试）
```

---

## 🛠️ 路线图

- [x] 基于 LangChain LCEL 的核心多 Agent 架构
- [x] 5 位专业面试官，独立记忆隔离
- [x] 预算治理与冲突仲裁机制
- [x] 可配置的面试轮次
- [ ] 持久化会话存储（当前为内存存储）
- [ ] Web UI 可视化面试管理
- [x] 基线评估：单 Agent vs 多 Agent 对比
- [ ] 支持自定义面试官人设

---

## 📝 引用

```bibtex
@software{interviewcrew2025,
  title={InterviewCrew: Multi-Agent Interview Simulator},
  author={Wentao Li},
  year={2025},
  url={https://github.com/sadlavaarsc/InterviewCrew}
}
```

---

<p align="center">
  Made with ❤️ for better interview preparation
</p>
