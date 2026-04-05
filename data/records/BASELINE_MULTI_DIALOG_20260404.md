# Multi-Agent Baseline Test - 2026-04-04

Session ID: 9b9ada41-89ac-48ea-9ef4-973db4dd3501
Mode: multi_agent
Total Turns: 15

## Turn 1 (Agent: tech1)

**Interviewer:** 你好，李文韬。看到你提到了 RepoMind 这个代码感知 RAG 系统。我想先了解一下，在处理代码库的索引构建时，你是如何设计代码切片（Chunking）策略的？特别是如何保证切分后的代码片段保留完整的语义结构，比如函数或类的完整性？

**Candidate:** 你好，我是李文韬，上海交通大学IEEE试点班的学生。我主要做AI Agent相关的项目，包括RepoMind代码感知RAG系统和CueZero台球AI系统。

## Turn 2 (Agent: tech2)

**Interviewer:** 88% 的 Token 节省确实很诱人，但 RAG 的核心终究是检索质量。你具体使用了什么数据集和评估指标来量化召回率，以确保在大幅削减 Token 的同时没有牺牲关键语义的检索效果，尤其是跨文件依赖场景？

**Candidate:** RepoMind是我最近的项目，我们用AST感知多级分块策略处理代码库，相比朴素RAG减少了88%的token消耗，还集成了MCP协议。

## Turn 3 (Agent: sysdes)

**Interviewer:** 四级切片确实提升了语义完整性，但在检索阶段，你如何决定召回的粒度？比如当用户查询某个具体逻辑时，是只返回 block 级片段，还是会自动向上聚合 function 甚至 import 信息？这其中的 token 开销与上下文完整性的 Trade-off 是怎么考量的？

**Candidate:** AST分块我们用了四级切片：file、class、function、block。每级提取结构化元数据，包括imports、signatures和call relationships。

## Turn 4 (Agent: hr)

**Interviewer:** 这套技术链路很清晰，但我想聊聊背后的权衡。你之前提到‘减少 88% token 消耗’，这往往伴随着召回率的风险。当业务方因为‘省了成本但漏了关键代码’而向你施压时，你是如何沟通并证明你的方案价值的？请举一个你不得不为技术决策承担业务后果的具体例子。

**Candidate:** Query扩展我们用MQE做语义扩展，向量检索用FAISS，然后用中文n-gram做关键词过滤，最后MMR重排序保证多样性。

## Turn 5 (Agent: scribe)

**Interviewer:** # 面评报告

## 技术评估
候选人在 AI Agent 系统工程化落地方面表现突出，特别是在代码感知 RAG 系统的优化上。具体体现在基于 AST 的四级切片策略（file/class/function/block）及检索链路设计（FAISS+MQE+MMR），有效降低 88% token 消耗。CueZero 项目展示了基于 MuZero 架构的强化学习能力，完成 200 万局自我对弈并结合 pooltool 物理引擎，体现较强的算法实现与系统整合能力。但检索效果缺乏召回率、F1 等量化指标支撑，RL 项目的奖励函数设计与收敛性细节待澄清。

## 行为/文化担忧
在应对业务压力与技术决策责任方面表现较弱。面对“因技术优化导致漏检”的假设情境，仅泛化回应“沟通证明价值”，缺乏具体案例、沟通策略及结果复盘。抗压能力与责任承担意识缺乏实证支撑，存在跨团队协作风险。

## 推荐
Weak Hire

## 证据链
1. RepoMind 项目：实现 AST 切片与 MCP 协议集成，token 消耗降低 88%（缺乏对照组实验数据）。
2. 检索链路：构建完整向量检索与重排序流程，但未提供召回率对比数据。
3. CueZero 项目：确认基于 MuZero 架构与 pooltool 引擎，但奖励函数与物理融合细节未展开。
4. 行为面试：对业务后果承担问题的回答模糊，无具体情境验证。

**Candidate:** CueZero是用强化学习做台球AI，基于MuZero架构，训练了200万局自我对弈，结合物理模拟引擎pooltool。

