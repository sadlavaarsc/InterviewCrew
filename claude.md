# InterviewCrew - Claude 开发速查

> Multi-Agent 面试模拟器 | LangGraph + FastAPI | 5 位专业面试官

---

## ⚠️ 关键约束

**所有命令必须在 `agentEnv` conda 环境中执行：**

```bash
conda activate agentEnv && <command>
```

**示例：**
```bash
conda activate agentEnv && python -m interview_crew.server
conda activate agentEnv && pytest tests/ -v
conda activate agentEnv && pip install <package>
```

---

## 快速开始

```bash
# 1. 确保环境激活并安装依赖
conda activate agentEnv && pip install -r requirements.txt

# 2. 配置环境变量（.env）
ARK_API_KEY=xxx
DASHSCOPE_API_KEY=xxx

# 3. 启动后端
conda activate agentEnv && python -m interview_crew.server

# 4. 运行 CLI 演示（另开终端）
conda activate agentEnv && python -m interview_crew.cli --turns 6 --resume data/samples/resume.md --jd data/samples/jd.md
```

---

## 项目结构速览

```
interview_crew/        # 核心代码
├── agents/            # 5 位面试官 (tech1/tech2/sysdes/hr/scribe)
├── orchestrator/      # 编排器 + 预算控制 + 冲突仲裁
├── memory/            # 记忆蒸馏 + 邮箱隔离
├── tools/             # 工具注册
└── prompts/           # 系统提示词

reports/               # 审计报告、测试反馈、扩展计划
data/                  # 测试记录、样本数据
docs/TECHNICAL.md      # 详细技术文档
```

---

## 常用命令

```bash
# 运行测试
conda activate agentEnv && pytest tests/ -v

# 创建会话（API）
curl -X POST http://localhost:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{"rounds_config":{"tech1":{"enabled":true,"max_turns":4}}}'

# 查询会话状态
curl http://localhost:8000/sessions/{session_id}
```

---

## 注意事项

1. **环境隔离**：所有 Python 命令必须通过 `conda activate agentEnv &&` 前缀执行
2. **API 依赖**：CLI 是 HTTP 客户端，必须先启动后端 (`python -m interview_crew.server`)
3. **测试数据**：样本简历/JD 存放在 `data/samples/`，测试记录保存在 `data/records/`
4. **模型配置**：支持 Ark + DashScope 双模型自动 fallback

---

## 参考文档

- **README.md** / **README_CN.md** - 项目介绍与功能演示
- **docs/TECHNICAL.md** - 详细技术文档（架构、数据结构、扩展指南）
- **reports/** - 审计报告、测试反馈、扩展计划

---

*最后更新: 2026-04-04*
