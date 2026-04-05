# MAS 提前终止问题代码审计报告

**审计日期**: 2026-04-05
**审计对象**: `interview_crew/orchestrator/engine.py`, `interview_crew/api.py`
**问题描述**: MAS 模式在使用自定义 `rounds_config` 时，面试在达到预期轮次前提前终止
**严重程度**: 高

---

## 1. 执行摘要

经代码审计，确认 MAS 存在**面试流程控制逻辑缺陷**。当通过 API 配置 `rounds_config` 指定各面试官轮次时，编排器（Orchestrator）会**在每次调用 `step()` 时递增轮次索引**，导致面试在消耗完配置的 `total_max_turns` 之前就遍历完所有启用的面试轮次，触发提前终止。

**核心问题**: `_next_agent()` 方法的执行时机与 `_current_round_index` 递增逻辑不匹配。

---

## 2. 问题详细分析

### 2.1 代码流程追踪

#### Step 1: API 层配置传递（`api.py:238-239`）

```python
effective_total_turns = req.total_max_turns if req.total_max_turns != 30 else req.max_turns
config = InterviewConfig(total_max_turns=effective_total_turns)
```

**问题**: 当 `total_max_turns=15` 被显式设置时，`effective_total_turns = 15`。但如果使用默认值 30，则回退到 `max_turns`（默认 6）。

#### Step 2: Orchestrator 初始化（`engine.py:62-63`）

```python
self._enabled_rounds = self.state.config.get_enabled_rounds()  # ["tech1", "tech2", "sysdes", "leader", "hr"]
self._current_round_index = self._get_current_round_index()    # 初始化为 0
```

#### Step 3: 关键的 step() 方法流程（`engine.py:132-181`）

```python
def step(self, candidate_response: str) -> StepResult:
    self.state.turn += 1                    # 全局回合计数器 +1

    # ... 全局限制检查 ...
    if self.state.turn >= effective_max_turns:
        return self._generate_final_report()  # 第5回合触发（如果配置15轮，但只执行了5次step）

    # 检查子阶段（仅 tech1/tech2）
    if self.state.current_agent in ["tech1", "tech2"]:
        if sub_stage != "done":
            return self._process_tech_agent_sub_stage(...)  # 处理子阶段

    # 确定下一个 Agent（关键逻辑）
    next_agent = self._next_agent()         # ⚠️ 每次调用都会递增 _current_round_index

    if next_agent == "scribe":
        return self._generate_final_report()  # 提前触发终止
```

#### Step 4: _next_agent() 方法缺陷（`engine.py:106-130`）

```python
def _next_agent(self) -> str:
    # 检查当前轮次是否达到限制
    if self.state.current_agent and self.state.current_agent in self._enabled_rounds:
        round_config = self.state.config.get_round_config(self.state.current_agent)
        current_round_turns = self._round_turn_counts.get(self.state.current_agent, 0)
        if current_round_turns >= round_config.max_turns:
            pass  # 应该前进到下一轮，但这里只是 pass

    if self._current_round_index >= len(self._enabled_rounds):
        return "scribe"  # 终止信号

    next_agent = self._enabled_rounds[self._current_round_index]
    self._current_round_index += 1  # ⚠️ 每次调用都递增，无论当前轮次是否完成
    return next_agent
```

### 2.2 问题根因

| 问题 | 说明 |
|------|------|
| **轮次索引过早递增** | `_current_round_index += 1` 在 `_next_agent()` 每次被调用时都会执行，而不是在当前轮次的所有子阶段完成后才执行 |
| **子阶段检查位置不当** | 子阶段检查（`sub_stage != "done"`）在 `_next_agent()` 调用之前，但当子阶段标记为 "done" 后，立即调用 `_next_agent()` 导致索引递增 |
| **缺少每轮次回合计数** | `_round_turn_counts` 只用于检查，不会影响 `_current_round_index` 的递增逻辑 |
| **全局回合检查优先** | `self.state.turn >= effective_max_turns` 检查会在 `_next_agent()` 之前触发终止 |

### 2.3 执行流程演示

以配置 `total_max_turns=15`, `rounds_config={tech1:4, tech2:4, sysdes:3, leader:2, hr:2}` 为例：

| 调用 | state.turn | _current_round_index | 当前 Agent | 动作 | 结果 |
|------|------------|----------------------|------------|------|------|
| Initial | 0 | 0 | "" | - | tech1 开始 |
| step 1 | 1 | 1 | tech1 | chat 阶段 | 正常 |
| step 2 | 2 | 2 | tech2 | chat→coding | 切换 Agent（过早） |
| step 3 | 3 | 3 | sysdes | - | 跳过 tech2 剩余轮次 |
| step 4 | 4 | 4 | hr | - | 跳过 leader |
| step 5 | 5 | 5 | - | _next_agent 返回 "scribe" | **提前终止** |

**实际结果**: 只执行了 5 个回合，而不是预期的 15 个回合。

---

## 3. 问题影响评估

### 3.1 功能影响

- **面试不完整**: 候选人只经历了部分面试轮次
- **评估缺失**: Scribe 生成的面评报告基于不完整的数据
- **配置失效**: `rounds_config` 中的 `max_turns` 设置被忽略

### 3.2 影响范围

| 配置场景 | 是否受影响 | 说明 |
|----------|-----------|------|
| 使用默认配置 | 是 | 默认 30 轮，但实际只会执行 5 轮（5 个 agent） |
| 使用 `rounds_config` | 是 | 问题主要触发场景 |
| 单 Agent Baseline | 否 | SAS 使用独立的 `SingleAgentOrchestrator` |

---

## 4. 代码定位

### 主要问题文件

```
interview_crew/orchestrator/engine.py
  ├── Line 106-130: _next_agent() 方法 - 轮次索引递增逻辑错误
  ├── Line 132-181: step() 方法 - 子阶段检查与轮次切换顺序问题
  └── Line 66: _round_turn_counts - 计数器更新位置不当（Line 172）

interview_crew/api.py
  └── Line 238: effective_total_turns 计算逻辑存在歧义
```

### 关键问题代码段

```python
# engine.py:117-123 - 轮次限制检查逻辑不完整
if self.state.current_agent and self.state.current_agent in self._enabled_rounds:
    round_config = self.state.config.get_round_config(self.state.current_agent)
    current_round_turns = self._round_turn_counts.get(self.state.current_agent, 0)
    if current_round_turns >= round_config.max_turns:
        pass  # 没有实际作用，只是占位

# engine.py:128-129 - 每次调用都递增索引
next_agent = self._enabled_rounds[self._current_round_index]
self._current_round_index += 1  # 这是问题的核心
```

---

## 5. 修复建议（仅参考，不实施）

### 方案 A: 修复轮次索引递增逻辑

在 `_next_agent()` 中，只有当当前轮次真正完成（达到 `max_turns` 或子阶段完成）时才递增索引：

```python
def _next_agent(self) -> str:
    # 如果当前轮次未完成，继续当前轮次
    if self.state.current_agent and self.state.current_agent in self._enabled_rounds:
        round_config = self.state.config.get_round_config(self.state.current_agent)
        current_round_turns = self._round_turn_counts.get(self.state.current_agent, 0)

        # 检查是否还有剩余轮次
        if current_round_turns < round_config.max_turns:
            return self.state.current_agent  # 继续当前轮次
        # 否则前进到下一轮

    # 前进到下一轮
    if self._current_round_index >= len(self._enabled_rounds):
        return "scribe"

    next_agent = self._enabled_rounds[self._current_round_index]
    self._current_round_index += 1
    return next_agent
```

### 方案 B: 使用独立的每轮次计数器

重构 `_round_turn_counts` 的更新逻辑，确保在 `step()` 开始时检查当前轮次状态：

```python
def step(self, candidate_response: str) -> StepResult:
    self.state.turn += 1

    # 检查当前轮次是否还有剩余回合
    if self.state.current_agent in self._enabled_rounds:
        self._round_turn_counts[self.state.current_agent] = \
            self._round_turn_counts.get(self.state.current_agent, 0) + 1

        round_config = self.state.config.get_round_config(self.state.current_agent)
        if self._round_turn_counts[self.state.current_agent] > round_config.max_turns:
            # 轮次耗尽，强制前进
            self._advance_to_next_round()
```

### 方案 C: 移除 `_current_round_index` 依赖

改为基于 `state.turn` 和 `rounds_config` 动态计算当前应该由哪个 Agent 处理：

```python
def _get_current_agent_by_turn(self) -> str:
    """基于全局回合数和配置动态计算当前 Agent"""
    cumulative_turns = 0
    for agent_name in self._enabled_rounds:
        config = self.state.config.get_round_config(agent_name)
        cumulative_turns += config.max_turns
        if self.state.turn <= cumulative_turns:
            return agent_name
    return "scribe"
```

---

## 6. 间歇性行为说明（重要）

**⚠️ 注意：此 Bug 为间歇性问题，可能无法稳定复现。**

经分析，以下因素导致 Bug 表现不一致：

| 因素 | 影响 |
|------|------|
| **Coding 阶段手动触发** | `coding` 子阶段需要调用 `/submit-code` API 才能推进。如果测试时提交代码，会消耗额外回合；如果跳过，则更快进入 "done" 触发提前终止 |
| **配置解析歧义** | `api.py:238` 的 `total_max_turns != 30` 判断逻辑导致：显式设置 30 会回退到 `max_turns=6`，与直觉相反 |
| **Conflict 仲裁** | 随机触发的评分冲突会强制返回 `tech2` 但不递增索引，打乱计数 |

**实测现象差异原因**：
- 完整测试（含代码提交）：可能给人"正常"的错觉，因为 coding 阶段阻塞了 `step()` 调用
- 快速测试（跳过代码提交）：更快触发提前终止

**⚠️ 目前没有实测数据精确量化触发条件，以上为代码逻辑推测。**

---

## 7. 验证建议

1. **单元测试**: 添加针对 15 轮配置的测试用例
   ```python
   def test_15_turn_config_runs_full_interview():
       config = InterviewConfig(
           total_max_turns=15,
           rounds={...}  # tech1:4, tech2:4, sysdes:3, leader:2, hr:2
       )
       # 验证执行 15 次 step() 后才返回 finished=True
   ```

2. **集成测试**: 使用 API 创建会话并验证完整流程

3. **日志增强**: 在 `_next_agent()` 和 `step()` 中添加调试日志，追踪：
   - `_current_round_index` 的变化
   - `_round_turn_counts` 的更新
   - Agent 切换的原因

---

## 8. 结论

MAS 提前终止问题是由于 `Orchestrator._next_agent()` 方法的**轮次索引递增逻辑缺陷**导致的。该方法在每次 `step()` 调用时都递增 `_current_round_index`，而不是在当前轮次的所有配置回合完成后才递增。

这导致即使配置了 15 个总回合（5 个 agent × 各自 max_turns），面试也会在执行 5 次 `step()` 后终止（每个 agent 只执行了 1 个回合）。

**建议优先级**: 高 - 此问题影响 MAS 核心功能，需要在下次发布前修复。

---

*报告生成时间: 2026-04-05*
*审计人员: Claude Code*
