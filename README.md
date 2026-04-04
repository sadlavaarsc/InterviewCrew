<h1 align="center">InterviewCrew</h1>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-blue.svg" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/LangGraph-✓-green.svg" alt="LangGraph">
  <img src="https://img.shields.io/badge/FastAPI-✓-009688.svg" alt="FastAPI">
  <img src="https://img.shields.io/badge/Multi--Agent-5_roles-purple.svg" alt="5 Agents">
  <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="MIT License">
</p>

<p align="center">
  <a href="README.md"><b>English</b></a> •
  <a href="README_CN.md">中文</a>
</p>

<p align="center">
  <b>Multi-Agent Interview Simulator for Programmers</b><br>
  <i>Stop practicing with predictable bots. Face the real "three-sided attack".</i>
</p>

<p align="center">
  <a href="#-highlights">Highlights</a> •
  <a href="#-demo">Demo</a> •
  <a href="#-quick-start">Quick Start</a> •
  <a href="#-architecture">Architecture</a> •
  <a href="#-configuration">Configuration</a> •
  <a href="docs/TECHNICAL.md">Technical Docs</a>
</p>

---

## 🔥 Highlights

- **🎭 5 Specialist Agents**: Tech-1 (algorithm), Tech-2 (deep dive), SysDes (architecture), HR (behavioral), Scribe (evaluation) — each with independent memory and persona
- **🧠 Context Isolation**: Agents only see their own conversation history, preventing "role confusion" common in single-agent systems
- **📊 Structured Evaluation**: Competency-based scoring with conflict arbitration — when two agents disagree on a dimension, Tech-2 automatically re-evaluates
- **💰 Budget-Aware**: Per-agent token budgets with automatic model downgrade to control costs
- **🔌 Flexible Configuration**: Enable/disable any interview round, customize turn limits per agent
- **⚡ Dual Model Fallback**: Ark + DashScope automatic failover for stability

---

## 🎬 Demo

### Real Interview Flow (14 turns, 5 stages)

Below is an actual test run demonstrating the multi-agent collaboration:

<details>
<summary><b>🔹 Stage 1: Tech-1 (Algorithm Screening)</b></summary>

**Interviewer (Tech-1)**:
*"In your RepoMind project, you mentioned AST-based multi-level chunking. Did you use Python's built-in `ast` module or third-party libraries like `tree-sitter` for cross-file call relationships?"*

**Candidate**:
*"We used a hybrid approach: Python standard `ast` for Python code, tree-sitter for 12 languages including Java/C++/Go, with a unified AST traversal interface..."*

**Interviewer (Tech-1)**:
*"You mentioned multi-threaded parsing. How do you avoid concurrent write conflicts to the symbol table?"*

**Candidate**:
*"We use 'cache-first + optimistic locking': each thread checks global cache before parsing, and we use 16 segmented locks for the symbol table..."*

**→ Then coding challenge: Find duplicate in array with O(n) time, O(1) space without modifying array**

</details>

<details>
<summary><b>🔹 Stage 2: Tech-2 (Deep Dive)</b></summary>

**Interviewer (Tech-2)**:
*"If file A modifies a function signature referenced by file B, but B itself has no code changes, how does your global symbol table detect that B's index is stale? Won't transitive dependency tracking cause full rebuilds in extreme cases?"*

**Candidate**:
*"We solve this with reverse dependency index: each symbol maintains a 'referenced-by file list'. When A modifies a signature, all files in that list are marked for update—only direct references, not recursive..."*

**Interviewer (Tech-2)**:
*"What about A→B→C chain calls? If C changes and B's return structure changes but interface signature doesn't, your reverse index won't detect it, right?"*

**Candidate**:
*"That's correct. We compensate in three ways: (1) signatures include return type structure, (2) static type analysis, (3) unit test gating triggers rebuild if tests fail..."*

</details>

<details>
<summary><b>🔹 Stage 3: System Design (Architecture)</b></summary>

**Interviewer (Architect)**:
*"The '1-level pruning' strategy is attractive for performance, but architecturally: if C's change causes B's signature to change, theoretically A also needs updating. With only direct-reference marking, won't you miss transitive signature changes? What's your degradation strategy?"*

**Candidate**:
*"We balance performance vs. completeness with three compensation mechanisms: (1) daily full validation during off-peak hours for eventual consistency, (2) impact analysis for core path changes, (3) user-triggered full rebuild API. 1-level pruning covers 99% of cases; remaining 1% is handled by these fallbacks..."*

</details>

<details>
<summary><b>🔹 Stage 4: HR (Behavioral)</b></summary>

**Interviewer (HR)**:
*"You mentioned '1-level pruning covers 99% of cases'—is this based on actual test sets or theoretical estimates? If the兜底机制 triggers frequently and slows things down, how do you weigh 'refactoring optimization' vs 'business delivery' pressure? Share a specific example where you abandoned 'perfect design' due to real constraints."*

**Candidate**:
*"The 99% is from statistics on 3 real projects pre-launch, not theoretical. If兜底 triggers frequently, I'd do gray release: enable 2-level pruning for new users, observe for a week. I faced this with RepoMind V1: I designed a perfect distributed cache architecture but the business needed demo in 2 weeks. I chose local cache for fast launch, then refactored to distributed in iteration 2..."*

**Interviewer (HR)**:
*"If you join us and find our tech stack is much older than what you used, how would you drive upgrades?"*

**Candidate**:
*"Tech stack is just a tool—solving problems is what matters. I'd start with non-core modules for pilot, get data on actual benefits, then gradually promote. Business stability comes first; tech upgrades serve the business..."*

</details>

<details>
<summary><b>🔹 Stage 5: Scribe (Final Evaluation)</b></summary>

```markdown
# 面评报告

## 技术评估
候选人在代码感知RAG系统（RepoMind）中展现了深厚的技术积累，特别是在AST解析、
增量索引优化及依赖图构建方面具备全链路经验...

## 推荐
Strong Hire

## 证据链
- **系统设计能力**: 提出混合式AST解析架构、反向依赖索引及三重补偿机制
- **工程权衡思维**: RepoMind V1案例中，为满足两周上线deadline，权衡后选择本地缓存方案
- **数据驱动决策**: 剪枝策略基于真实测试集统计，而非纯理论估算
```

</details>

> 📄 **Full test log**: [data/records/FULL_TEST_DIALOG_20260404_FULL_FLOW.md](data/records/FULL_TEST_DIALOG_20260404_FULL_FLOW.md)

---

## 🚀 Quick Start

### Prerequisites

```bash
# Must run in agentEnv conda environment
conda activate agentEnv
pip install -r requirements.txt
```

Configure `.env`:
```bash
ARK_API_KEY=your_ark_key
DASHSCOPE_API_KEY=your_dashscope_key
```

### Run CLI Demo

```bash
# Start backend
python -m interview_crew.server

# In another terminal, run CLI
python -m interview_crew.cli --turns 6 --resume ./candidate.md --jd ./jd.md
```

### API Usage

```bash
# Create session with custom configuration
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

# Step through interview
curl -X POST http://localhost:8000/sessions/{session_id}/step \
  -H "Content-Type: application/json" \
  -d '{"candidate_response": "Your answer here"}'
```

---

## 🏗️ Architecture

```
┌─────────────┐     HTTP/JSON      ┌─────────────────────────────────────┐
│   CLI/API   │  ◄──────────────►  │        FastAPI Backend              │
│   Client    │                    │  ┌───────────────────────────────┐  │
└─────────────┘                    │  │  /sessions      ──Create      │  │
                                   │  │  /step          ──Progress    │  │
                                   │  │  /health        ──Health      │  │
                                   │  └───────────────────────────────┘  │
                                   │                 │                    │
                                   │                 ▼                    │
                                   │      ┌──────────────────┐            │
                                   │      │   Orchestrator   │            │
                                   │      │     Engine       │            │
                                   │      └────────┬─────────┘            │
                                   │               │                      │
                                   │      ┌────────▼─────────┐            │
                                   │      │  Agent LCEL Chain│            │
                                   │      └──────────────────┘            │
                                   └─────────────────────────────────────┘
```

**Core Components**:
- **Orchestrator**: State machine managing interview flow
- **5 Specialist Agents**: Each with isolated memory and specialized tools
- **Budget Guardian**: Per-agent token budget with auto-downgrade
- **Conflict Arbitrator**: Detects scoring variance, triggers re-evaluation
- **Memory Distiller**: Compresses conversation history for context

---

## ⚙️ Configuration

### Interview Round Configuration

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `total_max_turns` | int | 30 | Global max turns across all agents |
| `rounds.{agent}.enabled` | bool | true | Enable/disable this agent |
| `rounds.{agent}.max_turns` | int | varies | Max turns for this agent |
| `rounds.{agent}.max_chat_turns` | int | 2 | Chat sub-stage max turns |
| `rounds.{agent}.max_reflect_turns` | int | 1 | Reflect sub-stage max turns |

### Preset Configurations

**Full Interview (Default)**
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

**Tech-Only (Skip HR/Leader)**
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

**Quick Screening (Tech1 + HR)**
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

## 📊 Test Results

```bash
$ conda activate agentEnv && pytest tests/ -v

============================= test results ==============================
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

## 📁 Project Structure

```
interview_crew/
├── api.py                  # FastAPI routes
├── server.py               # Uvicorn entry
├── cli.py                  # CLI client
├── config.py               # Pydantic settings
├── state.py                # InterviewState dataclass
├── protocol/schemas.py     # TransferPackage, MemoryDistillate
├── llm/client.py           # LLM factory with fallback
├── memory/                 # Distiller & agent mailbox
├── agents/                 # 5 specialist agents
├── orchestrator/           # Engine, budget, conflict
├── tools/                  # Tool registry & stubs
└── prompts/                # Agent system prompts

docs/
└── TECHNICAL.md            # Detailed technical documentation

tests/                      # pytest suite (19 tests)
```

---

## 🛠️ Roadmap

- [x] Core multi-agent architecture with LangGraph
- [x] 5 specialist agents with isolated memory
- [x] Budget governance & conflict arbitration
- [x] Configurable interview rounds
- [ ] Persistent session storage (currently in-memory)
- [ ] Web UI for visual interview management
- [ ] Baseline evaluation: Single Agent vs Multi-Agent
- [ ] Support for custom agent personas

---

## 📝 Citation

```bibtex
@software{interviewcrew2025,
  title={InterviewCrew: Multi-Agent Interview Simulator},
  author={InterviewCrew Team},
  year={2025},
  url={https://github.com/yourusername/InterviewCrew}
}
```

---

<p align="center">
  Made with ❤️ for better interview preparation
</p>