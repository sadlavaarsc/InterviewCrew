# InterviewCrew Baseline 测试方案 V3

> 完整测试规章流程  
> 创建时间: 2026-04-04  
> 测试目标: 对比 Multi-Agent 与 Single-Agent Baseline 性能差异

---

## 一、测试目标

1. **量化对比** Multi-Agent 与 Single-Agent 在相同输入下的性能差异
2. **验证指标** 包括：技术覆盖度、追问深度、幻觉率、token消耗、评分一致性
3. **产出结论** 为简历项目提供可量化的 A/B 测试数据

---

## 二、测试资产

| 资产类型 | 文件路径 | 说明 |
|---------|---------|------|
| **候选人简历** | `data/samples/resume.md` | 李文韬（上海交通大学 IEEE试点班）|
| **目标职位JD** | `data/samples/jd_agent.md` | AI Agent研发工程师（实习/校招）|
| **代码版本** | `02b5cb4` | main分支最新commit |
| **服务端口** | `8000` | FastAPI默认端口 |

---

## 三、测试环境准备

```bash
# 1. 进入项目目录
cd /root/.openclaw/workspace/InterviewCrew

# 2. 确保代码最新
git pull origin main

# 3. 启动服务
python -m interview_crew.api

# 4. 健康检查
curl http://localhost:8000/health
```

---

## 四、测试配置

### 4.1 Multi-Agent 模式配置

**轮次分配：4-4-3-3-1（总计15轮）**

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
      "max_turns": 3,
      "max_chat_turns": 1,
      "max_reflect_turns": 1
    },
    "hr": {
      "enabled": true,
      "max_turns": 1,
      "max_chat_turns": 1,
      "max_reflect_turns": 0
    }
  },
  "resume_path": "data/samples/resume.md",
  "jd_path": "data/samples/jd_agent.md"
}
```

### 4.2 Single-Agent Baseline 配置

**相同总轮数，无阶段划分**

```json
{
  "mode": "single_agent",
  "total_max_turns": 15,
  "resume_path": "data/samples/resume.md",
  "jd_path": "data/samples/jd_agent.md"
}
```

---

## 五、测试执行流程

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
      "leader": {"enabled": true, "max_turns": 3, "max_chat_turns": 1, "max_reflect_turns": 1},
      "hr": {"enabled": true, "max_turns": 1, "max_chat_turns": 1, "max_reflect_turns": 0}
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

**候选人回答策略**：根据问题类型，模拟真实候选人回答
- 技术问题：基于简历中的项目经历回答
- 行为问题：展示团队协作者形象
- 系统设计：展示架构思维

#### Step 3: 获取最终报告

```bash
curl http://localhost:8000/sessions/{session_id}
```

保存完整的 `state` 和 `scribe_report`。

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

**记录返回的 `session_id`**

#### Step 2-3: 同 Phase 1

使用相同候选人回答策略，完成15轮对话。

---

## 六、实时报告格式

每轮 step 后立即在聊天中报告：

```json
{
  "turn": 3,
  "mode": "multi_agent",
  "current_round": "tech1",
  "agent": "tech_1",
  "question": "面试官本轮提出的问题",
  "candidate_response": "候选人的回答",
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

## 七、产出文件清单

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

## 八、SubAgent 评估方案

### 8.1 启动评估 SubAgent

```bash
# 方式1: 使用 openclaw CLI
openclaw sessions spawn \
  --task "[完整评估提示词见下方]" \
  --mode run \
  --runtime subagent

# 方式2: 使用工具调用
sessions_spawn(
  task="[完整评估提示词]",
  mode="run",
  runtime="subagent"
)
```

### 8.2 完整评估提示词

```markdown
## 任务
你是专业的AI面试系统评估专家。请对比分析InterviewCrew的Multi-Agent模式与Single-Agent Baseline模式的两份测试报告，给出客观、量化的评估结论。

## 输入材料
1. Multi-Agent完整对话记录（15轮，5阶段：tech1/tech2/sysdes/leader/hr）
2. Single-Agent完整对话记录（15轮，无阶段划分）
3. Multi-Agent Scribe评估报告
4. Single-Agent Scribe评估报告
5. 候选人简历（李文韬，上海交大IEEE班）
6. 目标JD（AI Agent研发工程师）

## 评估维度（逐项对比）

### 1. 技术覆盖度（30%）
- 统计两份对话中考察的技术知识点数量
- 检查是否覆盖：LLM应用开发、Agent框架、RAG、强化学习、系统设计、工程化部署
- 输出：Multi-Agent覆盖X个知识点，Single-Agent覆盖Y个知识点，差距Z%

### 2. 追问深度（25%）
- 统计每轮的连续追问次数（面试官连续发问未切换agent/话题）
- 计算平均追问深度
- 输出：Multi-Agent平均X轮，Single-Agent平均Y轮

### 3. 幻觉率（25%）
- 逐条核对Scribe报告中的事实陈述与简历/JD的一致性
- 标记明显错误（如虚构项目、错误技术栈、错误时间线）
- 输出：Multi-Agent幻觉数X，Single-Agent幻觉数Y，幻觉率Z%

### 4. 评分一致性（20%）
- 同一份简历测两次，检查Multi-Agent两次评分方差
- 检查Single-Agent两次评分方差（如有多次测试）
- 评估哪个模式评分更稳定

## 输出格式

### 量化对比表
| 指标 | Multi-Agent | Single-Agent | 胜出方 | 差距 |
|------|-------------|--------------|--------|------|
| 技术覆盖度 | X个知识点 | Y个知识点 | ? | Z% |
| 平均追问深度 | X轮 | Y轮 | ? | Z轮 |
| 幻觉率 | X% | Y% | ? | Z% |
| 总token消耗 | X | Y | ? | Z% |
| Plus模型占比 | X% | Y% | ? | Z% |

### 质性分析
1. Multi-Agent优势场景
2. Single-Agent优势场景
3. 关键差异点分析
4. 推荐结论（简历项目用哪个数据）

## 约束
- 基于事实，不臆测
- 量化优先，给出具体数字
- 如有不确定，明确标注"无法判断"
```

### 8.3 评估产出

| 文件名 | 内容 | 保存路径 |
|--------|------|---------|
| `SUBAGENT_EVALUATION_20260404.md` | SubAgent独立评估结论 | `reports/` |

---

## 九、关键指标对比表（待填充）

测试完成后，填写以下表格：

| 指标 | Multi-Agent | Single-Agent | 胜出方 | 备注 |
|------|-------------|--------------|--------|------|
| 总token消耗 | ? | ? | ? | 低者胜 |
| Plus模型token占比 | ? | ? | ? | 高者胜（深入追问多）|
| Flash模型token占比 | ? | ? | ? | 参考 |
| 实际回合数 | ? | ? | ? | 应均为15 |
| LLM调用次数 | ? | ? | ? | 参考 |
| 技术覆盖知识点数 | ? | ? | ? | 人工/SubAgent评估 |
| 幻觉/事实错误数 | ? | ? | ? | 人工/SubAgent评估 |
| 平均追问深度 | ? | ? | ? | 人工/SubAgent评估 |
| Scribe报告完整性 | ? | ? | ? | 主观评估 |

---

## 十、测试完成标准

- [ ] Multi-Agent模式完成15轮对话
- [ ] Single-Agent模式完成15轮对话
- [ ] 两份完整对话记录已保存
- [ ] 两份Scribe报告已保存
- [ ] 原始state数据已导出
- [ ] SubAgent评估已完成
- [ ] 量化对比表已填充
- [ ] Git commit & push 完成

---

*测试方案版本: V3*  
*最后更新: 2026-04-04*  
*维护者: Kimi Claw (沈清欢)*
