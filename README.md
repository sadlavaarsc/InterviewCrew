<h1 align="center">InterviewCrew</h1>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-blue.svg" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/LangChain-Core-green.svg" alt="LangChain">
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
- **💰 Production-Grade Cost Control**: **~¥4-20 per interview** (vs ~¥17-34 for single-agent) — 70% calls use cheaper default/economy model via BudgetGuardian + Memory Distiller
- **🔬 Validated by A/B Testing**: MAS scores **86.2/100** vs SAS **52.5/100** (+64% lead) on role consistency, memory isolation, and technical coverage
- **🔌 Flexible Configuration**: Enable/disable any interview round, customize turn limits per agent
- **⚡ Dual Model Fallback**: DeepSeek primary + Ark fallback; Qwen/DashScope kept as deprecated compatibility
- **🔥 Backend Architecture Upgrade (v0.2.0)**: True async streaming SSE (`async_step()` + `async_llm.astream()`), tiktoken precise token counting, Redis session persistence, Prometheus-style /metrics, token bucket rate limiting, 18-problem sandbox + 20-case AST extended benchmark all green
- **🧪 Single Agent Baseline**: Built-in baseline for quantitative comparison — same APIs, fair benchmark

---

## 🧪 Single Agent Baseline

InterviewCrew includes a **Single Agent Baseline** for quantitative comparison with the Multi-Agent System. Both modes expose identical APIs and follow the same interview flow, making it easy to run A/B tests.

### Quick Comparison

| Feature | Multi-Agent | Single-Agent Baseline |
|---------|-------------|----------------------|
| **Architecture** | 5 specialist agents + orchestrator | 1 all-in-one agent |
| **Interview Flow** | `tech1 → tech2 → sysdes → leader → hr` | Same hardcoded workflow |
| **Memory** | Isolated per agent | **Unified history (all stages visible)** |
| **Role Switching** | Swap Agent instance | **Dynamic prompt拼接** |
| **Model Strategy** | Per-agent budget with downgrade | Premium for interview, default/economy for report |
| **Key Challenge** | Coordination overhead | **Role confusion & memory pollution** |

### How SAS "Switches Roles"

Unlike MAS which loads different Agent instances, SAS dynamically builds the system prompt for each turn:

```python
# Before each LLM call, SAS constructs stage-specific prompt
stage_prompt = f"""{base_prompt}

【当前阶段】你现在正在进行：{stage_desc}

重要提醒：
1. 你是一位面试官，现在正在扮演"{current_stage}"的角色
2. 你可以看到之前的全部对话历史，但要注意维持当前阶段的角色一致性
3. 阶段切换时主动调整提问风格和关注点
"""
```

**This creates intentional challenges for SAS:**
- **Context Length**: Must process 15+ rounds of full history
- **Role Confusion**: Difficult to "forget" previous stage's persona
- **Memory Pollution**: Tech-2's questions may influence HR's evaluation

### Usage

```bash
# Multi-Agent mode (default) - True specialists with isolated memory
curl -X POST http://localhost:8000/sessions \
  -d '{"mode": "multi_agent", "total_max_turns": 15}'

# Single-Agent Baseline - One agent playing 5 roles with full history
curl -X POST http://localhost:8000/sessions \
  -d '{"mode": "single_agent", "total_max_turns": 15}'
```

Both modes return the same response format with `agent: "tech1" | "tech2" | ...`.

---

## 📊 Benchmark: Multi-Agent vs Single-Agent

We conducted rigorous A/B testing with identical candidates, resumes, and JDs:

### Quantitative Results

| Dimension | MAS (Multi-Agent) | SAS (Single-Agent) | Lead |
|-----------|-------------------|-------------------|------|
| **Role Consistency** | 90/100 | 55/100 | **+64%** |
| **Memory Isolation** | 85/100 | 40/100 | **+113%** |
| **Technical Coverage** | 88/100 | 65/100 | **+35%** |
| **Follow-up Depth** | 82/100 | 50/100 | **+64%** |
| **Factual Accuracy** | 85/100 | 75/100 | **+13%** |
| **Overall Score** | **86.2** | **52.5** | **+64%** |

*Evaluation: Independent subagent scored 6 dimensions based on full conversation logs*

### Key Findings

**1. Memory Isolation Works**
- MAS agents receive only previous stage summaries — prevents conversation pollution
- SAS suffered severe topic drift (candidate switched projects, interviewer didn't notice)
- Follow-up continuity: MAS averages 1.9 rounds/topic vs SAS placeholders

**2. Clear Role Boundaries**
- tech1/tech2/sysdes/leader/hr strictly follow stage positioning
- SAS stage switching confusion: 6 of 14 rounds were placeholders (57% completeness)

**3. Comprehensive Technical Coverage**
- MAS covers all 6 JD knowledge domains (LLM apps, Agent frameworks, RAG, RL, System Design, Engineering)
- SAS missed RAG multi-level retrieval, Agent frameworks, MCP protocol requirements

---

## 💰 Cost Analysis

> Model pricing (example): default/economy model ¥0.1/M input ¥0.5/M output | premium/quality model ¥1/M input ¥8/M output — DeepSeek is now the default provider for better long-context pricing

### Cost Control Architecture

| Mechanism | Implementation | Effect |
|-----------|---------------|--------|
| **BudgetGuardian** | Auto-downgrade to default/economy model when tokens exceed budget | 70% calls use cheaper tier |
| **Memory Distiller** | Default model compresses conversation history | 50% context reduction |
| **Scribe Reports** | Default model for long report generation | Significant cost savings |
| **Agent Budgets** | tech1:2000, sysdes:4000, etc. | Enforced cost caps |

### Cost Comparison

| Scenario | MAS | SAS | Note |
|----------|-----|-----|------|
| **No-cache estimate** | ~¥20 | ~¥34 | Fair architecture comparison |
| **Actual test cost** | **~¥4/interview** | ~¥17 | With cache + cost controls |

**Result: MAS is 41% cheaper even without caching, and costs only ¥4 per interview in production.**

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
# Final Evaluation Report (面评报告)

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
DEEPSEEK_API_KEY=your_deepseek_key
ARK_API_KEY=your_ark_key
# DASHSCOPE_API_KEY=your_dashscope_key  # deprecated, kept for compatibility
```

### Run Web UI

```bash
# Start backend
python -m interview_crew.server

# Open browser at http://localhost:8000/
```

The Web UI supports round configuration (enable/disable agents), real-time chat, coding task editor with test execution, token usage stats, and final report display.

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

### API Reference

**Create Session** — `POST /sessions`
```json
// Request
{
  "mode": "multi_agent",           // "multi_agent" (default) or "single_agent"
  "total_max_turns": 15,
  "candidate_response": "Initial response"
}

// Response
{
  "session_id": "uuid",
  "status": "ongoing",
  "mode": "multi_agent"
}
```

**Step Through Interview** — `POST /sessions/{id}/step`
```json
// Request
{
  "candidate_response": "Your answer"
}

// Response
{
  "agent": "tech1",
  "question": "Next question...",
  "finished": false,
  "report": "",
  // Token statistics
  "token_consumed_this_turn": 1250,
  "total_token_consumed": 8750,
  // Detailed breakdown by model tier
  "plus_token_consumed_this_turn": 1000,
  "flash_token_consumed_this_turn": 250,
  "total_plus_token_consumed": 7000,
  "total_flash_token_consumed": 1750
}
```

**Get Session State** — `GET /sessions/{id}`
```json
{
  "session_id": "uuid",
  "status": "ongoing",
  "current_agent": "tech1",
  "turn": 5,
  // Mode and statistics
  "mode": "single_agent",
  "llm_call_count": 10,
  "token_consumed": 8750,
  // Detailed breakdown
  "plus_call_count": 8,
  "flash_call_count": 2,
  "total_plus_token_consumed": 7000,
  "total_flash_token_consumed": 1750
}
```

---

## 🔥 Backend Architecture Upgrade (v0.2.0)

Production-grade backend improvements targeting high-performance, scalable AI service architecture:

### Async Streaming + SSE
- **AsyncLLMClient** with `httpx` connection pooling — replaces synchronous blocking calls
- **SSE endpoint** `/sessions/{id}/stream` for real-time token-by-token response streaming
- **83% TTFT reduction**: ~3500ms → ~600ms time-to-first-token
- **33x concurrency gain**: ~3 → ~100 concurrent sessions per node (validated with DeepSeek API: 100 concurrent, 0 failures)

### Precise Token Counting & Observability
- **tiktoken** (`cl100k_base`) replaces `chars/4` heuristic
- **Token accuracy**: 57% average error → **<2% error**
- **Prometheus-style `/metrics`** endpoint with P50/P95/P99 latency histograms
- Per-agent token consumption tracking

### Real Code Execution Sandbox
- **Subprocess-isolated execution** with 2s timeout and 256MB memory limit
- **AST static analysis**: cyclomatic complexity, time/space complexity inference, anti-pattern detection
- **Security filtering**: 100% block rate on dangerous operations (os, subprocess, eval, exec, file I/O)

### High Availability
- **Redis session persistence** with 24h TTL — automatic recovery after restart
- **Token bucket rate limiter** — per-session and global limits
- **Serialization overhead**: <0.5ms per session

### Benchmark Results

| Metric | Before (v0.1) | After (v0.2) | Improvement |
|--------|--------------|--------------|-------------|
| TTFT | ~3500ms | **~355ms** (实测) | **↓90%** |
| Concurrent sessions | ~3 | **~100** | **↑33x** |
| Token counting error | 57% | **<2%** | **Precision** |
| Code execution | Mock heuristic | **Docker/Subprocess + AST** | **Quality** |
| Session persistence | In-memory (lost on restart) | **Redis (24h)** | **Reliability** |
| Observability | None | **/metrics + histograms** | **Production** |

See full report: [reports/BENCHMARK_20260610.md](reports/BENCHMARK_20260610.md)

---

## 🏗️ Architecture

```
┌─────────────┐     HTTP/SSE       ┌──────────────────────────────────────────┐
│  Web / CLI  │  ◄──────────────►  │        FastAPI Backend (Async)           │
│   Client    │                    │  ┌────────────────────────────────────┐  │
└─────────────┘                    │  │  /              ──Web UI           │  │
                                   │  │  /sessions      ──Create/Recover   │  │
                                   │  │  /step          ──Sync Progress    │  │
                                   │  │  /stream        ──SSE Streaming    │  │
                                   │  │  /metrics       ──Prometheus       │  │
                                   │  │  /health        ──Health           │  │
                                   │  └────────────────────────────────────┘  │
                                   │                    │                      │
                                   │      ┌─────────────▼──────────────┐       │
                                   │      │   Token Bucket Rate Limit  │       │
                                   │      └─────────────┬──────────────┘       │
                                   │                    │                      │
                                   │      ┌─────────────▼──────────────┐       │
                                   │      │   Redis Session Store      │       │
                                   │      │   (24h TTL, auto-recovery) │       │
                                   │      └─────────────┬──────────────┘       │
                                   │                    │                      │
                                   │      ┌─────────────▼──────────────┐       │
                                   │      │   Orchestrator Engine      │       │
                                   │      └─────────────┬──────────────┘       │
                                   │                    │                      │
                                   │      ┌─────────────▼──────────────┐       │
                                   │      │  AsyncLLMClient + tiktoken │       │
                                   │      │  (Connection Pool, Stream) │       │
                                   │      └────────────────────────────┘       │
                                   └──────────────────────────────────────────┘
```

**Core Components**:
- **AsyncLLMClient**: Async OpenAI client with connection pooling and SSE streaming
- **Orchestrator**: State machine managing interview flow
- **5 Specialist Agents**: Each with isolated memory and specialized tools
- **Budget Guardian**: Per-agent token budget with auto-downgrade
- **Conflict Arbitrator**: Detects scoring variance, triggers re-evaluation
- **Memory Distiller**: Compresses conversation history for context
- **Code Sandbox**: Real subprocess execution with AST analysis
- **Session Store**: Redis persistence with automatic recovery
- **Rate Limiter**: Token bucket for per-session and global limits

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
57 passed
```

---

## 📁 Project Structure

```
interview_crew/
├── api.py                      # FastAPI routes + SSE + metrics
├── server.py                   # Uvicorn entry
├── cli.py                      # CLI client
├── static/                     # Web UI (index.html)
├── config.py                   # Pydantic settings (+ Redis)
├── state.py                    # InterviewState (serializable)
├── protocol/schemas.py         # TransferPackage, MemoryDistillate
├── llm/
│   ├── client.py               # Sync LLM factory
│   ├── async_client.py         # Async streaming client
│   ├── token_counter.py        # tiktoken precise counting
│   └── metrics.py              # Prometheus-style metrics
├── services/
│   ├── code_sandbox.py         # Unified sandbox interface
│   ├── code_executor.py        # Subprocess execution engine
│   └── ast_analyzer.py         # AST static analysis
├── storage/
│   └── session_store.py        # Redis / Memory abstraction
├── middleware/
│   └── rate_limiter.py         # Token bucket rate limiting
├── memory/                     # Distiller & agent mailbox
├── agents/                     # 5 specialist agents
├── orchestrator/               # Engine, budget, conflict
├── tools/                      # Tool registry & stubs
└── prompts/                    # Agent system prompts

benchmarks/                     # Performance & sandbox benchmarks
docs/
└── TECHNICAL.md                # Detailed technical documentation

reports/
└── BENCHMARK_20260610.md       # Quantitative benchmark report

tests/                          # pytest suite (57+ tests)
```

---

## 🛠️ Roadmap

- [x] Core multi-agent architecture with LangChain LCEL
- [x] 5 specialist agents with isolated memory
- [x] Budget governance & conflict arbitration
- [x] Configurable interview rounds
- [x] Async streaming SSE with connection pooling
- [x] tiktoken precise token counting + Prometheus /metrics
- [x] Real code execution sandbox with AST analysis
- [x] Redis session persistence with auto-recovery
- [x] Token bucket rate limiting
- [x] Web UI for visual interview management
- [x] Baseline evaluation: Single Agent vs Multi-Agent
- [ ] Docker-based container sandbox
- [ ] Support for custom agent personas

---

## 📝 Citation

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
