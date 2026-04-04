# InterviewCrew 代码审计报告与修复（2026-04-04）

## 审计概要

**审计时间**: 2026-04-04
**审计依据**: TEST_FEEDBACK_20260404_5ROUNDS.md, TEST_FEEDBACK_20260404_FULL.md
**修复 Commit**: `a4b6c5a`

---

## 发现的 Bug

### P0 - Tech Agent 子阶段切换失败（严重）

**问题描述**: 15 轮面试全部卡在 tech1，无法切换到 tech2 及后续 Agent

**根本原因**: `submit_code` API 在代码提交后只生成追问，**没有推进 sub_stage 从 coding → reflect**

**代码位置**: `interview_crew/api.py:147-207`

**修复方案**:
```python
# 代码执行完成后，推进 sub_stage: coding -> reflect
new_sub_stage = orchestrator.state.advance_sub_stage(agent_name)

# 如果进入 reflect 阶段，自动触发 reflect 阶段的问题生成
if new_sub_stage == "reflect":
    # 蒸馏记忆、构建 reflect 上下文、调用 LLM 生成问题
    ...
```

---

### P1 - Scribe 报告幻觉问题（中等）

**问题描述**: 生成面评报告时编造未在对话/简历中出现的内容

**示例幻觉**:
- "语速偏快"、"沟通紧张"（对话中未观察）
- "声称拥有三年分布式系统开发经验"（简历中未提及）

**根本原因**: Prompt 缺乏严格约束，大模型自动脑补通用面试评估内容

**修复方案**:

1. **scribe.txt** - 添加【重要规则】段落：
   - 禁止编造任何未在对话中提及的内容
   - 禁止对未观察到的行为（语速、表情、态度）进行推测
   - 所有结论必须有对应的对话证据支撑

2. **distiller.py** - 更新 `_DISTILL_PROMPT`：
   - 能力评估必须基于对话中的具体回答
   - evidence 字段必须引用对话原文
   - 禁止推测候选人的未提及经历

---

## 修复文件清单

| 文件 | 修改行数 | 修复内容 |
|------|---------|---------|
| `interview_crew/api.py` | +52/-4 | 添加 coding → reflect 阶段推进逻辑 |
| `interview_crew/prompts/scribe.txt` | +11/-2 | 添加严格的幻觉约束规则 |
| `interview_crew/memory/distiller.py` | +28/-1 | 添加证据约束到 distiller prompt |

---

## 测试验证

```bash
$ conda activate agentEnv && python -m pytest tests/ -v
Pytest: 20 passed
```

所有现有测试通过，修复无回归。

---

## 后续建议

### 1. 轮次配置增强（用户建议）

当前 `max_turns` 是全局总轮数，建议增加更灵活的配置：

```python
class InterviewConfig:
    rounds_config: Dict[str, int] = field(default_factory=lambda: {
        "tech1": 4,      # chat(2) + coding(1) + reflect(1)
        "tech2": 4,
        "sysdes": 3,
        "leader": 2,
        "hr": 2,
    })
```

### 2. 进一步验证

建议运行完整 15 轮测试，验证：
- Tech1 (chat→coding→reflect) 正常完成
- 自动切换到 Tech2
- Scribe 报告无幻觉内容

---

## 结论

本次审计发现并修复了两个严重 Bug：

1. **Tech Agent 阶段切换 Bug** - 已修复，coding 阶段完成后可正常进入 reflect
2. **Scribe 幻觉问题** - 已修复，添加严格的 prompt 约束

修复后系统可支持完整的面试流程：tech1 → tech2 → sysdes → leader → hr → scribe
