from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage
from pydantic import SecretStr
from langgraph.graph import StateGraph, START, MessagesState
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg import AsyncConnection
from psycopg.rows import dict_row
from ivy_gpt.services.tools import tools
from ivy_gpt.config import settings

DEFAULT_MODEL = settings.default_model

ALLOWED_MODELS = {
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-2.5-flash-lite",  # Included the lite version if needed
    "gemini-1.5-flash",  # Kept for fallback compatibility
    "gemini-1.5-pro"
}

SYSTEM_PROMPT = """
You are a helpful Agentic AI assistant named IvyGPT similar to ChatGPT.

You can:
1. Answer normal questions.
2. Use tools when needed.
3. Search uploaded documents using the RAG tool.
4. Search the web for latest/current information using Tavily Search.
5. Remember important user information using the memory tool.
6. Recall memory when useful.
7. Use calculator for math.

Rules:
- If the user asks about latest news, current events, recent updates, today's information, current prices, current people, current versions, new releases, or anything time-sensitive, use Tavily Search.
- If the user asks about an uploaded document, use search_uploaded_documents.
- If the user asks you to remember something, use remember_this.
- If the user asks about previous preferences or saved facts, use recall_memory.
- Use calculator for math questions.
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

async def build_agent(model_name: str):
    """
    Build one LangGraph agent for a selected Gemini model
    """
    selected_model = normalize_model_name(model_name)

    llm = ChatGoogleGenerativeAI(
        model= selected_model,
        api_key=SecretStr(settings.google_api_key) if settings.google_api_key else None,
        temperature=0.3,
        streaming=True
    )

    llm_with_tools = llm.bind_tools(tools)

    async def chatbot_node(state: MessagesState):
        messages = [
            SystemMessage(content=SYSTEM_PROMPT)
        ] + state["messages"]

        response = await llm_with_tools.ainvoke(messages)

        return {
            "messages": [response]
        }

    tool_node = ToolNode(tools)

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


async def get_agent(model_name: str | None = None):
    """
    Return cached LangGraph agent for selected model.
    If not created yet, create it once and reuse it.
    """

    selected_model = normalize_model_name(model_name)

    if selected_model not in _AGENT_CACHE:
        agent, conn = await build_agent(selected_model)
        _AGENT_CACHE[selected_model] = agent
        _CHECKPOINT_CONNECTIONS[selected_model] = conn

    return _AGENT_CACHE[selected_model]


async def close_agent_connections() -> None:
    for conn in _CHECKPOINT_CONNECTIONS.values():
        await conn.close()

    _CHECKPOINT_CONNECTIONS.clear()
    _AGENT_CACHE.clear()
