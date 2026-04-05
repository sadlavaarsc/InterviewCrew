# MAS 状态切换 Bug 代码审计报告

**审计日期**: 2026-04-05
**审计对象**: `interview_crew/orchestrator/engine.py`, `interview_crew/api.py`, `interview_crew/state.py`
**问题描述**: MAS 模式 Agent 状态切换失效，面试流程卡在单个 Agent 阶段无法推进
**严重程度**: 高（阻塞性 Bug）
**代码版本**: aa00709

---

## 1. 执行摘要

经代码审计，确认 MAS 存在**多重叠加的状态切换逻辑缺陷**。核心问题是 `Orchestrator._next_agent()` 方法在 Tech Agent 的 sub_stage 完成（`== "done"`）时，**完全绕过 `max_turns` 轮次限制检查**，直接递增 `_current_round_index` 并切换到下一个 Agent。这导致：

1. Tech Agent 配置的 `max_turns` 被完全忽略，每个 Tech Agent 仅执行 **1 个主轮次**（而非配置的 4 轮）就被强制切换
2. `_round_turn_counts` 和 `_current_round_index` 作为**非持久化实例变量**，在会话恢复时状态丢失，引发不可预期的行为
3. Transfer Queue 中累积大量"转移请求"但从未真正执行，形成"幽灵队列"

**根本原因**: `engine.py:106-146` 的 `_next_agent()` 方法中，sub_stage `== "done"` 分支与 `max_turns` 检查分支是**互斥路径**，永远不会同时执行。

---

## 2. 问题详细分析

### 2.1 核心 Bug：`_next_agent()` 方法逻辑缺陷（engine.py:106-146）

```python
def _next_agent(self) -> str:
    if self.state.conflict_flag:
        self.state.conflict_flag = False
        if "tech2" in self._enabled_rounds:
            return "tech2"

    if self.state.current_agent and self.state.current_agent in self._enabled_rounds:
        if self.state.current_agent in ["tech1", "tech2"]:
            if self.state.get_sub_stage(self.state.current_agent) == "done":
                pass  # Will advance below          ← ⚠️ Bug 核心：直接 pass，不检查 max_turns
            else:
                round_config = self.state.config.get_round_config(self.state.current_agent)
                current_round_turns = self._round_turn_counts.get(self.state.current_agent, 0)
                if current_round_turns < round_config.max_turns:  ← 仅当 sub_stage != "done" 时检查
                    return self.state.current_agent
        else:
            round_config = self.state.config.get_round_config(self.state.current_agent)
            current_round_turns = self._round_turn_counts.get(self.state.current_agent, 0)
            if current_round_turns < round_config.max_turns:
                return self.state.current_agent

    # Advance to next round
    if self._current_round_index >= len(self._enabled_rounds):
        return "scribe"

    next_agent = self._enabled_rounds[self._current_round_index]
    self._current_round_index += 1  ← 每次 sub_stage=="done" 都递增，无视 max_turns
    return next_agent
```

#### 问题分析

| 场景 | 实际行为 | 预期行为 |
|------|----------|----------|
| tech1 sub_stage="chat"，已执行 1 轮 | 继续 tech1 | ✅ 正确 |
| tech1 sub_stage="done"，已执行 1 轮（max_turns=4）| **切换到 tech2** | ❌ 应继续 tech1，还有 3 轮 |
| tech1 sub_stage="done"，已执行 4 轮（max_turns=4）| 切换到 tech2 | ✅ 正确，但纯属巧合 |

**关键结论**: `max_turns` 配置对 Tech Agent 完全失效。无论配置多少轮，Tech Agent 永远只执行 **1 个 sub_stage 周期**（chat→coding→reflect）就被切换。

### 2.2 计数器系统崩溃：双轨制计数器互不交汇

```python
# engine.py:180-181
if self.state.current_agent and self.state.current_agent in self._enabled_rounds:
    self._round_turn_counts[self.state.current_agent] = \
        self._round_turn_counts.get(self.state.current_agent, 0) + 1
```

```python
# engine.py:306-317（在 _process_tech_agent_sub_stage 中）
self.state.increment_stage_turns(agent_name)  # 子阶段计数器

if sub_stage == "chat" and self.state.get_stage_turns(agent_name) >= round_config.max_chat_turns:
    self.state.advance_sub_stage(agent_name)    # 推进子阶段
```

| 计数器 | 用途 | 更新时机 | 持久化 |
|--------|------|----------|--------|
| `_round_turn_counts` | 控制主轮次切换 | 仅在 sub_stage=="done" 时 | ❌ 否 |
| `tech1_stage_turns` | 控制子阶段推进 | 每次 sub-stage step | ✅ 是（state 中） |

**问题**:
1. `_round_turn_counts` 和子阶段计数器是**完全独立**的系统
2. `_round_turn_counts` 只在 `sub_stage=="done"` 的 step 中更新，而 `max_turns` 检查只在 `sub_stage!="done"` 时执行
3. 两个条件**永不同时满足**，因此 `_round_turn_counts` 的递增与 `max_turns` 的检查永远发生在不同的 step 中

### 2.3 非持久化状态：会话恢复导致状态丢失

```python
# engine.py:66
self._round_turn_counts: Dict[str, int] = {}

# engine.py:63
self._current_round_index = self._get_current_round_index()
```

这两个变量是 `Orchestrator` 的**实例变量**，不是 `InterviewState` 的一部分。当：
- API 服务器重启
- 会话被序列化后反序列化
- 任何需要重建 Orchestrator 实例的场景

这些计数器会被**重置为初始值**，导致：
- `_round_turn_counts` 归零 → Tech Agent 可以无限重复
- `_current_round_index` 被重新计算 → 可能指向错误位置

### 2.4 Transfer Queue 幽灵累积

```python
# engine.py:325-337
pkg = TransferPackage(
    session_id=self.state.session_id,
    from_agent=agent_name,
    to_agent=self._peek_next_agent(agent_name),  # 永远是下一个 Agent
    ...
)
self.state.transfer_queue.append(pkg)
```

`_peek_next_agent("tech1")` 始终返回 "tech2"，即使在当前 Tech Agent 还有剩余轮次时也是如此。

**测试报告现象**: "Transfer Queue 已累积 10 条转移到 tech2 的请求" —— 这是因为每次调用 `_process_tech_agent_sub_stage()` 都会添加一条指向 tech2 的 TransferPackage，但实际的 Agent 切换由 `_next_agent()` 控制，两者不同步。

### 2.5 API 层配置歧义（api.py:238）

```python
effective_total_turns = req.total_max_turns if req.total_max_turns != 30 else req.max_turns
```

| 用户输入 | effective_total_turns | 用户预期 | 是否符合预期 |
|----------|----------------------|----------|-------------|
| 不设置（默认 30） | 6（max_turns 默认值） | 30 | ❌ |
| total_max_turns=15 | 15 | 15 | ✅ |
| total_max_turns=30 | 6 | 30 | ❌ |

当用户显式设置 `total_max_turns=30` 时，会**回退**到 `max_turns=6`，这与直觉相反。

### 2.6 `__init__` 初始化逻辑与 `_get_current_round_index()` 冲突

```python
# engine.py:79-86
def _get_current_round_index(self) -> int:
    if not self.state.current_agent:
        return 0
    if self.state.current_agent in self._enabled_rounds:
        return self._enabled_rounds.index(self.state.current_agent)
    return len(self._enabled_rounds)

# engine.py:70-75
if self.state.current_agent in ["tech1", "tech2"]:
    if self.state.get_sub_stage(self.state.current_agent) == "done":
        self._current_round_index += 1
```

如果会话恢复时 `current_agent="tech1"` 且 `sub_stage="done"`：
- `_get_current_round_index()` 返回 0
- `__init__` 中递增到 1
- 但之前的会话可能已经将 `_current_round_index` 递增到更高值
- 由于非持久化，这个信息丢失，导致索引计算错误

---

## 3. Bug 执行流程演示

### 配置
```python
rounds_config = {
    "tech1": {"enabled": true, "max_turns": 4, "max_chat_turns": 2, "max_reflect_turns": 1},
    "tech2": {"enabled": true, "max_turns": 4, ...},
    "sysdes": {"enabled": true, "max_turns": 3, ...},
    "leader": {"enabled": true, "max_turns": 2, ...},
    "hr": {"enabled": true, "max_turns": 2, ...}
}
total_max_turns = 15
```

### 实际执行流程

| Step | turn | Agent | sub_stage | _round_turns[tech1] | _current_idx | 动作 | 问题 |
|------|------|-------|-----------|---------------------|--------------|------|------|
| Init | 0 | "" | - | {} | 0 | - | - |
| 1 | 1 | tech1 | chat | - | 1 | 初始化 | - |
| 2 | 2 | tech1 | chat | - | 1 | chat 阶段 1 | - |
| 3 | 3 | tech1 | coding | - | 1 | advance 到 coding | - |
| 4 | 4 | tech1 | reflect | - | 1 | submit-code 后 advance | - |
| 5 | 5 | tech1 | **done** | **1** | **2** | ⚠️ 直接切换到 tech2 | **Bug: 无视 max_turns=4** |
| 6-9 | 6-9 | tech2 | ... | - | 3 | 同样只执行 1 轮 | Bug 重复 |
| 10 | 10 | sysdes | - | - | 4 | 执行 1 轮 | Bug 重复 |
| 11 | 11 | leader | - | - | 5 | 执行 1 轮 | Bug 重复 |
| 12 | 12 | hr | - | - | 6 | 执行 1 轮后返回 scribe | - |

**实际结果**: 12 步后面试终止，每个 Agent 只执行了 1 轮（而非配置的多轮）。

**预期结果**: tech1 应执行 4 个完整周期（约 20+ step），然后才切换到 tech2。

---

## 4. 与测试报告现象的对应

| 测试报告现象 | 对应 Bug |
|-------------|----------|
| "卡在 tech1 阶段" | Bug 1 + Bug 3：Agent 切换逻辑混乱，可能因非持久化计数器导致索引计算错误 |
| "Transfer Queue 已累积 10 条转移到 tech2 的请求" | Bug 4：`_peek_next_agent()` 始终返回下一个 Agent，与实际切换逻辑不同步 |
| "Current Agent 仍卡在 tech1" | Bug 2 + Bug 6：计数器重置后 `_current_round_index` 被错误计算 |
| "tech1 Agent 重复提问，未执行交接" | Bug 1：sub_stage 完成时本应根据 max_turns 决定是否继续，但逻辑直接 pass |
| "完成 10 轮后仍未切换" | 综合：10 轮可能只完成了 tech1 的 2 个 sub_stage 周期，但切换逻辑异常导致无法推进 |

---

## 5. 问题影响评估

### 5.1 功能影响

- **面试不完整**: 每个 Tech Agent 仅执行 1 轮，深度追问能力完全丧失
- **配置失效**: `rounds_config.max_turns` 对 Tech Agent 完全无效
- **评估失真**: Scribe 基于不完整的多 Agent 数据生成报告
- **会话不可恢复**: 非持久化计数器导致会话恢复后行为不可预测

### 5.2 影响范围

| 配置场景 | 是否受影响 | 说明 |
|----------|-----------|------|
| 使用默认配置 | ✅ 是 | 默认配置下 Tech Agent 各 4 轮，实际只执行 1 轮 |
| 使用自定义 `rounds_config` | ✅ 是 | `max_turns` 对 Tech Agent 无效 |
| 仅使用非 Tech Agent | ⚠️ 部分 | sysdes/leader/hr 的 max_turns 检查正常 |
| 单 Agent Baseline | ❌ 否 | SAS 使用独立的 `SingleAgentOrchestrator` |

---

## 6. 代码定位

### 主要问题文件

```
interview_crew/orchestrator/engine.py
  ├── Line 62-63: _enabled_rounds, _current_round_index 初始化
  ├── Line 66: _round_turn_counts 声明（非持久化）
  ├── Line 70-75: __init__ 中 _current_round_index 额外递增
  ├── Line 106-146: _next_agent() - 核心 Bug 位置
  ├── Line 148-199: step() - 调用时序问题
  ├── Line 180-181: _round_turn_counts 更新位置
  └── Line 325-337: TransferPackage 构建（to_agent 始终为下一个）

interview_crew/api.py
  └── Line 238: effective_total_turns 计算逻辑歧义

interview_crew/state.py
  └── Line 120-123: reset_agent_stage() - 重置后未同步 _round_turn_counts
```

---

## 7. 修复建议（仅参考，不实施）

### 方案 A：修复 `_next_agent()` 的 max_turns 检查逻辑（推荐）

重构 `_next_agent()`，使 sub_stage 完成时也检查 `_round_turn_counts`：

```python
def _next_agent(self) -> str:
    if self.state.conflict_flag:
        self.state.conflict_flag = False
        if "tech2" in self._enabled_rounds:
            return "tech2"

    if self.state.current_agent and self.state.current_agent in self._enabled_rounds:
        round_config = self.state.config.get_round_config(self.state.current_agent)
        current_round_turns = self._round_turn_counts.get(self.state.current_agent, 0)

        # Tech Agent: 只有 sub_stage 完成且轮次耗尽时才切换
        if self.state.current_agent in ["tech1", "tech2"]:
            if self.state.get_sub_stage(self.state.current_agent) != "done":
                return self.state.current_agent  # 子阶段未完成，继续当前 Agent
            # sub_stage 已完成，检查是否还有剩余轮次
            if current_round_turns < round_config.max_turns:
                return self.state.current_agent  # 还有剩余轮次，继续当前 Agent
        else:
            # 非 Tech Agent: 仅检查轮次限制
            if current_round_turns < round_config.max_turns:
                return self.state.current_agent

    # 切换到下一轮
    if self._current_round_index >= len(self._enabled_rounds):
        return "scribe"

    next_agent = self._enabled_rounds[self._current_round_index]
    self._current_round_index += 1
    return next_agent
```

### 方案 B：将计数器持久化到 InterviewState

```python
# state.py 中添加持久化字段
tech1_round_turns: int = 0
tech2_round_turns: int = 0
sysdes_round_turns: int = 0
leader_round_turns: int = 0
hr_round_turns: int = 0
current_round_index: int = 0
```

### 方案 C：统一轮次计算模型

移除 `_round_turn_counts` 和 `_current_round_index`，改为基于 `state.turn` 和配置动态计算：

```python
def _get_current_agent_by_turn(self) -> str:
    """基于全局回合数和配置动态计算当前 Agent"""
    cumulative_turns = 0
    for agent_name in self._enabled_rounds:
        config = self.state.config.get_round_config(agent_name)
        # Tech Agent 的回合数 = max_turns * (max_chat_turns + 1 + max_reflect_turns)
        if agent_name in ["tech1", "tech2"]:
            agent_total_turns = config.max_turns * (config.max_chat_turns + 1 + config.max_reflect_turns)
        else:
            agent_total_turns = config.max_turns
        cumulative_turns += agent_total_turns
        if self.state.turn <= cumulative_turns:
            return agent_name
    return "scribe"
```

### 方案 D：修复 TransferPackage 的 to_agent 逻辑

```python
def _peek_next_agent(self, current: str) -> str:
    """根据当前轮次状态决定下一个 Agent"""
    if current == "scribe":
        return "scribe"

    # 检查当前 Agent 是否还有剩余轮次
    if current in self._enabled_rounds:
        round_config = self.state.config.get_round_config(current)
        current_round_turns = self._round_turn_counts.get(current, 0)
        if current_round_turns < round_config.max_turns:
            return current  # 还有剩余轮次，下一个还是自己

        idx = self._enabled_rounds.index(current)
        if idx + 1 < len(self._enabled_rounds):
            return self._enabled_rounds[idx + 1]

    return "scribe"
```

---

## 8. 验证建议

### 单元测试

```python
def test_tech_agent_respects_max_turns():
    """验证 Tech Agent 执行配置的 max_turns 轮次后才切换"""
    config = InterviewConfig(
        total_max_turns=30,
        rounds={
            "tech1": InterviewRoundConfig(max_turns=4, max_chat_turns=1, max_reflect_turns=1),
            "tech2": InterviewRoundConfig(enabled=False),
        }
    )
    state = InterviewState(session_id="test", config=config)
    orchestrator = Orchestrator(state)

    # 模拟完成 4 个完整周期
    for cycle in range(4):
        # chat 阶段
        orchestrator.step("response")
        # coding 阶段（模拟 submit-code）
        orchestrator.state.advance_sub_stage("tech1")
        orchestrator.step("response")
        # reflect 阶段
        orchestrator.state.advance_sub_stage("tech1")
        result = orchestrator.step("response")

    # 第 4 个周期完成后，应该切换到 scribe（没有 tech2）
    assert result.agent == "scribe" or orchestrator.state.current_agent != "tech1"
```

### 集成测试

1. 使用 API 创建 15 轮配置的会话
2. 模拟候选人回复，记录每个 step 的 Agent 变化
3. 验证 tech1 是否执行了 4 个完整周期后才切换

### 日志增强

在关键位置添加调试日志：
- `_next_agent()` 入口/出口：记录 `_current_round_index`、`_round_turn_counts`、返回值
- `step()` 中：记录 sub_stage 状态、Agent 切换原因
- `__init__` 中：记录 `_current_round_index` 的初始计算值

---

## 9. 结论

MAS 状态切换 Bug 是由**多个相互关联的设计缺陷**共同导致的：

1. **核心缺陷**: `_next_agent()` 在 sub_stage=="done" 时绕过 `max_turns` 检查，导致 Tech Agent 轮次配置失效
2. **架构缺陷**: 关键计数器（`_round_turn_counts`, `_current_round_index`）未持久化，会话恢复时状态丢失
3. **设计缺陷**: TransferPackage 构建逻辑与 Agent 切换逻辑不同步，产生"幽灵队列"
4. **配置缺陷**: API 层的 `total_max_turns` 计算逻辑存在歧义

**建议优先级**: **P0** - 此问题完全阻塞 MAS 核心功能，必须在下次发布前修复。

---

*报告生成时间: 2026-04-05*
*审计人员: Claude Code (Kimi-k2.5)*
*代码版本: aa00709*
