# MAS Sub-stage max_turns 问题 - 代码审计报告

**审计日期**: 2026-04-06
**审计人员**: Claude Code
**相关Bug**: [bugs/BUG-002-substage-max-turns.md](../bugs/BUG-002-substage-max-turns.md)
**状态**: 已确认根因

---

## 问题现象

当 Tech Agent (tech1/tech2) 在 sub-stages (chat → coding → reflect) 之间转换时，`max_turns` 配置没有被正确执行。每个 sub-stage 维护自己的独立 turn 计数器，导致 Tech Agent 可以超出配置的 `max_turns` 限制。

## 根因分析

### 1. 设计意图 vs 实际实现

**配置设计** (`interview_crew/protocol/schemas.py`):

```python
class InterviewRoundConfig(BaseModel):
    max_turns: int = Field(default=4, description="Max turns for this agent (excluding sub-stages)")
    max_chat_turns: int = Field(default=2, description="Max turns in chat sub-stage")
    max_reflect_turns: int = Field(default=1, description="Max turns in reflect sub-stage")
```

注释明确说明 `max_turns` 是 "excluding sub-stages"，但实际语义模糊：
- 用户期望: `max_turns` 是该 agent 的总轮次限制（跨所有 sub-stages）
- 当前实现: `max_turns` 是**完整轮次**的数量（chat→coding→reflect→done 算一轮）

### 2. 代码流程分析

**文件**: `interview_crew/orchestrator/engine.py`

#### 2.1 Per-round turn 计数更新位置

```python
# Lines 180-185: 只在 sub_stage == "done" 后才更新 _round_turn_counts
if self.state.current_agent and self.state.current_agent in self._enabled_rounds:
    self._round_turn_counts[self.state.current_agent] = self._round_turn_counts.get(self.state.current_agent, 0) + 1
    self.state.round_turn_counts = self._round_turn_counts
```

**问题**: 这段代码只在 `sub_stage == "done"` 时执行（见 line 173-178），而一个完整的 Tech Agent 轮次包含多个 sub-stage turns。

#### 2.2 _next_agent() 逻辑

```python
# Lines 131-136: Tech Agent 只有在 sub_stage == "done" 且 turns < max_turns 时才继续
if self.state.current_agent in ["tech1", "tech2"]:
    if self.state.get_sub_stage(self.state.current_agent) != "done":
        return self.state.current_agent  # ← 不检查 max_turns!
    if current_round_turns < round_config.max_turns:
        return self.state.current_agent
```

**问题**: 当 `sub_stage != "done"` 时，直接返回当前 agent，**不检查** `max_turns` 限制。

#### 2.3 Sub-stage 内部计数器

```python
# Lines 320-331: _process_tech_agent_sub_stage()
self.state.increment_stage_turns(agent_name)  # 只增加 sub-stage 计数

# 检查是否 advance sub-stage
if sub_stage == "chat" and self.state.get_stage_turns(agent_name) >= round_config.max_chat_turns:
    self.state.advance_sub_stage(agent_name)  # ← 这会重置 stage_turns!
```

**问题**: `advance_sub_stage()` (state.py line 84-96) 会**重置** `stage_turns` 计数器：

```python
def advance_sub_stage(self, agent: str) -> str:
    # ...
    if idx < len(stages) - 1:
        next_stage = stages[idx + 1]
        self.set_sub_stage(agent, next_stage)
        setattr(self, f"{agent}_stage_turns", 0)  # ← 重置!
        return next_stage
```

### 3. 执行流程示例

配置: `max_turns=6, max_chat_turns=2, max_reflect_turns=1`

| 实际 Turn | Sub-stage | stage_turns | _round_turn_counts | 行为 |
|-----------|-----------|-------------|-------------------|------|
| 1 | chat | 1 | 0 | chat 继续 |
| 2 | chat | 2 | 0 | advance to coding, **重置 stage_turns=0** |
| 3 | coding | 1 | 0 | coding 继续（等待代码提交）|
| 4 | coding | 2 | 0 | coding 继续... |
| ... | ... | ... | ... | 可以无限停留在 coding |
| N | reflect | 1 | 0 | advance to done, **重置 stage_turns=0** |
| N+1 | chat | 1 | **1** | 终于更新 _round_turn_counts |

**问题**:
1. coding stage 可以无限停留（没有 turn 限制）
2. 只有完成所有 sub-stages 后 `_round_turn_counts` 才会增加
3. `max_turns` 实际上限制的是**完整轮次**的数量，而不是总 turns

### 4. 为什么 BUG-002 会发生

根据 bug 报告中的数据：
- `max_turns: 6`
- reflect stage 执行了 8 rounds (turn 8-15)

可能的原因：
1. coding stage 没有手动触发 advance，导致无限停留
2. 或者 reflect stage 的 `max_reflect_turns` 没有被正确检查

---

## 修复方案对比

### 方案 A: 保持当前设计，修复 enforcement

**当前设计**: `max_turns` = 完整轮次数量（chat→coding→reflect→done 算一轮）

**修复**:
1. 在 `_process_tech_agent_sub_stage()` 中添加 per-round turn 限制检查
2. 限制每个 sub-stage 的最大停留时间（特别是 coding）

**优点**: 向后兼容
**缺点**: 语义不够直观，用户可能误解

### 方案 B: 改为跨 sub-stage 累计 (用户期望)

**新设计**: `max_turns` = 该 agent 的总 turns（跨所有 sub-stages）

**修改**:
1. 新增 `tech_total_turns` 计数器（跨 sub-stages 累计）
2. `_next_agent()` 中检查累计 turns
3. 配置改为允许设置每个 sub-stage 的数量，max 做截断

**优点**: 符合用户直觉
**缺点**: 破坏性变更，需要更新测试

### 方案 C: 细化配置（推荐）

**新设计**:
```python
class InterviewRoundConfig(BaseModel):
    # 限制方式选择
    limit_mode: Literal["total", "per_stage", "hybrid"] = "hybrid"

    # 总限制（跨所有 sub-stages）
    max_turns: int = 6

    # 各 sub-stage 期望数量（仅做分配参考）
    stage_distribution: Dict[str, int] = {
        "chat": 2,
        "coding": 3,  # 包括生成题目和等待提交
        "reflect": 1
    }

    # 硬性截断（无论哪个 stage，达到即停止）
    max_per_stage: Dict[str, int] = {
        "chat": 3,
        "coding": 10,  # 防止无限等待
        "reflect": 2
    }
```

**执行逻辑**:
1. 优先按 `stage_distribution` 分配 turns
2. 任一 stage 达到 `max_per_stage` 硬性截断
3. 累计达到 `max_turns` 立即停止

**优点**:
- 灵活且符合用户期望
- 可以防止 coding stage 无限停留
- 向后兼容（默认 hybrid 模式）

---

## 建议实现

推荐**方案 C** 的简化版：

1. **添加 `max_coding_turns` 配置** - 防止 coding stage 无限停留
2. **添加 per-round 累计计数器** - 跨 sub-stages 统计
3. **在 `_process_tech_agent_sub_stage()` 中统一检查**:
   - 全局 `total_max_turns` (BUG-001 已修复)
   - per-agent 累计 `max_turns`
   - per-stage `max_*_turns`

### 具体修改

**Step 1**: 更新 `InterviewRoundConfig`
```python
class InterviewRoundConfig(BaseModel):
    max_turns: int = Field(default=4, description="Max total turns for this agent across all sub-stages")
    max_chat_turns: int = Field(default=2)
    max_coding_turns: int = Field(default=5, description="Max turns in coding sub-stage (prevents infinite wait)")
    max_reflect_turns: int = Field(default=1)
```

**Step 2**: 在 `InterviewState` 中添加累计计数器
```python
@dataclass
class InterviewState:
    # ... existing fields ...
    tech1_total_turns: int = 0  # 跨 sub-stages 累计
    tech2_total_turns: int = 0
```

**Step 3**: 在 `_process_tech_agent_sub_stage()` 中检查限制
```python
def _process_tech_agent_sub_stage(self, agent_name: str, candidate_response: str) -> StepResult:
    # Check global limit (BUG-001 fix)
    effective_max_turns = self._get_effective_max_turns()
    if self.state.turn >= effective_max_turns:
        ...

    # Check per-agent total limit (BUG-002 fix)
    round_config = self.state.config.get_round_config(agent_name)
    total_turns = getattr(self.state, f"{agent_name}_total_turns", 0)
    if total_turns >= round_config.max_turns:
        # Force advance to done
        self.state.set_sub_stage(agent_name, "done")
        return self._process_tech_agent_sub_stage(agent_name, candidate_response)

    # ... rest of processing ...

    # Increment counters
    self.state.increment_stage_turns(agent_name)
    setattr(self.state, f"{agent_name}_total_turns", total_turns + 1)
```

---

## 相关文件

- `interview_crew/orchestrator/engine.py` - 核心问题所在
- `interview_crew/protocol/schemas.py` - 配置定义
- `interview_crew/state.py` - 状态管理
- `bugs/BUG-002-substage-max-turns.md` - Bug 报告

---

## 结论

**根因确认**:
1. `max_turns` 语义不明确（完整轮次 vs 总 turns）
2. coding stage 缺乏 turn 限制，可无限停留
3. sub-stage 计数器重置导致无法控制总 turns

**修复优先级**: 中 (P2) - 影响 MAS 模式公平性和成本，但 BUG-001 的 `total_max_turns` 可作为临时兜底

**推荐方案**: 细化配置，允许设置各 sub-stage 数量，max 参数做截断处理

---

*Report generated by Claude Code on 2026-04-06*
