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
DEEPSEEK_API_KEY=xxx          # 默认主模型（deepseek-v4-flash / deepseek-v4-pro）
ARK_API_KEY=xxx               # 故障转移 fallback
# DASHSCOPE_API_KEY=xxx       # 已废弃，仅保留兼容

# 3. 启动后端
conda activate agentEnv && python -m interview_crew.server

# 4a. 使用 Web UI（推荐）
# 浏览器访问 http://localhost:8000/

# 4b. 运行 CLI 演示（另开终端）
conda activate agentEnv && python -m interview_crew.cli --turns 6 --resume data/samples/resume.md --jd data/samples/jd.md
```

---

## 项目结构速览

```
interview_crew/        # 核心代码
├── agents/            # 5 位面试官 (tech1/tech2/sysdes/leader/hr/scribe)
├── orchestrator/      # 编排器 + 预算控制 + 冲突仲裁 + 配额
├── memory/            # 记忆蒸馏 + 邮箱隔离
├── llm/               # 通用 OpenAI 兼容 LLM 客户端 + 模型解析 + tiktoken + 指标
├── services/          # 代码沙箱 / AST 分析 / 代码执行
├── middleware/        # Token Bucket 限流
├── storage/           # Redis / 内存 会话持久化
├── tools/             # 工具注册与 Stub 实现
├── prompts/           # 系统提示词
└── static/            # Web UI (index.html)

benchmarks/            # 性能 / 沙箱 / 延迟 benchmark
reports/               # 审计报告、测试反馈、扩展计划
data/                  # 测试记录、样本数据
docs/TECHNICAL.md      # 详细技术文档
```

---

## 常用命令

```bash
# 运行测试（当前 100 个测试全绿）
conda activate agentEnv && pytest tests/ -v

# 运行沙箱/AST benchmark（零成本，100% 通过）
conda activate agentEnv && python -m benchmarks.sandbox_benchmark

# 运行性能 benchmark（离线模式使用模拟 TTFT）
conda activate agentEnv && python -m benchmarks.performance_benchmark --offline

# 真实 TTFT 压测（需配置 DEEPSEEK_API_KEY）
conda activate agentEnv && python -m benchmarks.real_latency_benchmark

# 创建会话（API）
curl -X POST http://localhost:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{"rounds_config":{"tech1":{"enabled":true,"max_turns":4}}}'

# 查询会话状态
curl http://localhost:8000/sessions/{session_id}
```

---

## 测试与 Benchmark 状态

| 模块 | 状态 | 备注 |
|------|------|------|
| 单元测试 | ✅ 100/100 通过 | 含新增限流器、Redis、真流式测试 |
| 代码沙箱 | ✅ 18/18 通过 | subprocess 执行，Docker fallback 已实现 |
| AST 复杂度 | ✅ 38/38 100% | 18 道沙箱题 + 20 组扩展用例 |
| 安全过滤 | ✅ 6/6 拦截 | 正则静态过滤 |
| TTFT | ⚠️ 离线模拟 | 配置 API key 后运行 `real_latency_benchmark.py` 可补实测 |
| 并发压测 | ✅ 历史 100 并发通过 | DeepSeek API，服务端 0 错误 |

---

## 注意事项

1. **环境隔离**：所有 Python 命令必须通过 `conda activate agentEnv &&` 前缀执行
2. **服务依赖**：CLI 和 Web UI 都是后端 API 的客户端，必须先启动后端 (`python -m interview_crew.server`)
3. **Web UI**：`http://localhost:8000/` 提供可视化面试界面，支持轮次配置、代码考核、实时统计
4. **测试数据**：样本简历/JD 存放在 `data/samples/`，测试记录保存在 `data/records/`
5. **模型配置**：默认 DeepSeek 主模型，Ark 作为 fallback；Qwen/DashScope 已标记为废弃，旧 `.env` 仍可兼容运行但会触发 `DeprecationWarning`
6. **模型分级**：代码中统一使用 `default_model`（经济型） / `premium_model`（高质量） / `fallback_model` 别名，避免绑定具体厂商

---

## 参考文档

- **README.md** / **README_CN.md** - 项目介绍与功能演示
- **docs/TECHNICAL.md** - 详细技术文档（架构、数据结构、扩展指南）
- **reports/** - 审计报告、测试反馈、扩展计划

---

*最后更新: 2026-06-21*
