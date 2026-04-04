# InterviewCrew - Claude 开发指南

## 项目概述

Multi-Agent Interview Simulator（多Agent面试模拟器）

面向程序员的技术面试陪练工具，模拟真实"三面夹击"场景：技术面试官深挖原理、HR/行为面试官施压质疑、项目面试官追问细节。使用 LangGraph 状态图管理多轮流转，解决 Single Agent "角色串戏、套路固定" 的痛点。

## 当前开发进度

### 已完成 ✅
- [x] 需求分析与文档整理
- [x] 项目骨架搭建（LangGraph + Agent 定义）
- [x] Planner 节点实现（LLM-based JSON 决策）
- [x] Specialist Agents 实现（TechAgent / BehavioralAgent / ProjectAgent）
- [x] Memory 上下文隔离与聚合节点（每个 Agent 独立历史 + Unified 聚合视角）
- [x] CLI Demo 交互入口（支持 readline、多轮对话）
- [x] 双模型 Fallback 机制（Ark / DashScope 自动切换）
- [x] 基础测试覆盖（pytest 全绿）

### 待重做/扩充 🔧
- [x] **面试配置系统**：支持灵活配置每轮 Agent 轮次和总轮数 ✅
- [ ] **Graph 架构调整**：当前为单次执行模式（CLI 控制循环），需评估是否恢复 LangGraph 闭环或采用 interrupt 机制
- [ ] **Planner 优化**：当前 JSON 解析不稳定，需改进 Prompt 或增加 retry/validation 机制
- [ ] **Baseline 对比实验**：预留脚本需实际实现，完成 Single Agent vs Multi-Agent 的量化评估
- [ ] **评估指标系统**：角色一致性评分、压力真实感、问题相关性等量化指标
- [ ] **Memory 持久化**：当前为内存状态，需支持会话保存/恢复
- [ ] **Web/API 界面**：CLI 仅为临时方案，需面向生产环境的接口

**状态**：Demo 阶段已完成，基本功能可运行。Planner + 3 Specialist Agents + Aggregator 流程已贯通，但架构层面需要进一步评估和调整。

## 面试配置系统（新功能）

支持灵活配置每轮 Agent 的轮次和总面试轮数。

### 配置结构

```python
# InterviewConfig 配置类
{
    "total_max_turns": 30,  # 全局最大轮数（安全限制）
    "rounds": {
        "tech1": {"enabled": true, "max_turns": 4, "max_chat_turns": 2, "max_reflect_turns": 1},
        "tech2": {"enabled": true, "max_turns": 4, "max_chat_turns": 2, "max_reflect_turns": 1},
        "sysdes": {"enabled": true, "max_turns": 3, "max_chat_turns": 2, "max_reflect_turns": 1},
        "leader": {"enabled": true, "max_turns": 2, "max_chat_turns": 1, "max_reflect_turns": 1},
        "hr": {"enabled": true, "max_turns": 2, "max_chat_turns": 1, "max_reflect_turns": 1}
    },
    "round_order": ["tech1", "tech2", "sysdes", "leader", "hr"]
}
```

### API 使用示例

#### 1. 完整面试（默认配置）
```bash
curl -X POST http://localhost:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{}'
```

#### 2. 仅技术面（跳过 HR 和 Leader）
```bash
curl -X POST http://localhost:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "total_max_turns": 15,
    "rounds_config": {
        "tech1": {"enabled": true, "max_turns": 4},
        "tech2": {"enabled": true, "max_turns": 4},
        "sysdes": {"enabled": true, "max_turns": 4},
        "leader": {"enabled": false},
        "hr": {"enabled": false}
    }
}'
```

#### 3. 快速筛选（仅 Tech1 + HR）
```bash
curl -X POST http://localhost:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "total_max_turns": 8,
    "rounds_config": {
        "tech1": {"enabled": true, "max_turns": 5, "max_chat_turns": 2},
        "tech2": {"enabled": false},
        "sysdes": {"enabled": false},
        "leader": {"enabled": false},
        "hr": {"enabled": true, "max_turns": 2}
    }
}'
```

#### 4. 超精简面试（每轮最少轮次）
```bash
curl -X POST http://localhost:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "total_max_turns": 6,
    "rounds_config": {
        "tech1": {"enabled": true, "max_turns": 3, "max_chat_turns": 1, "max_reflect_turns": 1},
        "tech2": {"enabled": false},
        "sysdes": {"enabled": false},
        "leader": {"enabled": false},
        "hr": {"enabled": true, "max_turns": 2, "max_chat_turns": 1}
    }
}'
```

### 配置字段说明

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `total_max_turns` | int | 30 | 全局最大轮数（所有 Agent 累计） |
| `rounds_config.{agent}.enabled` | bool | true | 是否启用该 Agent |
| `rounds_config.{agent}.max_turns` | int | 4 | 该 Agent 最大轮次（主轮次） |
| `rounds_config.{agent}.max_chat_turns` | int | 2 | chat 子阶段最大轮次 |
| `rounds_config.{agent}.max_reflect_turns` | int | 1 | reflect 子阶段最大轮次 |

### 轮次计算说明

- Tech Agent (tech1/tech2) 有三个子阶段：`chat` → `coding` → `reflect`
- `max_turns` 控制主轮次，子阶段轮次由 `max_chat_turns` 和 `max_reflect_turns` 控制
- 每个子阶段至少 1 轮（coding 阶段等待代码提交）
- 标准 Tech1 面试约 4 轮：chat(2) + coding(1) + reflect(1)

### 查询会话状态

```bash
curl http://localhost:8000/sessions/{session_id}
```

返回包含 `enabled_rounds` 字段，显示当前启用的面试轮次顺序。

## 技术栈

- 框架：LangGraph（状态图管理多轮流转）
- 模型：Claude 3.5 Sonnet / GPT-4o（Parent 协调），Claude 3.5 Haiku（Sub-agents，成本控制）
- 架构节点：
  - Planner：分析候选人回答，决定下一轮由哪个 Agent 提问
  - Specialist Agents：TechAgent（算法）、BehavioralAgent（软技能/压力）、ProjectAgent（履历深挖）
  - Memory：独立上下文隔离（每个 Agent 只看到自己的历史），聚合节点统一视角

## 环境约束

所有 Python/包管理/脚本命令必须在 `agentEnv` conda 环境中执行，格式为：

```bash
conda activate agentEnv && <command>
```

例如：
- `conda activate agentEnv && python main.py`
- `conda activate agentEnv && pip install langgraph`
- `conda activate agentEnv && pytest`

## 版本管理要求

每次完成一个功能点或阶段性修改后，必须：

1. **及时提交**：创建清晰的 commit，使用中文描述本次变更内容
2. **推送云端**：commit 后立即执行 `git push origin main`，保持本地与远程同步

提交规范示例：
```bash
git add <files>
git commit -m "feat: 添加 Planner 节点基础结构"
git push origin main
```

避免大量未提交的本地改动堆积，做好版本管理。
