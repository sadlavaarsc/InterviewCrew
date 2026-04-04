# 李文韬

**联系方式**  
📧 sadlavaarsc3248@gmail.com | 📱 (+86) 13307696016 | 🔗 GitHub: [sadlavaarsc](https://github.com/sadlavaarsc)

---

## 教育背景

**上海交通大学** | 电子信息与电气工程学院  
**自动化（IEEE 试点班）** | 本科在读  
*2023.09 – 2027.06*

**核心竞赛奖项：**
- 全国信息学奥林匹克竞赛（NOIP）省级一等奖（2021）
- 全国大学生数学建模竞赛全国三等奖（2024.10）

---

## 技术能力

**编程语言：** Python, C++, Java  
**技术栈关键词：** RAG / LangChain / MCP / RL / Agent / FastAPI

---

## 项目经历

### RepoMind | 代码感知 RAG 系统
*2026.03 – 至今* | [GitHub: sadlavaarsc/RepoMind](https://github.com/sadlavaarsc/RepoMind)  
**技术栈：** Python, FastAPI, FAISS, OpenAI SDK, Pydantic v2

**背景**  
传统 RAG 处理代码库时表现不佳：若按整块区分存在严重的 token 浪费问题；任意切块则会导致代码结构理解缺失。

**方案设计**
- **AST 感知多级分块策略：** file / class / function / block 四级切片，提取结构化元数据（imports, signatures, call relationships）
- **多级检索流水线：** Query 扩展（MQE）→ 向量检索（FAISS）→ 中文 n-gram 关键词过滤 → MMR 多样性重排序
- **双模型路由架构（Fast/Slow）：** 通过对问题进行智能分类，简单问题路由至高速低成本模型，复杂问题由大参数模型深度推理

**成果**
- 对比朴素 RAG（naive file-level chunking），在中大型代码库上实现约 **88% token 减少**（14,100 → 1,634 tokens）
- 集成 MCP 协议，支持 Claude Desktop 等 Agent 直接调用

---

### CueZero | 高性能台球 AI 系统
*2025.11 – 至今* | [GitHub: sadlavaarsc/CueZero](https://github.com/sadlavaarsc/CueZero)  
**技术栈：** Python, PyTorch, pooltool, Poetry

**背景**  
台球 AI 面临连续动作空间决策难题（5 维连续动作，约 243,000+ 潜在组合），传统暴力搜索不可行；需兼顾强度与实时性。

**方案设计**
- **Ghost Ball 启发式 + 策略引导剪枝的连续动作 MCTS：** 将搜索空间从 243,000 缩减至 4,500（**54× 缩减**）
- **双模式 MCTS 架构：** 
  - MCTS-Full（150 sims, depth 4）：用于强对局
  - MCTS-Fast（30 sims, depth 2）：用于实时交互
- **自对弈训练管道：** 预训练（~200 epochs）→ 自对弈（~600 epochs）→ 精调（~200 epochs），模型仅 **160K 参数**

**成果**
- 对比基于规则的基准代理（BasicAgent）达到 **95% 胜率**
- MCTS-Fast 实现 **180× 推理加速**（3 分钟/杆 → 1 秒/杆），仅牺牲 5% 胜率（90% vs 95%）

---

### DiabEyeDet | 糖尿病视网膜病变智能检测系统
*2025.11 – 至今* | [GitHub: sadlavaarsc/DiabEyeDet](https://github.com/sadlavaarsc/DiabEyeDet)  
**技术栈：** Python, FastAPI, PyTorch, OpenCV, Docker, Celery, Redis

**背景**  
医学影像分析需要高精度眼底检测（视盘、黄斑、血管），且面临标注样本稀缺问题；同时需要工程化部署支持异步并发处理。

**方案设计**
- **视盘检测：** U-Net 分割 + BCE + Dice 组合损失 + 早停策略，20-30 epochs 收敛
- **黄斑检测：** 三通道联合检测 + 解剖先验排序（disc-macula 水平距离 ≈ 2.5-2.7DD）
- **异常检测：** PCA 子空间学习 + 韦伯定律自适应阈值，无需标注样本
- **工程架构：** FastAPI 异步服务 + Celery + Redis 任务队列 + Docker 容器化一键部署

**成果**
- 血管分割达到像素级精度，黄斑检测精度超越人眼水平
- 系统支持异步并发处理，**API 平均响应延迟 &lt; 500ms**

---

## 竞赛获奖

| 竞赛                           | 奖项       | 时间    |
| :----------------------------- | :--------- | :------ |
| 全国大学生数学建模竞赛         | 全国三等奖 | 2024.10 |
| 全国信息学奥林匹克竞赛（NOIP） | 省级一等奖 | 2021    |
