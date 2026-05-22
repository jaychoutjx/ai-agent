"""
RAG 评估数据集。

【为什么要有评估集？面试加分点】
- 没有评估集，所有"优化"都是凭感觉，不科学
- 评估集 = (文档, 问题, 标准答案/期望命中分块) 的三元组
- 业界标准做法：每次优化前后跑同一份评估集，对比指标

【指标说明】
- Recall@K: Top-K 召回中是否包含正确分块（最重要指标）
- MRR (Mean Reciprocal Rank): 正确答案的平均倒数排名（越靠前越好）
- 答案正确率: 人工/LLM-as-judge 判断答案是否回答正确
"""

EVAL_DOCUMENT = """
# AI 应用开发知识库（评估专用）

## 1. LangChain

LangChain 是一个用于构建大语言模型应用的开源框架，由 Harrison Chase 于 2022 年 10 月创建。
LangChain 的核心理念是组合性：把 LLM、Prompt、Memory、Retriever、Tool 等组件像乐高一样组合起来。
最新主版本是 LangChain 1.x，于 2025 年发布，全面采用 LCEL 作为默认抽象。

## 2. LCEL

LCEL 全称 LangChain Expression Language，是 LangChain 的链式表达语言。
LCEL 使用管道符 `|` 把组件串联，例如 `prompt | llm | parser`。
LCEL 的核心抽象是 Runnable 接口，所有组件都必须实现 invoke / stream / batch / async 等方法。
LCEL 链路天然支持流式输出（streaming）和并发执行（RunnableParallel）。

## 3. RAG

RAG（Retrieval-Augmented Generation，检索增强生成）是一种典型的大模型应用模式。
RAG 工作流程分为三步：1) 检索（Retrieval）从知识库中查找相关文档；
2) 增强（Augmented）把找到的内容拼接到 Prompt 上下文中；3) 生成（Generation）让 LLM 基于上下文回答。
RAG 的两大优势：解决幻觉问题，使用最新私域知识。

## 4. 向量数据库 Milvus

Milvus 是开源的向量数据库，专为大规模向量相似度检索设计，由 Zilliz 团队开发。
Milvus 支持的索引类型包括 HNSW、IVF_FLAT、IVF_SQ8、DiskANN 等。
HNSW 索引在召回率和查询速度之间取得最好平衡，是生产环境推荐选择。
Milvus 支持的距离度量：COSINE（余弦相似度）、L2（欧氏距离）、IP（内积）。

## 5. Embedding 模型

text-embedding-v3 是阿里云通义实验室发布的 Embedding 模型，输出 1024 维向量。
BGE-M3 是北京智源研究院开源的多语言 Embedding 模型，支持稠密向量、稀疏向量、多向量三种模式。
Embedding 模型的核心作用是把文本转换成数值向量，让语义相近的文本在向量空间中距离更近。

## 6. LangGraph 与 Agent

LangGraph 是 LangChain 团队推出的智能体（Agent）编排框架，基于状态图（StateGraph）实现。
LangGraph 适合构建多步骤、需要循环或人工介入的复杂 Agent 工作流，如客服机器人、自动编程助手等。
Agent 的核心能力是工具调用（Function Calling），LLM 自主决定何时调用哪个工具。
"""

# 评估问题集：每个 question 对应一个 expected_keyword（必须在召回的分块中出现）
EVAL_QUESTIONS: list[dict] = [
    {
        "question": "LangChain 是谁创建的？",
        "expected_keywords": ["Harrison Chase"],
        "topic": "LangChain",
    },
    {
        "question": "LCEL 中用什么符号串联组件？",
        "expected_keywords": ["管道符", "|"],
        "topic": "LCEL",
    },
    {
        "question": "RAG 的工作流程是什么？",
        "expected_keywords": ["检索", "增强", "生成"],
        "topic": "RAG",
    },
    {
        "question": "Milvus 推荐使用哪种索引？",
        "expected_keywords": ["HNSW"],
        "topic": "Milvus",
    },
    {
        "question": "text-embedding-v3 输出多少维向量？",
        "expected_keywords": ["1024"],
        "topic": "Embedding",
    },
    {
        "question": "LangGraph 基于什么实现？",
        "expected_keywords": ["状态图", "StateGraph"],
        "topic": "Agent",
    },
    {
        "question": "BGE-M3 支持哪几种向量模式？",
        "expected_keywords": ["稠密", "稀疏", "多向量"],
        "topic": "Embedding",
    },
    {
        "question": "Agent 的核心能力是什么？",
        "expected_keywords": ["工具调用", "Function Calling"],
        "topic": "Agent",
    },
    # 故意问得"绕"一些，考察语义检索能力
    {
        "question": "为什么大模型会胡说八道，怎么解决？",  # 测试语义匹配（"幻觉"）
        "expected_keywords": ["幻觉"],
        "topic": "RAG",
    },
    {
        "question": "在向量库里怎么衡量两个向量的相似度？",  # 测试语义匹配（"距离度量"）
        "expected_keywords": ["COSINE", "余弦"],
        "topic": "Milvus",
    },
]
