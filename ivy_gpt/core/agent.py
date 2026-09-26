from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage
from langgraph.graph import StateGraph, START, MessagesState
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg import AsyncConnection
from psycopg.rows import dict_row
from sqlalchemy.ext.asyncio import AsyncSession
from ivy_gpt.services.tools import tools
from ivy_gpt.services.mcp_tools import get_mcp_tools
from ivy_gpt.config import settings

DEFAULT_MODEL = settings.default_model

ALLOWED_MODELS = {
    settings.openrouter_model
}

SYSTEM_PROMPT = """
You are a helpful Agentic AI assistant named IvyGPT similar to ChatGPT.

You can:
1. Answer normal questions.
2. Use tools when needed.
3. Search uploaded documents using the RAG tool.
4. Search the web for latest/current information using Tavily Search.
5. Search Wikipedia for stable encyclopedia-style background facts.
6. Search arXiv for academic and technical research papers.
7. Search PubMed for biomedical and life-sciences research.
8. Search DuckDuckGo as a fallback general web search.
9. Remember important user information using the memory tool.
10. Recall memory when useful.
11. Use calculator for math.
12. Use configured MCP tools when the user's request matches an MCP tool's purpose.

Rules:
- If the user asks about latest news, current events, recent updates, today's information, current prices, current people, current versions, new releases, or anything time-sensitive, use Tavily Search.
- If Tavily is unavailable or quota-limited, use DuckDuckGo for general web search.
- If the user asks for general background on a stable topic, use Wikipedia.
- If the user asks for papers, technical research, AI/ML research, math, physics, or computer science literature, use arXiv.
- If the user asks for biomedical or life-sciences research, use PubMed and avoid giving medical diagnosis.
- If the user asks about an uploaded document, use search_uploaded_documents.
- If the user asks you to remember something, use remember_this.
- If the user asks about previous preferences or saved facts, use recall_memory.
- Use calculator for math questions.
- Use MCP tools only when their name and description clearly match the user's request.
- When using web search, summarize clearly and mention that the answer is based on web search results.
- Be clear, helpful, and concise.
"""
tools = tools

def normalize_model_name(model_name: str | None) -> str:
    """
    Validate selected model from frontend.
    If model is missing or not allowed, fallback to DEFAULT_MODEL.
    """
    if not model_name:
        return DEFAULT_MODEL

    model_name = model_name.strip()

    if model_name not in ALLOWED_MODELS:
        return DEFAULT_MODEL

    return model_name

async def build_agent(
    model_name: str,
    user_id: str | None = None,
    db: AsyncSession | None = None
):
    """
    Build one LangGraph agent for the selected OpenRouter model.
    """
    selected_model = normalize_model_name(model_name)

    llm = ChatOpenAI(
        model=selected_model,
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        temperature=0.3,
        streaming=True
    )

    available_tools = tools + await get_mcp_tools(db=db, user_id=user_id)
    llm_with_tools = llm.bind_tools(available_tools)

    async def chatbot_node(state: MessagesState):
        messages = [
            SystemMessage(content=SYSTEM_PROMPT)
        ] + state["messages"]

        response = await llm_with_tools.ainvoke(messages)

        return {
            "messages": [response]
        }

    tool_node = ToolNode(available_tools)

    workflow = StateGraph(MessagesState)

    workflow.add_node("chatbot_node", chatbot_node)
    workflow.add_node("tools", tool_node)

    workflow.add_edge(START,"chatbot_node")
    workflow.add_conditional_edges("chatbot_node", tools_condition)
    workflow.add_edge("tools", "chatbot_node")

    conn = await AsyncConnection.connect(
        settings.postgres_checkpoint_url,
        autocommit=True,
        prepare_threshold=0,
        row_factory=dict_row
    )
    checkpointer = AsyncPostgresSaver(conn)
    await checkpointer.setup()

    return workflow.compile(checkpointer=checkpointer), conn

_AGENT_CACHE = {}
_CHECKPOINT_CONNECTIONS = {}


async def get_agent(
    model_name: str | None = None,
    user_id: str | None = None,
    db: AsyncSession | None = None
):
    """
    Return cached LangGraph agent for selected model.
    If not created yet, create it once and reuse it.
    """

    selected_model = normalize_model_name(model_name)

    cache_key = (selected_model, user_id)

    if cache_key not in _AGENT_CACHE:
        agent, conn = await build_agent(selected_model, user_id=user_id, db=db)
        _AGENT_CACHE[cache_key] = agent
        _CHECKPOINT_CONNECTIONS[cache_key] = conn

    return _AGENT_CACHE[cache_key]


async def clear_agent_cache_for_user(user_id: str) -> None:
    cache_keys = [
        cache_key
        for cache_key in _AGENT_CACHE
        if cache_key[1] == user_id
    ]

    for cache_key in cache_keys:
        conn = _CHECKPOINT_CONNECTIONS.pop(cache_key, None)

        if conn:
            await conn.close()

        _AGENT_CACHE.pop(cache_key, None)


async def close_agent_connections() -> None:
    for conn in _CHECKPOINT_CONNECTIONS.values():
        await conn.close()

    _CHECKPOINT_CONNECTIONS.clear()
    _AGENT_CACHE.clear()
