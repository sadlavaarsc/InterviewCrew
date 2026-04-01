# InterviewCrew - Claude 开发指南

## 项目概述

Multi-Agent Interview Simulator（多Agent面试模拟器）

面向程序员的技术面试陪练工具，模拟真实"三面夹击"场景：技术面试官深挖原理、HR/行为面试官施压质疑、项目面试官追问细节。使用 LangGraph 状态图管理多轮流转，解决 Single Agent "角色串戏、套路固定" 的痛点。

## 当前开发进度

- [x] 需求分析与文档整理
- [ ] 项目骨架搭建（LangGraph + Agent 定义）
- [ ] Planner 节点实现
- [ ] Specialist Agents 实现（TechAgent / BehavioralAgent / ProjectAgent）
- [ ] Memory 上下文隔离与聚合节点
- [ ] Baseline 对比实验（Single Agent vs Multi-Agent）
- [ ] 评估指标与测试

**状态**：需求分析已完成，处于项目骨架搭建与架构设计阶段。

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
