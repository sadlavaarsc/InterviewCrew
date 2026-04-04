# InterviewCrew 扩展计划书

**提交人**: Kimi Claw (HR Director Mode)  
**接收人**: Claude Code  
**日期**: 2026-04-03  
**版本**: v1.0 - 流程完善版

**重要提示:** 脚本沙箱暂时只支持python 即可，编译型语言可以暂时不支持

---

## 1. 当前问题诊断

### 1.1 流程缺失环节

| 大厂标准环节 | 当前 InterviewCrew | 状态 |
|-------------|-------------------|------|
| 算法 Coding 面 | ❌ 缺失 | **P0 - 必须补充** |
| Manager/Leader 面 | ❌ 缺失 | **P1 - 建议补充** |
| 简历上下文注入 | ✅ 已修复 | 问题已解决 |
| Scribe 幻觉 | ✅ 已修复 | 问题已解决 |

### 1.2 环节顺序问题

**当前顺序**: Tech1 → Tech2 → SysDes → HR → Scribe  
**问题**: SysDes 过早，HR 位置偏前，缺少 Coding 和 Leader 面

**建议顺序**:  
`Tech1 → Tech2 → Coding → SysDes → Leader → HR → Scribe`

---

## 2. 新增环节设计

### 2.1 Coding Round（算法手撕代码）

#### 定位
- **轮次**: 第 3 轮（Tech2 之后）
- **面试官**: CodeMaster Agent
- **目标**: 验证候选人实际编码能力，非纯问答
- **模型**: `qwen_plus_model` (需要强代码能力)
- **Temperature**: 0.3 (确定性高，减少创意发挥)

#### Prompt 设计

```text
你是一位算法面试官（CodeMaster），风格严谨，关注代码正确性与边界处理。

【核心规则】
- 每次只提出 1 道算法题，难度 LeetCode Medium
- 题目必须与候选人简历技术栈相关（如 Java 候选人选 Java 相关算法）
- 要求候选人写出可运行的代码，而非伪代码
- 候选人提交代码后，必须执行测试用例验证
- 如果代码有 bug，指出具体行并询问修复思路
- 如果代码正确，追问时间/空间复杂度优化
- 不透露自己是 AI

【题目选择策略】
- 优先选择与简历项目相关的算法（如 RAG 系统 → 倒排索引/相似度计算）
- 次选通用高频题（Two Sum, LRU, 二叉树遍历等）
- 避免过于冷门的算法（如珂朵莉树）

【交互流程】
1. 出题 → 2. 候选人写代码 → 3. 执行测试 → 4. 反馈结果 → 5. 追问优化

【输出格式】
{
  "question": "题目描述...",
  "starter_code": "可选的代码框架...",
  "test_cases": ["输入", "预期输出"],
  "evaluation_score": 0.0-1.0,
  "key_weaknesses": ["..."],
  "follow_up_candidates": ["..."],
  "reasoning": "..."
}
```

#### 技术实现要点

1. **Code Sandbox 集成**
   - 需要 Docker 容器隔离执行环境
   - 支持 Python/Java/Go/C++ 多语言
   - 限制执行时间（2秒）和内存（256MB）
   - 沙箱需防逃逸（no network, read-only fs）

2. **测试用例设计**
   - 每道题至少 3 组测试用例：正常、边界、错误
   - 隐藏测试用例（不展示给候选人）
   - 执行结果反馈：通过/失败 + 具体错误信息

3. **状态流转**
   - Tech2 → Coding → SysDes
   - Coding 轮不通过可直接 Reject（算法是硬通货）

#### 接口扩展

```python
# 新增 API
POST /sessions/{id}/code
{
  "code": "候选人提交的代码",
  "language": "python|java|go|cpp"
}

# 返回
{
  "compile_result": "编译结果",
  "test_results": [
    {"case": 1, "input": "...", "expected": "...", "actual": "...", "passed": true|false}
  ],
  "overall_passed": true|false
}
```

---

### 2.2 Leader Round（Manager 面）

#### 定位
- **轮次**: 第 5 轮（SysDes 之后，HR 之前）
- **面试官**: Leader Agent
- **目标**: 评估项目 Ownership、团队协作、商业敏感度
- **模型**: `qwen_plus_model`
- **Temperature**: 0.5 (专业但有温度)

#### Prompt 设计

```text
你是一位技术团队 Leader（Engineering Manager），风格务实直接，关注结果而非过程。
面试目标：评估候选人的项目 Ownership、团队协作能力、商业敏感度与文化匹配度。

【核心规则】
- 每次只提 1 个问题
- 问题基于候选人简历中的项目经历和前几轮技术表现
- 语气专业但有温度，不咄咄逼人但直击要害
- 不透露自己是 AI

【评估维度】
1. Ownership（权重 30%）：
   - 候选人是项目的推动者还是被动执行者？
   - 能否描述项目的关键决策及其影响？

2. 数据思维（权重 20%）：
   - 能否用量化指标描述项目成果？
   - 是否关注技术投入的 ROI？

3. 协作能力（权重 25%）：
   - 如何处理团队冲突与跨部门沟通？
   - 描述一次推动他人接受你方案的经历

4. 商业敏感度（权重 15%）：
   - 技术决策是否服务于业务目标？
   - 如何看待技术债与业务需求的平衡？

5. 文化匹配（权重 10%）：
   - 职业目标是否与团队方向一致？
   - 为什么想加入我们公司/团队？

【提问策略】
- 首轮：从简历中挑选最复杂的项目，问 "如果重来一次，你会改变什么决策？"
- 次轮：基于回答追问冲突处理或数据指标
- 第三轮：职业规划与动机

【输出格式】
{
  "question": "...",
  "evaluation_score": 0.0-1.0,
  "key_weaknesses": ["..."],
  "follow_up_candidates": ["..."],
  "reasoning": "..."
}
```

#### 上下文注入

```python
# LeaderAgent.build_context() 需注入
- candidate_profile（完整画像）
- competency_vector（能力评分）
- project_highlights（简历项目亮点摘要）
- tech_evaluation_summary（前几轮技术评估摘要）
- contradiction_alerts（需重点核查的矛盾点）
```

#### 与 HR 的区别

| 维度 | Leader 面 | HR 面 |
|------|-----------|-------|
| 关注点 | 项目影响力、技术决策 | 价值观、行为、薪资 |
| 提问深度 | 深挖项目细节 | 行为面试（STAR） |
| 评估目标 | 能否成为靠谱队友 | 是否符合公司文化 |
| 语气 | 务实、直接 | 亲和、敏锐 |

---

## 3. 流程重构

### 3.1 新状态机

```python
_state_order = [
    "screening",   # Tech1 映射 - 基础技术
    "tech1",       # Tech2 映射 - 深度技术
    "tech2",       # Coding 映射 - 算法编码 ★新增
    "coding",      # SysDes 映射 - 系统设计 ★重命名
    "system",      # Leader 映射 - Manager 面 ★新增
    "leader",      # HR 映射 - 行为面试
    "hr",          # Finished - Scribe 评估
    "finished"
]
```

### 3.2 Agent 映射表

| 状态 | Agent 类 | Prompt 文件 | 出场轮次 |
|------|----------|-------------|----------|
| screening | Tech1Agent | tech1.txt | 第 1 轮 |
| tech1 | Tech2Agent | tech2.txt | 第 2 轮 |
| tech2 | **CodingAgent** | **coding.txt** ★ | 第 3 轮 |
| coding | SysDesAgent | sysdes.txt | 第 4 轮 |
| system | **LeaderAgent** | **leader.txt** ★ | 第 5 轮 |
| leader | HRAgent | hr.txt | 第 6 轮 |
| hr | ScribeAgent | scribe.txt | 第 7 轮 |

### 3.3 max_turns 适配

| max_turns | 实际流程 | 适用场景 |
|-----------|----------|----------|
| 3 | Tech1 → Tech2 → Scribe | 快速筛选 |
| 4 | Tech1 → Tech2 → Coding → Scribe | 校招/实习基础版 |
| 5 | + SysDes | 社招基础版 |
| 6 | + Leader | 社招完整版 |
| 7 | + HR | 社招终极版 |

---

## 4. 技术实现清单

### 4.1 新增文件

```
interview_crew/
├── agents/
│   ├── coding_agent.py      # ★ 新增
│   └── leader_agent.py      # ★ 新增
├── prompts/
│   ├── coding.txt           # ★ 新增
│   └── leader.txt           # ★ 新增
├── services/
│   └── code_sandbox.py      # ★ 新增（Docker 沙箱）
└── schemas.py               # 扩展 AgentOutput 支持代码相关字段
```

### 4.2 修改文件

```
interview_crew/
├── engine.py                # 更新 _state_order 和 Agent 映射
├── agents/base.py           # 扩展 _prepare_input 支持代码提交
└── memory/agent_mailbox.py  # 扩展 build_agent_messages
```

### 4.3 依赖新增

```bash
# requirements.txt 新增
docker>=6.0.0          # Docker SDK for Python
RestrictedPython>=6.0  # 代码安全沙箱（备用方案）
```

---

## 5. 验证方案

### 5.1 Coding Round 验证

- [ ] 能正确生成与简历技术栈相关的算法题
- [ ] 候选人提交代码后能执行测试用例
- [ ] 测试失败时指出具体错误
- [ ] 测试通过时追问复杂度优化
- [ ] 支持 Python/Java/Go 至少三种语言

### 5.2 Leader Round 验证

- [ ] 问题基于简历项目经历
- [ ] 追问 Ownership 和项目影响力
- [ ] 语气专业不咄咄逼人
- [ ] 与 HR 面有明显区分度

### 5.3 全流程验证

- [ ] max_turns=7 能跑完完整流程
- [ ] 短轮数（3-4）不出现异常跳过
- [ ] Scribe 报告包含所有轮次评价

---

## 6. 优先级与时间预估

| 任务 | 优先级 | 预估工作量 | 依赖 |
|------|--------|-----------|------|
| Coding Prompt 设计 | P0 | 2h | 无 |
| Code Sandbox 基础框架 | P0 | 8h | Docker |
| CodingAgent 实现 | P0 | 4h | 沙箱框架 |
| Leader Prompt 设计 | P1 | 2h | 无 |
| LeaderAgent 实现 | P1 | 3h | 无 |
| 状态机重构 | P1 | 2h | Agent 实现 |
| 全流程测试 | P1 | 4h | 全部 |
| 多语言支持 | P2 | 6h | CodingAgent |
| 隐藏测试用例 | P2 | 3h | 测试框架 |

**总计**: P0 约 14h，P1 约 11h，P2 约 9h

---

## 7. 交付物

1. **新增 Agent 代码**: `coding_agent.py`, `leader_agent.py`
2. **新增 Prompt 文件**: `coding.txt`, `leader.txt`
3. **沙箱服务**: `code_sandbox.py` + Docker 配置
4. **更新后的 Engine**: 新状态机映射
5. **测试报告**: 验证 Coding 和 Leader 轮次的测试记录
6. **飞书文档**: 更新后的 [PROMPT_REGISTRY.md](../reports/PROMPT_REGISTRY.md)

---

*文档编制: Kimi Claw*  
*日期: 2026-04-03*
