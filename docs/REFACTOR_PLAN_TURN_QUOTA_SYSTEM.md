# MAS 核心状态机重构完整方案

> 目标：根治 turn 限制相关的反复 bug，实施统一的配额制 (Quota System)
> 创建时间：2026-04-06
> 状态：✅ 已完成

---

## 一、问题背景

### 1.1 反复出现的 Bug

| Bug | 现象 | 根因 |
|-----|------|------|
| BUG-001 | `total_max_turns` 在 sub-stage 处理时未生效 | 限制检查分散在多处，sub-stage 路径绕过检查 |
| BUG-002 | `max_turns` 在 sub-stage 转换时未正确累计 | per-round 计数器只在 sub_stage=done 时更新 |
| 经典问题 | 修好了切换，破坏了截断；修好了截断，又不切换 | 条件判断错综复杂，互相耦合 |

### 1.2 现有架构的问题

```
混乱的 turn 计数器:
├── state.turn          - 全局计数器（每次 step 递增）
├── _round_turn_counts  - per-round 计数器（只在 sub_stage=done 更新）
├── stage_turns         - per-sub-stage 计数器（随时重置）
└── 分散的限制检查:
    ├── step() 开头检查 total_max_turns
    ├── _next_agent() 检查 max_turns（但 Tech Agent 特殊处理）
    ├── _process_tech_agent_sub_stage() 检查 max_*_turns
    └── step() 末尾再次检查 total_max_turns
```

---

## 二、重构方案：统一配额制 (Quota System)

### 2.1 核心思想

分层状态机 + 统一配额管理：

```
┌─────────────────────────────────────────────────────────────────┐
│                     对外接口层 (保持不变)                          │
│  Orchestrator.step() → StepResult                               │
│  Orchestrator._next_agent()                                     │
│  state.turn, state.current_agent, state.status                  │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                     配额管理层 (新增)                              │
│  TurnQuotaManager                                               │
│  ├── 统一消费配额 (global/agent/sub-stage)                        │
│  ├── 提供限制检查 (should_continue)                              │
│  └── 触发状态转换 (quota_exhausted)                              │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                     状态执行层 (简化)                              │
│  _execute_turn()                                                │
│  ├── _process_tech_agent()                                      │
│  └── _process_standard_agent()                                  │
│  (不再关心限制检查，只执行业务逻辑)                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 配额层级设计

```
┌─────────────────────────────────────────────────────────────┐
│  Quota Level 1: Global                                      │
│  ├── total_max_turns (默认 30)                              │
│  └── 耗尽动作: FINISH (结束面试)                             │
├─────────────────────────────────────────────────────────────┤
│  Quota Level 2: Agent                                       │
│  ├── max_turns (默认 4)                                     │
│  └── 语义: 该 agent 的总 turns（跨所有 sub-stages）           │
│  └── 耗尽动作: SWITCH_AGENT (切换到下一个 agent)              │
├─────────────────────────────────────────────────────────────┤
│  Quota Level 3: Sub-Stage                                   │
│  ├── max_chat_turns (默认 2)                                │
│  ├── max_coding_turns (默认 10, 新增)                       │
│  ├── max_reflect_turns (默认 1)                             │
│  └── 耗尽动作: ADVANCE_STAGE (推进到下一个 sub-stage)         │
└─────────────────────────────────────────────────────────────┘
```

**配额消费顺序**: 先检查所有层级，再统一消费（确保原子性）

---

## 三、详细设计

### 3.1 新增 Quota 模块

**文件**: `interview_crew/orchestrator/quota.py`

```python
"""
统一的 Turn 配额管理系统

设计原则:
1. 单一职责: 所有限制逻辑在此集中
2. 不可绕过: 无论走哪个代码路径，配额都会被消费和检查
3. 向后兼容: 支持现有的 InterviewConfig 配置格式

配额层级 (从高到低):
- global: total_max_turns (全局总限制)
- agent: max_turns (每个 agent 的总限制，跨 sub-stages)
- stage: max_chat/coding/reflect_turns (每个 sub-stage 的限制)

消费顺序:
1. 检查所有层级是否还有配额
2. 从低到高消费 (stage -> agent -> global)
3. 任一层级耗尽触发相应动作
"""

from dataclasses import dataclass, field
from typing import Dict, Optional, Literal
from enum import Enum


class QuotaLevel(Enum):
    """配额层级"""
    GLOBAL = "global"
    AGENT = "agent"
    STAGE = "stage"


class QuotaAction(Enum):
    """配额耗尽时的动作"""
    CONTINUE = "continue"      # 继续执行
    ADVANCE_STAGE = "advance"  # 推进到下一个 sub-stage
    SWITCH_AGENT = "switch"    # 切换到下一个 agent
    FINISH = "finish"          # 结束面试


@dataclass
class QuotaCheckResult:
    """配额检查结果"""
    can_continue: bool
    exhausted_level: Optional[QuotaLevel] = None
    action: QuotaAction = QuotaAction.CONTINUE
    reason: str = ""


class TurnQuotaManager:
    """
    Turn 配额管理器

    使用示例:
        quota = TurnQuotaManager(config, state)

        # 在 step() 开始时检查
        result = quota.check_and_consume("tech1", "chat")
        if not result.can_continue:
            return self._handle_quota_exhausted(result)
    """

    def __init__(self, config: InterviewConfig, state: InterviewState):
        self.config = config
        self.state = state

        # 初始化剩余配额
        self._remaining_global = config.total_max_turns
        self._remaining_agent: Dict[str, int] = {}
        self._remaining_stage: Dict[str, int] = {}

        # 从 state 恢复配额（支持会话恢复）
        self._restore_from_state()

    def _restore_from_state(self):
        """从 state 恢复配额（用于会话恢复）"""
        # 根据已执行的 turns 调整剩余配额
        self._remaining_global = max(0, self.config.total_max_turns - self.state.turn)

        # 恢复 agent 配额
        if hasattr(self.state, 'quota_consumed_agent'):
            for agent, consumed in self.state.quota_consumed_agent.items():
                cfg = self.config.get_round_config(agent)
                self._remaining_agent[agent] = max(0, cfg.max_turns - consumed)

    def check(self, agent: str, sub_stage: Optional[str] = None) -> QuotaCheckResult:
        """
        检查配额（不消费）

        Returns:
            QuotaCheckResult: 检查结果和建议动作
        """
        # 检查全局配额
        if self._remaining_global <= 0:
            return QuotaCheckResult(
                can_continue=False,
                exhausted_level=QuotaLevel.GLOBAL,
                action=QuotaAction.FINISH,
                reason=f"Global limit reached: {self.config.total_max_turns}"
            )

        # 检查 agent 配额
        remaining_agent = self._get_remaining_agent(agent)
        if remaining_agent <= 0:
            return QuotaCheckResult(
                can_continue=False,
                exhausted_level=QuotaLevel.AGENT,
                action=QuotaAction.SWITCH_AGENT,
                reason=f"Agent {agent} limit reached"
            )

        # 检查 sub-stage 配额
        if sub_stage:
            remaining_stage = self._get_remaining_stage(agent, sub_stage)
            if remaining_stage <= 0:
                return QuotaCheckResult(
                    can_continue=False,
                    exhausted_level=QuotaLevel.STAGE,
                    action=QuotaAction.ADVANCE_STAGE,
                    reason=f"Stage {agent}:{sub_stage} limit reached"
                )

        return QuotaCheckResult(can_continue=True)

    def consume(self, agent: str, sub_stage: Optional[str] = None) -> QuotaCheckResult:
        """
        消费配额并返回结果

        注意: 即使 can_continue=False，也会消费配额（保证计数准确）
        """
        result = self.check(agent, sub_stage)

        # 消费配额（从高到低）
        self._remaining_global = max(0, self._remaining_global - 1)

        if agent not in self._remaining_agent:
            self._remaining_agent[agent] = self._get_agent_limit(agent)
        self._remaining_agent[agent] = max(0, self._remaining_agent[agent] - 1)

        if sub_stage:
            stage_key = f"{agent}:{sub_stage}"
            if stage_key not in self._remaining_stage:
                self._remaining_stage[stage_key] = self._get_stage_limit(agent, sub_stage)
            self._remaining_stage[stage_key] = max(0, self._remaining_stage[stage_key] - 1)

        # 持久化到 state
        self._persist_to_state()

        return result

    def check_and_consume(self, agent: str, sub_stage: Optional[str] = None) -> QuotaCheckResult:
        """检查并消费配额的便捷方法"""
        return self.consume(agent, sub_stage)

    def get_remaining(self, agent: str, sub_stage: Optional[str] = None) -> Dict[str, int]:
        """获取各层级剩余配额（用于调试）"""
        result = {
            "global": self._remaining_global,
            "agent": self._get_remaining_agent(agent)
        }
        if sub_stage:
            result["stage"] = self._get_remaining_stage(agent, sub_stage)
        return result

    def _get_remaining_agent(self, agent: str) -> int:
        """获取 agent 剩余配额"""
        if agent not in self._remaining_agent:
            self._remaining_agent[agent] = self._get_agent_limit(agent)
        return self._remaining_agent[agent]

    def _get_remaining_stage(self, agent: str, sub_stage: str) -> int:
        """获取 sub-stage 剩余配额"""
        stage_key = f"{agent}:{sub_stage}"
        if stage_key not in self._remaining_stage:
            self._remaining_stage[stage_key] = self._get_stage_limit(agent, sub_stage)
        return self._remaining_stage[stage_key]

    def _get_agent_limit(self, agent: str) -> int:
        """获取 agent 配额上限"""
        cfg = self.config.get_round_config(agent)
        return cfg.max_turns if cfg else 4  # 默认 4

    def _get_stage_limit(self, agent: str, sub_stage: str) -> int:
        """获取 sub-stage 配额上限"""
        cfg = self.config.get_round_config(agent)
        if not cfg:
            return 2

        limit_map = {
            "chat": cfg.max_chat_turns,
            "coding": getattr(cfg, 'max_coding_turns', 10),  # 新增，防止无限等待
            "reflect": cfg.max_reflect_turns
        }
        return limit_map.get(sub_stage, 2)

    def _persist_to_state(self):
        """持久化配额状态到 InterviewState（支持会话恢复）"""
        # 使用新的字段存储配额消耗情况
        if not hasattr(self.state, 'quota_consumed_agent'):
            self.state.quota_consumed_agent = {}

        for agent in self._remaining_agent:
            limit = self._get_agent_limit(agent)
            self.state.quota_consumed_agent[agent] = limit - self._remaining_agent[agent]
```

### 3.2 配置更新

**文件**: `interview_crew/protocol/schemas.py`

```python
class InterviewRoundConfig(BaseModel):
    """
    更新后的配置

    关键变化:
    - max_turns 语义变为"该 agent 的总 turns（跨所有 sub-stages）"
    - 新增 max_coding_turns 防止 coding 无限等待
    """
    enabled: bool = Field(default=True)
    max_turns: int = Field(
        default=6,  # 增加默认值，适应新的语义
        ge=1,
        le=30,
        description="该 agent 的总 turns（跨所有 sub-stages）"
    )

    # Sub-stage 限制（达到即截断）
    max_chat_turns: int = Field(default=2, ge=1, le=10)
    max_coding_turns: int = Field(
        default=5,
        ge=1,
        le=20,
        description="coding sub-stage 最大 turns，防止无限等待"
    )
    max_reflect_turns: int = Field(default=1, ge=1, le=5)
```

### 3.3 State 更新

**文件**: `interview_crew/state.py`

```python
@dataclass
class InterviewState:
    # ... 现有字段 ...

    # 配额持久化（新增，用于会话恢复）
    quota_consumed_agent: Dict[str, int] = field(default_factory=dict)
    """记录每个 agent 已消费的配额"""
```

### 3.4 Engine 重构

**文件**: `interview_crew/orchestrator/engine.py`

#### 3.4.1 初始化更新

```python
class Orchestrator:
    def __init__(self, state: InterviewState, jd_parser: Optional[JDParsingStrategy] = None):
        # ... 现有初始化 ...

        # 新增: 配额管理器
        self._quota = TurnQuotaManager(self.state.config, self.state)
```

#### 3.4.2 重写 step() 方法

```python
def step(self, candidate_response: str) -> StepResult:
    """
    简化的 step 方法 - 统一配额检查入口

    核心原则:
    1. 单一入口: 所有 turn 都经过这里
    2. 统一配额检查: 不分散在各分支
    3. 清晰分流: 根据配额结果决定动作
    """
    self.state.candidate_response = candidate_response

    # 1. 确定当前状态
    current_agent = self.state.current_agent
    sub_stage = self._get_current_sub_stage(current_agent)

    # 2. 统一配额检查 (核心！)
    quota_result = self._quota.check_and_consume(current_agent, sub_stage)

    # 3. 记录 turn（在配额消费之后）
    self.state.turn += 1
    if candidate_response:
        self.state.append_unified({"role": "user", "content": candidate_response})

    # 4. 根据配额结果执行动作
    if not quota_result.can_continue:
        return self._handle_quota_exhausted(quota_result, candidate_response)

    # 5. 执行正常 turn
    return self._execute_turn(current_agent, sub_stage, candidate_response)

def _get_current_sub_stage(self, agent: str) -> Optional[str]:
    """获取当前 sub-stage（如果有）"""
    if agent not in ["tech1", "tech2"]:
        return None
    return self.state.get_sub_stage(agent)

def _handle_quota_exhausted(
    self,
    result: QuotaCheckResult,
    candidate_response: str
) -> StepResult:
    """统一处理配额耗尽情况"""
    if result.action == QuotaAction.FINISH:
        self.state.status = "finished"
        report = self._generate_report()
        return StepResult(agent="scribe", question="", finished=True, report=report)

    elif result.action == QuotaAction.SWITCH_AGENT:
        # Agent 配额耗尽，切换到下一个
        self._current_round_index += 1
        next_agent = self._get_next_enabled_agent()
        if next_agent == "scribe":
            self.state.status = "finished"
            report = self._generate_report()
            return StepResult(agent="scribe", question="", finished=True, report=report)

        self.state.current_agent = next_agent
        return self._execute_turn(next_agent, None, candidate_response)

    elif result.action == QuotaAction.ADVANCE_STAGE:
        # Sub-stage 配额耗尽，推进到下一个
        agent = self.state.current_agent
        self.state.advance_sub_stage(agent)

        # 推进后如果是 done，进入正常切换逻辑
        if self.state.get_sub_stage(agent) == "done":
            return self._handle_agent_round_complete(agent, candidate_response)

        # 否则继续执行新的 sub-stage
        new_stage = self._get_current_sub_stage(agent)
        return self._execute_turn(agent, new_stage, candidate_response)

    else:
        raise RuntimeError(f"Unknown quota action: {result.action}")

def _handle_agent_round_complete(self, agent: str, candidate_response: str) -> StepResult:
    """处理 agent 完成一轮（sub_stage == done）"""
    # 增加 per-round 计数（用于向后兼容）
    if agent in self._enabled_rounds:
        self._round_turn_counts[agent] = self._round_turn_counts.get(agent, 0) + 1
        self.state.round_turn_counts = self._round_turn_counts

    # 检查是否还有配额继续该 agent 的下一轮
    remaining = self._quota.get_remaining(agent)
    if remaining.get("agent", 0) > 0:
        # 继续该 agent 的下一轮
        self.state.reset_agent_stage(agent)
        new_stage = self._get_current_sub_stage(agent)
        return self._execute_turn(agent, new_stage, candidate_response)
    else:
        # 切换到下一个 agent
        return self._handle_quota_exhausted(
            QuotaCheckResult(
                can_continue=False,
                exhausted_level=QuotaLevel.AGENT,
                action=QuotaAction.SWITCH_AGENT,
                reason=f"Agent {agent} completed round but quota exhausted"
            ),
            candidate_response
        )

def _execute_turn(
    self,
    agent: str,
    sub_stage: Optional[str],
    candidate_response: str
) -> StepResult:
    """执行实际的 turn（无限制检查，只执行业务逻辑）"""
    if agent in ["tech1", "tech2"] and sub_stage and sub_stage != "done":
        return self._process_tech_agent_sub_stage(agent, candidate_response)
    elif agent == "scribe":
        return self._finish_interview()
    else:
        return self._process_standard_agent(agent, candidate_response)

def _get_next_enabled_agent(self) -> str:
    """获取下一个启用的 agent"""
    if self._current_round_index >= len(self._enabled_rounds):
        return "scribe"
    return self._enabled_rounds[self._current_round_index]
```

#### 3.4.3 简化 _next_agent()

```python
def _next_agent(self) -> str:
    """
    简化的 _next_agent

    注意: 现在限制检查主要在 quota 中处理，这里只做简单的状态判断
    """
    if self.state.conflict_flag:
        self.state.conflict_flag = False
        if "tech2" in self._enabled_rounds:
            return "tech2"

    # 如果没有当前 agent（初始状态），返回第一个启用的 agent
    if not self.state.current_agent:
        if self._enabled_rounds:
            return self._enabled_rounds[0]
        return "scribe"

    # 如果当前 agent 有 sub-stages 且未完成，继续
    if self.state.current_agent in ["tech1", "tech2"]:
        if self.state.get_sub_stage(self.state.current_agent) != "done":
            return self.state.current_agent

    # 使用配额系统决定下一步
    remaining = self._quota.get_remaining(self.state.current_agent)
    if remaining.get("agent", 0) > 0:
        return self.state.current_agent

    # 配额耗尽，切换到下一个
    return self._get_next_enabled_agent()
```

#### 3.4.4 移除 _process_tech_agent_sub_stage() 中的限制检查

```python
def _process_tech_agent_sub_stage(self, agent_name: str, candidate_response: str) -> StepResult:
    """
    处理 Tech Agent sub-stage

    注意: 不再检查限制！限制检查统一在 step() 中处理
    """
    # 移除: 全局 turn limit 检查（已在 step() 中处理）

    agent = self.agents[agent_name]
    sub_stage = self.state.get_sub_stage(agent_name)

    # ... 执行业务逻辑 ...

    # 移除: max_chat_turns/max_reflect_turns 检查（已在 quota 中处理）
    # 只处理业务逻辑：生成问题、更新历史等

    # 注意: 不在这里检查 should advance，只记录状态
    # advance 逻辑由 quota 触发

    return StepResult(agent=agent_name, question=output.question, finished=False)
```

---

## 四、实施步骤

### Phase 1: 创建 Quota 模块（不修改现有代码）

**目标**: 创建并测试 quota.py

```bash
# 1. 创建文件
touch interview_crew/orchestrator/quota.py

# 2. 编写实现（见上文）

# 3. 添加单元测试
touch tests/test_quota.py
```

**测试重点**:
- 配额消费顺序正确
- 层级检查逻辑正确
- 状态持久化/恢复正确

### Phase 2: 更新配置和状态

**目标**: 添加新字段，保持向后兼容

```python
# schemas.py - 添加 max_coding_turns
# state.py - 添加 quota_consumed_agent
```

### Phase 3: 重构 engine.py（核心）

**目标**: 引入 QuotaManager，重写 step()

**风险点**:
- 确保 TransferPackage 创建不变
- 确保消息传递流程不变
- 确保向后兼容

### Phase 4: 全面测试

**测试清单**:
- [ ] 所有现有单元测试通过
- [ ] BUG-001 场景测试通过
- [ ] BUG-002 场景测试通过
- [ ] 会话恢复测试通过
- [ ] API 接口测试通过

---

## 五、技术细节备忘

### 5.1 向后兼容处理

**会话恢复兼容性**:
```python
def _restore_from_state(self):
    """兼容旧会话的配额恢复"""
    if not hasattr(self.state, 'quota_consumed_agent'):
        # 从旧字段推算
        self.state.quota_consumed_agent = {}
        for agent, count in getattr(self.state, 'round_turn_counts', {}).items():
            # 估算：每个完整 round 包含 3-4 个 sub-stage turns
            self.state.quota_consumed_agent[agent] = count * 3
```

### 5.2 关键设计决策

| 决策 | 选择 | 原因 |
|-----|------|------|
| max_turns 语义 | 跨 sub-stages 累计 | 更符合用户直觉 |
| max_coding_turns 默认值 | 5 | 足够生成题目+2次提交 |
| 配额检查时机 | step() 开头 | 确保不遗漏 |
| 配额消费顺序 | stage→agent→global | 细粒度优先 |

### 5.3 不会影响的功能

✅ **角色隔离** - Agent 层设计，与配额无关
✅ **BudgetGuardian** - 独立预算系统
✅ **ConflictArbitrator** - 独立冲突检测
✅ **MemoryDistillate** - 独立功能
✅ **TransferPackage** - 创建逻辑不变
✅ **ToolPolicy** - tools 层设计
✅ **LLM Client** - 独立工厂模式

---

## 六、验证清单

### 6.1 功能验证

- [ ] `total_max_turns` 正确截断全局 turns
- [ ] `max_turns` 正确限制每个 agent 的总 turns
- [ ] `max_chat_turns` 正确推进 chat→coding
- [ ] `max_coding_turns` 正确防止无限等待
- [ ] `max_reflect_turns` 正确推进 reflect→done
- [ ] Agent 切换逻辑正常
- [ ] 会话恢复正常工作

### 6.2 性能验证

- [ ] QuotaManager 开销可忽略
- [ ] 无额外的 LLM 调用
- [ ] 内存使用合理

### 6.3 兼容性验证

- [ ] 现有 API 调用格式不变
- [ ] 现有配置文件可加载
- [ ] 旧会话可恢复

---

## 七、相关文件索引

| 文件 | 变更类型 | 说明 |
|-----|---------|------|
| `interview_crew/orchestrator/quota.py` | 新增 | 配额管理核心 |
| `interview_crew/orchestrator/engine.py` | 重写 | step() 和 _next_agent() |
| `interview_crew/protocol/schemas.py` | 修改 | 添加 max_coding_turns |
| `interview_crew/state.py` | 修改 | 添加 quota_consumed_agent |
| `tests/test_quota.py` | 新增 | QuotaManager 单元测试 |
| `tests/test_orchestrator.py` | 更新 | 调整测试用例 |

---

## 八、后续优化方向

1. **动态配额分配**: 根据候选人表现动态调整各 stage 配额
2. **配额预警**: 剩余配额少于 20% 时通知 agent
3. **配额可视化**: 在 API 返回中暴露配额使用情况

---

*创建时间: 2026-04-06*
*作者: Claude Code*
*状态: 待实施*
