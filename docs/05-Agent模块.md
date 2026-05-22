# 05 · Agent 模块

> 让 LLM 自主决策、调用工具、多步推理。基于 LangGraph StateGraph 实现。

---

## 一、模块全景

```
backend/app/services/agent/
├── state.py    # AgentState（TypedDict）+ ToolCallRecord
├── tools.py    # 4 个工具：知识库 / Tavily / 计算 / 时间
└── graph.py    # StateGraph 编排 + TrackedToolNode + 流式入口
```

---

## 二、为什么需要 Agent

### 2.1 RAG 解决不了的场景

| 场景 | RAG 能否处理 | Agent 能否处理 |
|------|-------------|---------------|
| "合同里违约金条款？" | ✅ | ✅ |
| "今天北京天气怎样？" | ❌（知识库没有）| ✅（联网）|
| "1+1+...+100 等于几？" | ❌（LLM 容易算错）| ✅（计算器）|
| "结合知识库 + 联网" | ❌ | ✅ |

→ Agent 把"什么时候用什么工具"的决策交给 LLM 自己。

### 2.2 ReAct 模式

```
Reasoning + Acting 循环：
    Thought  → 我需要做什么？
    Action   → 调哪个工具？参数是什么？
    Observation → 工具返回结果
    Thought  → 拿到结果后下一步做什么？
    ...
    Final Answer
```

LangGraph 用 StateGraph 把这个循环结构化：节点 `agent`（Thought + Action）和节点 `tools`（执行 + Observation）来回跳转。

---

## 三、状态设计

```python
class AgentState(TypedDict):
    # LangGraph 的 add_messages reducer 自动追加新消息
    messages: Annotated[list[BaseMessage], add_messages]
    
    # 用户输入（用于工具上下文）
    question: str
    history: list[dict]
    selected_doc_ids: list[str] | None
    
    # 工具调用记录（给前端 Trace 用）
    tool_calls: list[ToolCallRecord]
    
    # 检索引用（给前端 Citation 用）
    citations: list[Citation]
    
    # 控制：迭代次数（防死循环）
    iterations: int
    final_answer: str | None
```

**关键：`add_messages` reducer**

```python
messages: Annotated[list[BaseMessage], add_messages]
```

LangGraph 会自动把节点 return 的新 messages **追加**到现有 messages，而不是覆盖。这是 LangGraph 的核心约定。

```python
# agent_node 只 return 新增的消息
return {"messages": [new_ai_message], "iterations": 1}
# state["messages"] 自动变成 [所有旧消息..., new_ai_message]
```

---

## 四、工具集

### 4.1 工具列表

| 名称 | 实现 | 用途 |
|------|------|------|
| `search_knowledge_base` | 调 RAG advanced_retrieve | 私有文档检索 |
| `web_search` | Tavily API（lazy load）| 联网搜索 |
| `calculator` | 沙箱 eval | 精确计算 |
| `get_current_time` | datetime | 当前时间 |

### 4.2 用 `@tool` 装饰器

```python
from langchain_core.tools import tool

@tool
async def search_knowledge_base(query: str) -> str:
    """
    在企业内部知识库中检索相关信息。
    适用场景：回答关于上传文档内容的问题...
    输入：要检索的查询文本（建议中文，10-50 字最佳）
    """
    ...
```

LangChain 自动把：
- 函数名 → 工具名
- docstring → 工具描述（**LLM 用这个决定要不要调用**）
- 类型注解 → 参数 schema（生成 Function Calling JSON）

### 4.3 LLM 怎么知道有哪些工具

```python
llm = get_chat_model().bind_tools([search_knowledge_base, web_search, ...])
```

`bind_tools` 把工具列表转成 OpenAI Function Calling schema，发给 LLM。LLM 在响应里如果有 `tool_calls`，框架就会触发工具执行。

### 4.4 优雅降级（Tavily 案例）

```python
@lru_cache(maxsize=1)
def _get_tavily_client():
    api_key = settings.tavily_api_key
    if not api_key:
        return None
    from tavily import TavilyClient
    return TavilyClient(api_key=api_key)


@tool
async def web_search(query: str) -> str:
    client = _get_tavily_client()
    if client is None:
        # 没 key 不让 Agent 崩，返回 mock 文本提醒用户配 key
        return f"（联网搜索功能未启用：未配置 TAVILY_API_KEY）..."
    
    try:
        # Tavily SDK 是同步的，包 to_thread
        data = await asyncio.to_thread(
            client.search,
            query=query,
            search_depth="basic",
            max_results=5,
            include_answer=True,
        )
        return _format_tavily_results(data)
    except Exception as e:
        return f"联网搜索失败：..."
```

**三层防御**：
1. 没配 key → mock 文本，提示用户
2. SDK 调用失败 → 友好错误信息
3. 全部异常 → 不抛出，返回字符串（Agent 可以读懂并选择换工具）

### 4.5 安全沙箱（calculator）

```python
@tool
def calculator(expression: str) -> str:
    # 字符级白名单
    allowed = set("0123456789+-*/(). %")
    for ch in expression:
        if ch not in allowed:
            return f"表达式包含非法字符 '{ch}'..."
    
    # eval 禁用 builtins
    result = eval(expression, {"__builtins__": {}}, {})
    return f"计算结果：{expression} = {result}"
```

防御点：
- 只允许数字 + 基本运算符
- `__builtins__: {}` 阻止 `import` / `open` / `__import__`

### 4.6 工具上下文（call_context）

`search_knowledge_base` 需要知道"要查哪几份文档"，但 LLM 决定调用工具时不会传这个参数（这是会话级上下文，不该让 LLM 操心）。

→ 用模块级 dict `_call_context` 在 Agent 启动前注入：

```python
# Agent 入口
set_call_context(
    selected_doc_ids=selected_doc_ids,
    collected_citations=[],
)

# 工具内部读
@tool
async def search_knowledge_base(query: str) -> str:
    document_ids = _call_context.get("selected_doc_ids")
    results = await advanced_retrieve(question=query, document_ids=document_ids)
    # 把检索结果存进 call_context，最后给前端
    _call_context.setdefault("collected_citations", []).extend(results)
```

> 注意：单进程多请求时 `_call_context` 会冲突。生产应改成 `contextvar.ContextVar`，本项目作为 v1 暂用全局 dict（FastAPI 单 worker 串行 await 阶段不冲突）。

---

## 五、StateGraph 编排

### 5.1 图结构

```
START
  │
  ↓
┌──────────┐
│  agent   │  ← LLM 决策（Thought + Action）
└────┬─────┘
     │
     ↓ 条件分支
   ┌─┴─┐
   │   │
 有  ↓   ↓ 无 tool_calls
 ┌─────┐  END
 │tools│
 └──┬──┘
    │
    └──→ 回到 agent（继续推理）
```

### 5.2 代码

```python
graph = StateGraph(AgentState)
graph.add_node("agent", agent_node)
graph.add_node("tools", TrackedToolNode(ALL_TOOLS))

graph.add_edge(START, "agent")
graph.add_conditional_edges(
    "agent",
    should_continue,           # 路由函数
    {"tools": "tools", END: END},  # 映射
)
graph.add_edge("tools", "agent")  # tools 完成后回 agent

compiled = graph.compile()
```

### 5.3 路由函数

```python
def should_continue(state: AgentState) -> str:
    if state.get("iterations", 0) >= MAX_ITERATIONS:
        return END
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return "tools"
    return END
```

### 5.4 防死循环

```python
MAX_ITERATIONS = 6

async def agent_node(state):
    iterations = state.get("iterations", 0)
    if iterations >= MAX_ITERATIONS:
        return {
            "messages": [AIMessage(content="（已达到最大思考轮数。请重新提问或简化问题。）")],
            "iterations": iterations + 1,
        }
    ...
```

为什么 6 次？经验值：
- 大部分查询 1-3 轮够用
- 留一些余量给"工具失败重试 + 综合回答"
- 太大会让用户等太久 + 烧 token

---

## 六、TrackedToolNode（关键创新）

LangGraph 自带的 `ToolNode` 只负责执行工具，但前端需要展示"思考过程"卡片。我们继承它，在执行前后埋点：

```python
class TrackedToolNode(ToolNode):
    async def ainvoke(self, input, config=None, **kwargs):
        last_msg = input["messages"][-1]
        tool_calls = getattr(last_msg, "tool_calls", []) or []
        
        # 记录每个 tool 的开始时间
        starts = {tc["id"]: time.perf_counter() for tc in tool_calls}
        
        # 父类执行
        result = await super().ainvoke(input, config=config, **kwargs)
        
        # 把 ToolMessage 转成 ToolCallRecord
        records = list(input.get("tool_calls", []))
        for msg in result.get("messages", []):
            if isinstance(msg, ToolMessage):
                tc_match = next((tc for tc in tool_calls if tc["id"] == msg.tool_call_id), None)
                if tc_match:
                    duration_ms = int((time.perf_counter() - starts[msg.tool_call_id]) * 1000)
                    summary = str(msg.content)[:200] + ("..." if len(str(msg.content)) > 200 else "")
                    records.append(ToolCallRecord(
                        tool_name=tc_match["name"],
                        arguments=tc_match.get("args", {}),
                        result_summary=summary,
                        duration_ms=duration_ms,
                    ))
        result["tool_calls"] = records
        return result
```

**带来什么？**
- 前端 `AgentTrace` 组件能拿到完整的工具调用列表
- 每个工具的执行时长可展示（性能调优用）
- 不影响主流程，纯增强

---

## 七、流式协议（精彩部分）

### 7.1 用 astream_events 而不是 astream

```python
async for event in graph.astream_events(initial_state, version="v2"):
    kind = event["event"]
    name = event["name"]
    ...
```

`astream_events` 比 `astream` 提供更细粒度的事件：
- `on_chain_start` / `on_chain_end`：节点开始 / 结束
- `on_chat_model_stream`：LLM 每个 token
- `on_tool_start` / `on_tool_end`：工具开始 / 结束

### 7.2 关键过滤：tool_call_chunks vs content

LangGraph 的 LLM 流式响应会推两种 chunk：

```python
# 当 LLM 决定调工具时
chunk.tool_call_chunks = [{"name": "calculator", "args": {"expression": "1+1"}}]
chunk.content = ""  # 这一阶段 content 是空的！

# 当 LLM 在生成最终回答时
chunk.tool_call_chunks = []
chunk.content = "答案是"  # 这才是要给用户看的文字
```

**坑**：如果不过滤，前端会看到 LLM "思考时的工具参数 JSON" 出现在聊天框里。

**解决**：

```python
if kind == "on_chat_model_stream":
    chunk = event["data"].get("chunk")
    if not isinstance(chunk, AIMessageChunk):
        continue
    
    # 跳过工具调用阶段的 chunk
    if chunk.tool_call_chunks:
        continue
    
    # 只推有 content 的 chunk（最终回答阶段）
    if chunk.content:
        yield {"type": "content", "content": chunk.content}
```

### 7.3 事件类型完整清单

| 事件 | 触发时机 | 前端行为 |
|------|---------|---------|
| `step` | 节点开始 | 状态条："Agent 思考中..." / "调用工具..." |
| `tool_call` | LLM 决定调工具 | AgentTrace 新增一行 |
| `tool_result` | 工具执行完 | AgentTrace 该行更新结果 |
| `content` | LLM 流式生成最终回答 | 聊天气泡追加 token |
| `citations` | RAG 工具被调用过 | 底部 Citation 卡片 |
| `done` | Agent 全部结束 | 关闭 SSE 连接 |

### 7.4 前端实现示意

```typescript
streamAgent({
  question, history, selectedDocIds,
  callbacks: {
    onStep: (node) => updateStatus(node),
    onToolCall: (tc) => addToolCallToLastAssistant(tc),
    onToolResult: (id, result) => updateToolCallResult(id, result),
    onContent: (text) => appendContentToLastAssistant(text),
    onCitations: (cs) => attachCitations(cs),
    onDone: () => setStreaming(false),
  },
})
```

---

## 八、典型对话样例

### 8.1 简单问题（无工具）

```
User: 你好
Agent: [agent_node] LLM 直接回答 → END
       Agent: 你好！有什么可以帮你的？
```

### 8.2 单工具

```
User: 现在几点？
Agent: [agent_node] LLM 决定调 get_current_time
       [tools]      执行，得到 "2026-05-15 20:32"
       [agent_node] LLM 综合回答 → END
       Agent: 现在是 2026 年 5 月 15 日 20:32。
```

### 8.3 多工具串联

```
User: 查一下今年北京 GDP，并算它占全国百分之几？

Agent:
  [agent_node] LLM 决定 → web_search("2026 北京 GDP")
  [tools]      → "北京 2025 GDP 约 4.8 万亿"
  [agent_node] LLM 决定 → web_search("2026 全国 GDP")
  [tools]      → "全国 2025 GDP 约 134 万亿"
  [agent_node] LLM 决定 → calculator("4.8 / 134 * 100")
  [tools]      → "3.58"
  [agent_node] LLM 综合回答 → END
       Agent: 北京 2025 年 GDP 约 4.8 万亿元，占全国 134 万亿元的约 3.58%。
              （来源：联网搜索）
```

### 8.4 RAG + 联网混合

```
User: 我们公司的产品规格，对比下竞品 X？

Agent:
  [tools] search_knowledge_base("公司产品规格")     → 文档片段 1, 2
  [tools] web_search("竞品 X 规格")                 → 联网结果
  [agent] 综合两路数据 → 最终回答（带 Citation [1] [2]）
```

---

## 九、性能数据

| 场景 | 延迟 |
|------|------|
| 简单问题（无工具） | ~700ms |
| 单工具（calculator）| ~1.5s |
| 单工具（web_search）| ~3s |
| 三工具串联 | ~6-8s |
| 多工具并行（同轮）| ~3-4s |

LLM 决策延迟（每次 agent_node 进出）：~600-1000ms。

---

## 十、System Prompt 设计

```
你是一个专业的 AI 助手，能够调用以下工具来帮助回答问题：

【可用工具】
- search_knowledge_base: 检索企业私有知识库
- web_search:           联网搜索最新信息
- calculator:           精确数学计算
- get_current_time:     获取当前日期时间

【决策原则】
1. 优先尝试 search_knowledge_base：如果问题可能与用户文档相关
2. 涉及"今天/现在/最新"等时效性问题：先调用 get_current_time
3. 涉及精确数字计算：必须用 calculator，不要自己心算
4. 知识库找不到 + 涉及外部信息：用 web_search 兜底
5. 简单常识问答（不需要工具）：直接回答即可
6. 一次性调用多个工具时使用并行调用
7. 综合所有工具结果，用中文 Markdown 给出最终答案
```

**为什么这样写？**

- 列出工具但**不重复 schema**（schema 已通过 `bind_tools` 注入）
- "不要自己心算"是关键 → LLM 经常会强行心算然后翻车
- "简单问答不要硬调用工具" → 防止 Agent 把所有问题都强转工具调用，浪费 token
- 鼓励并行 tool call（同一轮返回多个 tool_calls）→ 减少总耗时

---

## 十一、关键设计决策

| 决策 | 选了什么 | 拒绝了什么 | 原因 |
|------|---------|-----------|------|
| Agent 框架 | LangGraph | 自己写循环 / AutoGen | 状态机更清晰，工具调用框架成熟 |
| 工具定义 | @tool 装饰器 | 手写 JSON Schema | 自动从 docstring + type hint 生成 |
| 流式协议 | astream_events v2 | astream | 节点级事件更细 |
| 防死循环 | MAX_ITERATIONS=6 | 自动停止 | 显式 + 可调 |
| 工具上下文 | 模块级 dict | 加 LLM 参数 | LLM 不该管会话级参数 |
| Tavily 失败 | 优雅降级 mock | 抛异常 | 不阻断主流程 |
| 跟踪信息 | TrackedToolNode | 在外层手动埋点 | 内聚，不污染节点逻辑 |

---

## 十二、踩坑速查

| 现象 | 原因 | 解决 |
|------|------|------|
| 前端聊天框出现 `{"name":"calculator","args":{...}}` | 没过滤 tool_call_chunks | 检查 `chunk.tool_call_chunks` |
| Agent 死循环 | LLM 反复调同一个工具 | MAX_ITERATIONS + Prompt 要求"知识库找不到就停" |
| Tavily 报 `module not found` | 未装依赖或 key 缺失 | lazy import + 优雅降级 |
| 工具调用没有 trace | 用了原生 ToolNode | 用 `TrackedToolNode` 替换 |
| 多请求工具上下文串了 | 全局 dict | 改用 `contextvars.ContextVar`（待优化）|

---

## 十三、下一步阅读

- 想看 RAG 内部原理：[04-RAG模块.md](./04-RAG模块.md)
- 想看 Agent API 详情：[06-API文档.md](./06-API文档.md)
