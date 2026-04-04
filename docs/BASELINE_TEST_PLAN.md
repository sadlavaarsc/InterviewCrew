# InterviewCrew Baseline 测试方案 V4

> 完整测试规章流程  
> 创建时间: 2026-04-04  
> 测试目标: 对比 Multi-Agent 与 Single-Agent Baseline 性能差异  
> **核心改进**: SAS改为Workflow-like模式，与MAS阶段完全对齐

---

## 一、测试目标

1. **量化对比** Multi-Agent 与 Single-Agent 在**相同阶段配置**下的性能差异
2. **验证核心假设**: MAS的记忆隔离 vs SAS的角色混淆/记忆污染
3. **产出结论** 为简历项目提供可量化的 A/B 测试数据

---

## 二、测试资产

| 资产类型 | 文件路径 | 说明 |
|---------|---------|------|
| **候选人简历** | `data/samples/resume.md` | 李文韬（上海交通大学 IEEE试点班）|
| **目标职位JD** | `data/samples/jd_agent.md` | AI Agent研发工程师（实习/校招）|
| **代码版本** | `5eb78b9` | 包含Workflow-like SAS的最新commit |
| **服务端口** | `8000` | FastAPI默认端口 |

---

## 三、关键对比维度

| 维度 | Multi-Agent System (MAS) | Single-Agent Baseline (SAS) |
|------|--------------------------|----------------------------|
| **架构** | 5个专家Agent，独立记忆 | 1个Agent，硬切换角色 |
| **阶段划分** | tech1→tech2→sysdes→leader→hr | tech1→tech2→sysdes→leader→hr（相同）|
| **轮次分配** | 4-4-3-2-2 = 15轮 | 4-4-3-2-2 = 15轮（相同）|
| **记忆隔离** | ✅ 每阶段独立上下文 | ❌ 共享统一历史，易混淆 |
| **角色切换** | Agent自动交接 | Prompt约束，无硬性隔离 |

---

## 四、测试环境准备

```bash
# 1. 进入项目目录
cd /root/.openclaw/workspace/InterviewCrew

# 2. 确保代码最新（包含Workflow-like SAS）
git pull origin main

# 3. 启动服务
python -m interview_crew.api

# 4. 健康检查
curl http://localhost:8000/health
```

---

## 五、测试配置

### 5.1 Multi-Agent 模式配置

**阶段分配：4-4-3-2-2（总计15轮）**

```json
{
  "mode": "multi_agent",
  "total_max_turns": 15,
  "rounds_config": {
    "tech1": {
      "enabled": true,
      "max_turns": 4,
      "max_chat_turns": 2,
      "max_reflect_turns": 1
    },
    "tech2": {
      "enabled": true,
      "max_turns": 4,
      "max_chat_turns": 2,
      "max_reflect_turns": 1
    },
    "sysdes": {
      "enabled": true,
      "max_turns": 3,
      "max_chat_turns": 1,
      "max_reflect_turns": 1
    },
    "leader": {
      "enabled": true,
      "max_turns": 2,
      "max_chat_turns": 1,
      "max_reflect_turns": 1
    },
    "hr": {
      "enabled": true,
      "max_turns": 2,
      "max_chat_turns": 1,
      "max_reflect_turns": 0
    }
  },
  "resume_path": "data/samples/resume.md",
  "jd_path": "data/samples/jd_agent.md"
}
```

### 5.2 Single-Agent Baseline 配置

**Workflow-like阶段划分，与MAS完全对齐**

```json
{
  "mode": "single_agent",
  "total_max_turns": 15,
  "resume_path": "data/samples/resume.md",
  "jd_path": "data/samples/jd_agent.md"
}
```

**SAS内部阶段映射**（自动按轮次推进）：
- tech1: 第1-4轮
- tech2: 第5-8轮  
- sysdes: 第9-11轮
- leader: 第12-13轮
- hr: 第14-15轮

---

## 六、测试执行流程

### Phase 1: Multi-Agent 模式测试

#### Step 1: 创建会话

```bash
curl -X POST http://localhost:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "multi_agent",
    "total_max_turns": 15,
    "rounds_config": {
      "tech1": {"enabled": true, "max_turns": 4, "max_chat_turns": 2, "max_reflect_turns": 1},
      "tech2": {"enabled": true, "max_turns": 4, "max_chat_turns": 2, "max_reflect_turns": 1},
      "sysdes": {"enabled": true, "max_turns": 3, "max_chat_turns": 1, "max_reflect_turns": 1},
      "leader": {"enabled": true, "max_turns": 2, "max_chat_turns": 1, "max_reflect_turns": 1},
      "hr": {"enabled": true, "max_turns": 2, "max_chat_turns": 1, "max_reflect_turns": 0}
    },
    "resume_path": "data/samples/resume.md",
    "jd_path": "data/samples/jd_agent.md"
  }'
```

**记录返回的 `session_id`**

#### Step 2: 循环调用 step

每轮调用后实时报告结果，直到 `finished=true`：

```bash
curl -X POST http://localhost:8000/sessions/{session_id}/step \
  -H "Content-Type: application/json" \
  -d '{
    "candidate_response": "候选人的回答内容"
  }'
```

**候选人回答策略**：基于简历内容，模拟真实候选人
- **RepoMind项目**：AST分块、RAG优化、MCP协议
- **CueZero项目**：强化学习、物理模拟
- **技术栈**：Python、FastAPI、PyTorch、LangChain

#### Step 3: 获取最终报告

```bash
curl http://localhost:8000/sessions/{session_id}
```

---

### Phase 2: Single-Agent Baseline 测试

#### Step 1: 创建会话

```bash
curl -X POST http://localhost:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "single_agent",
    "total_max_turns": 15,
    "resume_path": "data/samples/resume.md",
    "jd_path": "data/samples/jd_agent.md"
  }'
```

#### Step 2-3: 同 Phase 1

使用**相同候选人回答策略**，完成15轮对话。

**关键观察点**：
- SAS是否在阶段切换时出现角色混淆？
- SAS是否把tech1的问题带到sysdes？
- SAS是否忘记之前问过的内容？

---

## 七、实时报告格式

每轮 step 后立即在聊天中报告：

```json
{
  "turn": 3,
  "mode": "multi_agent",
  "current_stage": "tech1",
  "agent": "tech_1",
  "question": "面试官本轮提出的问题",
  "candidate_response": "候选人的回答（用户提供）",
  "token_consumed_this_turn": 2345,
  "total_token_consumed": 8921,
  "plus_token_consumed_this_turn": 1890,
  "flash_token_consumed_this_turn": 455,
  "total_plus_token_consumed": 5670,
  "total_flash_token_consumed": 3251,
  "llm_call_count": 8,
  "finished": false,
  "transfer_queue": ["tech_2"]
}
```

---

## 八、产出文件清单

测试完成后，生成以下文件：

| 文件名 | 内容 | 保存路径 |
|--------|------|---------|
| `BASELINE_MULTI_DIALOG_20260404.md` | Multi-Agent完整对话记录 | `data/records/` |
| `BASELINE_SINGLE_DIALOG_20260404.md` | Single-Agent完整对话记录 | `data/records/` |
| `SCRIBE_MULTI_REPORT_20260404.md` | Multi-Agent Scribe评估报告 | `reports/` |
| `SCRIBE_SINGLE_REPORT_20260404.md` | Single-Agent Scribe评估报告 | `reports/` |
| `BASELINE_RAW_MULTI_20260404.json` | Multi-Agent原始state数据 | `data/records/` |
| `BASELINE_RAW_SINGLE_20260404.json` | Single-Agent原始state数据 | `data/records/` |

---

## 九、SubAgent 评估方案

### 9.1 启动评估 SubAgent

```bash
sessions_spawn(
  task="[完整评估提示词]",
  mode="run",
  runtime="subagent"
)
```

### 9.2 完整评估提示词

```markdown
## 任务
你是专业的AI面试系统评估专家。请对比分析InterviewCrew的Multi-Agent模式与Single-Agent Baseline模式的两份测试报告，给出客观、量化的评估结论。

## 输入材料
1. Multi-Agent完整对话记录（15轮，5阶段：tech1/tech2/sysdes/leader/hr）
2. Single-Agent完整对话记录（15轮，相同5阶段）
3. Multi-Agent Scribe评估报告
4. Single-Agent Scribe评估报告
5. 候选人简历（李文韬，上海交大IEEE班）
6. 目标JD（AI Agent研发工程师）

## 评估维度（逐项对比）

### 1. 角色一致性（新增核心指标）
- **MAS检查**：每个阶段的问题是否符合该阶段定位？
  - tech1: 基础算法、代码能力
  - tech2: 深度追问、边界条件
  - sysdes: 系统设计、架构权衡
  - leader: 项目深挖、技术决策
  - hr: 行为面试、文化契合
- **SAS检查**：阶段切换时是否出现角色混淆？
  - 是否把tech1的问题带到sysdes？
  - 是否忘记自己是哪个阶段？
  - 是否在同一轮中混合多个角色的问题？
- **输出**：MAS角色准确率X%，SAS角色准确率Y%，混淆事件数Z

### 2. 记忆隔离效果（核心指标）
- **MAS检查**：各阶段记忆是否独立？
  - tech2是否只记得tech1的summary，不记得细节？
  - sysdes是否不受tech阶段干扰？
- **SAS检查**：是否出现记忆污染？
  - 是否反复追问已经问过的问题？
  - 是否把前面的结论错误地带到后面？
- **输出**：MAS记忆隔离度X%，SAS记忆污染事件数Y

### 3. 技术覆盖度（30%）
- 统计两份对话中考察的技术知识点数量
- 检查是否覆盖：LLM应用开发、Agent框架、RAG、强化学习、系统设计、工程化部署
- 输出：Multi-Agent覆盖X个知识点，Single-Agent覆盖Y个知识点，差距Z%

### 4. 追问深度（25%）
- 统计每轮的连续追问次数
- 计算平均追问深度
- 输出：Multi-Agent平均X轮，Single-Agent平均Y轮

### 5. 幻觉率（25%）
- 逐条核对Scribe报告中的事实陈述与简历/JD的一致性
- 标记明显错误
- 输出：Multi-Agent幻觉数X，Single-Agent幻觉数Y，幻觉率Z%

### 6. 评分一致性（20%）
- 检查两次测试的评分稳定性

## 输出格式

### 量化对比表
| 指标 | Multi-Agent | Single-Agent | 胜出方 | 差距 |
|------|-------------|--------------|--------|------|
| 角色一致性 | X% | Y% | ? | Z% |
| 记忆隔离度 | X% | Y事件污染 | ? | - |
| 技术覆盖度 | X个知识点 | Y个知识点 | ? | Z% |
| 平均追问深度 | X轮 | Y轮 | ? | Z轮 |
| 幻觉率 | X% | Y% | ? | Z% |
| 总token消耗 | X | Y | ? | Z% |
| Plus模型占比 | X% | Y% | ? | Z% |

### 质性分析
1. MAS核心优势（记忆隔离、角色一致性）
2. SAS主要缺陷（角色混淆、记忆污染实例）
3. 关键差异点对比（举例说明）
4. 简历项目推荐结论

## 约束
- 基于事实，不臆测
- 量化优先，给出具体数字
- 对SAS的角色混淆/记忆污染事件，引用具体对话片段作为证据
- 如有不确定，明确标注"无法判断"
```

### 9.3 评估产出

| 文件名 | 内容 | 保存路径 |
|--------|------|---------|
| `SUBAGENT_EVALUATION_20260404.md` | SubAgent独立评估结论 | `reports/` |

---

## 十、关键指标对比表（待填充）

测试完成后，填写以下表格：

| 指标 | Multi-Agent | Single-Agent | 胜出方 | 备注 |
|------|-------------|--------------|--------|------|
| 角色一致性 | ? | ? | ? | SAS易混淆 |
| 记忆隔离度 | ? | ? | ? | MAS独立 |
| 记忆污染事件数 | ? | ? | ? | SAS可能>0 |
| 总token消耗 | ? | ? | ? | 低者胜 |
| Plus模型token占比 | ? | ? | ? | 高者胜 |
| 实际回合数 | ? | ? | ? | 应均为15 |
| LLM调用次数 | ? | ? | ? | 参考 |
| 技术覆盖知识点数 | ? | ? | ? | 评估 |
| 幻觉/事实错误数 | ? | ? | ? | 评估 |
| 平均追问深度 | ? | ? | ? | 评估 |
| Scribe报告完整性 | ? | ? | ? | 评估 |

---

## 十一、测试完成标准

- [ ] Multi-Agent模式完成15轮对话
- [ ] Single-Agent模式完成15轮对话
- [ ] 两份完整对话记录已保存
- [ ] 两份Scribe报告已保存
- [ ] 原始state数据已导出
- [ ] SubAgent评估已完成
- [ ] 量化对比表已填充
- [ ] Git commit & push 完成

---

## 十二、预期结果（假设）

| 指标 | 预期MAS表现 | 预期SAS表现 | 原因 |
|------|------------|------------|------|
| 角色一致性 | >90% | 60-80% | SAS单Agent硬切角色易混淆 |
| 记忆隔离度 | >95% | 40-60% | MAS物理隔离，SAS共享上下文 |
| 技术覆盖度 | 高 | 中 | SAS可能重复追问 |
| 追问深度 | 深 | 浅 | SAS可能忘记之前问了什么 |
| 幻觉率 | 低 | 高 | SAS可能混淆不同阶段的结论 |

---

*测试方案版本: V4*  
*最后更新: 2026-04-04*  
*维护者: Kimi Claw (沈清欢)*  
*核心改进: Workflow-like SAS，与MAS阶段完全对齐*
