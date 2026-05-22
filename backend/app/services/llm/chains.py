"""
LangChain LCEL 链路定义。

LCEL（LangChain Expression Language）是 LangChain 的核心抽象，
通过 `|` 管道符把组件串成一个 Runnable。

【面试必讲】LCEL 的好处：
1. 统一接口：所有组件都是 Runnable，都支持 invoke/stream/batch/ainvoke/astream
2. 自动并行：RunnableParallel 会并发执行
3. 自动流式：链路中只要 LLM 支持流式，整个链路就支持流式
4. 易于调试：可以单独 invoke 任何子链路
5. 可观测性：天然支持 callbacks，对接 Langfuse 不用改代码
"""

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import Runnable

from app.services.llm.chat_model import get_chat_model

CHAT_SYSTEM_PROMPT = """你是一个专业、友好的 AI 助手，名叫"小智"。

你的能力：
- 回答各类知识性问题
- 帮助用户解决编程、写作、学习等问题
- 在不确定时坦诚说明，不会胡编乱造

回答要求：
- 使用 Markdown 格式
- 中文回答，简洁清晰
- 涉及代码时使用代码块
"""


def build_chat_chain() -> Runnable:
    """
    构建基础聊天链路：Prompt | LLM | OutputParser

    使用 MessagesPlaceholder 让链路支持多轮历史对话。

    使用方式：
        chain = build_chat_chain()
        # 同步调用
        result = chain.invoke({"history": [...], "input": "你好"})
        # 流式调用
        async for chunk in chain.astream({"history": [], "input": "你好"}):
            print(chunk, end="")
    """
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", CHAT_SYSTEM_PROMPT),
            MessagesPlaceholder(variable_name="history", optional=True),
            ("human", "{input}"),
        ]
    )

    llm = get_chat_model(temperature=0.7, streaming=True)
    parser = StrOutputParser()

    chain = prompt | llm | parser
    return chain
