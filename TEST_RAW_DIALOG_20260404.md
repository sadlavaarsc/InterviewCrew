# 2026-04-04 测试原始对话记录（5轮面试）
---
## 第一轮（Tech1开场）
**面试官**：你好，欢迎参加面试。我对你简历中的 RepoMind 项目比较感兴趣，能否请你简要介绍一下这个项目的核心架构，以及你是如何利用 AST 来实现代码的多级分块的？
**候选人**：RepoMind是我主导开发的开源代码RAG助手，核心架构分为三层：前端是基于React的Web UI，中间层是FastAPI后端服务，底层是向量数据库+大模型推理模块。AST多级分块的实现逻辑是：首先用Python的ast模块解析Python代码，Tree-sitter解析多语言代码，识别类、函数的边界作为一级分块，然后对超过200行的超大函数，识别内部的逻辑块（循环、条件分支、嵌套函数）作为二级分块，每个分块都保留上层的函数签名、全局依赖等上下文信息，同时设置10%的重叠窗口避免上下文断裂，最终代码检索准确率提升了35%。

---
## 第二轮（Tech1追问）
**面试官**：感谢介绍。既然后端使用了 FastAPI，我想考察一下 Python 并发相关的基础知识。请问在 FastAPI 中，`async def` 定义的路径操作函数与普通的 `def` 定义有什么区别？底层事件循环（Event Loop）是如何调度这两者的？
**候选人**：FastAPI中async def定义的是异步路径函数，会被提交到底层的uvicorn事件循环中调度，不会阻塞其他请求；普通def定义的是同步函数，会被放到线程池中执行，阻塞时会占用独立线程不影响事件循环。底层调度逻辑是：异步函数直接在事件循环中协程调度，同步函数会被uvicorn的ThreadPoolExecutor包装后执行，执行完再把结果返回给事件循环。如果在async函数里调用同步阻塞代码，会卡住整个事件循环，导致所有请求都被阻塞。

---
## 第三轮（Tech1编码阶段）
**面试官**：好的，理解得很清晰。现在进入编码环节，请完成以下算法题。
**题目：最接近目标和的两个数**
给定一个整数数组 `nums` 和一个目标值 `target`，请找出数组中两个数，使它们的和最接近 `target`。返回这两个数的索引（任意顺序）。
**候选人提交代码**：
```python
def two_sum_closest(nums, target):
    nums_with_index = [(num, idx) for idx, num in enumerate(nums)]
    nums_with_index.sort()
    left, right = 0, len(nums_with_index) - 1
    closest_sum = float("inf")
    result = []
    while left < right:
        current_sum = nums_with_index[left][0] + nums_with_index[right][0]
        if abs(current_sum - target) < abs(closest_sum - target):
            closest_sum = current_sum
            result = [nums_with_index[left][1], nums_with_index[right][1]]
        if current_sum < target:
            left += 1
        else:
            right -= 1
    return result
```
**判题结果**：所有3个测试用例全部通过，执行耗时0.33ms
**面试官追问**：代码执行通过！请分析这段代码的时间复杂度和空间复杂度。如果数据量扩大 100 倍，你会如何优化？
**候选人**：这段双指针解法的时间复杂度是O(n log n)，主要来自排序步骤，双指针遍历是O(n)；空间复杂度是O(n)，用来存储带索引的排序后数组。如果数据量扩大100倍，可以采用哈希表解法把时间复杂度优化到O(n)，空间复杂度还是O(n)，适合大规模数据处理。

---
## 第四轮（Tech1反思阶段）
**面试官**：分析得很准确。现在面试进入最后阶段，请你回顾一下今天的表现：你觉得自己在哪个环节回答得最好？有没有哪个问题让你觉得可以回答得更好？另外，结合你做的 Agent 和 RAG 项目，你认为在实际工程中最容易被忽视的性能瓶颈是什么？
**候选人**：我觉得自己在项目架构和异步原理部分回答得最好，对FastAPI的调度逻辑理解比较透彻。刚才哈希表优化的点我确实混淆了精确匹配和近似匹配的场景，这里可以回答得更好。实际工程中最容易被忽视的性能瓶颈是序列化/反序列化的开销，尤其是大模型RAG场景下，大量文档的序列化和向量计算的批量优化经常被忽视，会导致QPS上不去。
