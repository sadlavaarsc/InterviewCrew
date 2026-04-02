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
- [ ] **Graph 架构调整**：当前为单次执行模式（CLI 控制循环），需评估是否恢复 LangGraph 闭环或采用 interrupt 机制
- [ ] **Planner 优化**：当前 JSON 解析不稳定，需改进 Prompt 或增加 retry/validation 机制
- [ ] **Baseline 对比实验**：预留脚本需实际实现，完成 Single Agent vs Multi-Agent 的量化评估
- [ ] **评估指标系统**：角色一致性评分、压力真实感、问题相关性等量化指标
- [ ] **Memory 持久化**：当前为内存状态，需支持会话保存/恢复
- [ ] **Web/API 界面**：CLI 仅为临时方案，需面向生产环境的接口

**状态**：Demo 阶段已完成，基本功能可运行。Planner + 3 Specialist Agents + Aggregator 流程已贯通，但架构层面需要进一步评估和调整。

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
