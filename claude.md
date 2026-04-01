# InterviewCrew - Claude 开发指南

## 项目概述

Multi-Agent Interview Simulator（多Agent面试模拟器）

面向程序员的技术面试陪练工具，模拟真实"三面夹击"场景：技术面试官深挖原理、HR/行为面试官施压质疑、项目面试官追问细节。使用 LangGraph 状态图管理多轮流转，解决 Single Agent "角色串戏、套路固定" 的痛点。

## 当前开发进度

- [x] 需求分析与文档整理
- [x] 项目骨架搭建（LangGraph + Agent 定义）
- [x] Planner 节点实现
- [x] Specialist Agents 实现（TechAgent / BehavioralAgent / ProjectAgent）
- [x] Memory 上下文隔离与聚合节点
- [x] CLI Demo 交互入口
- [x] Baseline 对比实验脚本预留（Single Agent vs Multi-Agent）
- [x] 基础测试覆盖（pytest 全绿）

**状态**：Demo 阶段搭建完成。项目已具备可运行的 LangGraph 多 Agent 面试模拟器骨架，Plnner + 3 Specialist Agents + Aggregator 流程已贯通，Memory 隔离机制已验证，测试覆盖通过。

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
