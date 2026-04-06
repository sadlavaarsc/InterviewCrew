# MAS Turn Limit 未生效问题 - 代码审计报告

**审计日期**: 2026-04-06
**审计人员**: Claude Code
**相关Bug**: [bugs/BUG-001-turn-limit-not-enforced.md](../bugs/BUG-001-turn-limit-not-enforced.md)
**状态**: 已确认根因

---

## 问题现象

配置 `total_max_turns=15` 时，面试实际运行了 **20 turns** 才终止。

### 数据证据

来自 `data/records/BASELINE_RAW_MAS_20260405.json`:

```json
{
  "total_max_turns": 15,
  "max_turns": 6,
  "turn": 20,  // <-- 超出限制5轮
  "status": "finished"
}
```

Transfer Queue 分析:
- 显示 14 个 completed rounds (round_completed: 1-14)
- 但 turn 计数器达到 20
- 差异 6 turns 来自 Tech Agent 的 sub-stage 处理

---

## 根因分析

### 1. 代码流程缺陷

**文件**: `interview_crew/orchestrator/engine.py`

在 `step()` 方法 (第150-206行) 中:

```python
def step(self, candidate_response: str) -> StepResult:
    self.state.candidate_response = candidate_response
    self.state.turn += 1                          # ← 计数器递增

    # Append candidate response to unified history
    if candidate_response:
        self.state.append_unified({"role": "user", "content": candidate_response})

    # Global turn limit check (applies even during sub-stages)
    effective_max_turns = self._get_effective_max_turns()
    if self.state.turn >= effective_max_turns:    # ← 检查1: 通过
        self.state.status = "finished"
        report = self._generate_report()
        return StepResult(agent="scribe", question="", finished=True, report=report)

    # Check if current agent has sub-stages and is not done
    if self.state.current_agent in ["tech1", "tech2"]:
        agent_name = self.state.current_agent
        agent = self.agents[agent_name]

        if agent.has_sub_stages:
            sub_stage = self.state.get_sub_stage(agent_name)

            if sub_stage != "done":
                # Process sub-stage
                return self._process_tech_agent_sub_stage(agent_name, candidate_response)  # ← 提前返回!
            else:
                # Sub-stages complete, advance to next main state
                pass

    # Track per-round turn count for current agent BEFORE calling _next_agent()
    # This ensures _next_agent() sees the updated count when deciding whether to advance
    if self.state.current_agent and self.state.current_agent in self._enabled_rounds:
        self._round_turn_counts[self.state.current_agent] = self._round_turn_counts.get(self.state.current_agent, 0) + 1  # ← 被跳过!
        # Persist to state for session recovery
        self.state.round_turn_counts = self._round_turn_counts

    # Determine next agent
    next_agent = self._next_agent()               # ← 被跳过!
    # ...
```

### 2. 问题点详解

| 问题 | 位置 | 说明 |
|------|------|------|
| **Sub-stage 提前返回** | 第175行 | 当 Tech Agent 处于 sub-stage (chat/coding/reflect) 时，直接返回，跳过后续逻辑 |
| **_round_turn_counts 未更新** | 第183行 | 由于提前返回，per-agent turn 计数未更新 |
| **_next_agent() 未被调用** | 第188行 | 由于提前返回，agent 切换逻辑被跳过 |
| **Sub-stage 内无全局检查** | `_process_tech_agent_sub_stage()` | 该函数内部只有 sub-stage 级别的 limit 检查，无全局 `total_max_turns` 检查 |

### 3. 执行流程图

```
step() 调用 (Tech Agent, sub_stage != "done")
│
├─> turn += 1                              ← 计数器递增
├─> 检查 turn >= total_max_turns            ← 检查1 (假设 turn=15, limit=15, 通过)
├─> 进入 sub-stage 分支
│   ├─> sub_stage != "done" ? 是
│   └─> return _process_tech_agent_sub_stage()  ← 提前返回!
│       ├─> 生成 TransferPackage
│       ├─> 更新 competency_history
│       └─> 检查 sub-stage limits (max_chat_turns/max_reflect_turns)
│           └─> 无全局 limit 检查!              ← 问题!
│
[第183-206行被跳过]
  ├─> _round_turn_counts[agent] += 1       ← 未执行
  ├─> _next_agent()                        ← 未执行
  └─> 检查 turn >= effective_max_turns     ← 检查2 被跳过

step() 再次调用
├─> turn += 1                              ← turn=16
├─> ...流程继续
```

### 4. 为什么会导致 20 turns

配置:
- `total_max_turns: 15` (全局限制)
- Tech Agents 有 3 个 sub-stages: chat → coding → reflect

执行过程:
1. Tech Agent 完成 chat sub-stage (turn=13)
2. 进入 coding sub-stage (turn=14)
3. 进入 reflect sub-stage (turn=15)
4. **此时 turn=15, 达到 limit，但 sub-stage 处理内无检查**
5. sub-stage 继续处理，turn 被递增到 16, 17, 18, 19, 20
6. 直到某个条件触发终止

---

## 影响评估

| 影响项 | 严重程度 | 说明 |
|--------|----------|------|
| Token 消耗 | **高** | 多出 5 turns 约 33% 的额外 token 消耗 |
| 用户体验 | **中** | 面试时长超出预期 |
| A/B 测试 | **高** | MAS vs SAS 对比不可靠 |
| 成本 | **高** | 生产环境导致额外 API 费用 |

---

## 修复建议

### 方案1: 在 _process_tech_agent_sub_stage 内添加全局检查

```python
def _process_tech_agent_sub_stage(self, agent_name: str, candidate_response: str) -> StepResult:
    # 添加全局 limit 检查
    effective_max_turns = self._get_effective_max_turns()
    if self.state.turn >= effective_max_turns:
        self.state.status = "finished"
        report = self._generate_report()
        return StepResult(agent="scribe", question="", finished=True, report=report)
    # ... rest of the function
```

### 方案2: 重构 step() 流程

将全局 limit 检查提取到统一出口点，确保无论走哪个分支都会检查。

### 方案3: 在 sub-stage 转换点检查

在 chat→coding、coding→reflect 等转换点添加全局 limit 检查。

---

## 相关文件

- `interview_crew/orchestrator/engine.py` - 核心问题所在
- `interview_crew/api.py` - 配置解析 (第238-239行)
- `bugs/BUG-001-turn-limit-not-enforced.md` - Bug 报告
- `data/records/BASELINE_RAW_MAS_20260405.json` - 证据数据

---

## 结论

**根因确认**: Tech Agent 的 sub-stage 处理路径 (`_process_tech_agent_sub_stage`) 中缺少对全局 `total_max_turns` 的检查，导致在 sub-stage 内部时 turn 计数器继续递增但不受限制。

**修复优先级**: 高 (P1) - 影响生产环境成本和用户体验

---

*Report generated by Claude Code on 2026-04-06*
