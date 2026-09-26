import math
from contextvars import ContextVar, Token

from langchain_core.tools import tool
from langchain_tavily import TavilySearch
from langchain_tavily._utilities import TavilySearchAPIWrapper
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from ivy_gpt.config import settings
from ivy_gpt.db.crud import save_memory, search_memory
from ivy_gpt.services.rag import retrieve_from_rag

CURRENT_THREAD_ID: ContextVar[str] = ContextVar("CURRENT_THREAD_ID", default="default")
CURRENT_USER_ID: ContextVar[str | None] = ContextVar("CURRENT_USER_ID", default=None)
CURRENT_DB_SESSION: ContextVar[AsyncSession | None] = ContextVar("CURRENT_DB_SESSION", default=None)


def set_tool_context(
    thread_id: str,
    user_id: str,
    db: AsyncSession
) -> tuple[Token[str], Token[str | None], Token[AsyncSession | None]]:
    thread_token = CURRENT_THREAD_ID.set(thread_id)
    user_token = CURRENT_USER_ID.set(user_id)
    db_token = CURRENT_DB_SESSION.set(db)

    return thread_token, user_token, db_token


def reset_tool_context(tokens: tuple[Token[str], Token[str | None], Token[AsyncSession | None]]) -> None:
    thread_token, user_token, db_token = tokens
    CURRENT_THREAD_ID.reset(thread_token)
    CURRENT_USER_ID.reset(user_token)
    CURRENT_DB_SESSION.reset(db_token)


def get_tool_db() -> AsyncSession:
    db = CURRENT_DB_SESSION.get()

    if db is None:
        raise RuntimeError("Database session is not available in the current tool context.")

    return db


def get_tool_user_id() -> str:
    user_id = CURRENT_USER_ID.get()

    if user_id is None:
        raise RuntimeError("User is not available in the current tool context.")

    return user_id


web_search_args = {
    "max_results": 5,
    "topic": "general",
    "search_depth": "advanced"
}

if settings.tavily_api_key:
    web_search_args["api_wrapper"] = TavilySearchAPIWrapper(
        tavily_api_key=SecretStr(settings.tavily_api_key)
    )

web_search = TavilySearch(**web_search_args)


@tool
def calculator(expression: str) -> str:
    """
    Useful for simple math calculations.
    Input should be a valid math expression.
    Example: 2 + 2, math.sqrt(16), 10 * 5
    """

    try:
        allowed = {
            "math": math,
            "abs": abs,
            "round": round,
            "min": min,
            "max": max,
            "sum": sum
        }

        result = eval(expression, {"__builtins__": {}}, allowed)
        return str(result)

    except Exception as e:
        return f"Calculation error: {str(e)}"


@tool
def search_uploaded_documents(query: str) -> str:
    """
    Search uploaded documents for relevant information.
    Use this when the user asks about uploaded PDFs, DOCX, TXT, notes, files, or documents.
    """

    return retrieve_from_rag(
        query=query,
        thread_id=CURRENT_THREAD_ID.get()
    )


@tool
async def remember_this(memory: str) -> str:
    """
    Save an important user preference or fact into long-term memory.
    Use this when the user asks you to remember something.
    """

    return await save_memory(
        db=get_tool_db(),
        user_id=get_tool_user_id(),
        thread_id=CURRENT_THREAD_ID.get(),
        memory=memory
    )


@tool
async def recall_memory(query: str) -> str:
    """
    Recall saved long-term memories about the user or this conversation.
    """

    return await search_memory(
        db=get_tool_db(),
        user_id=get_tool_user_id(),
        thread_id=CURRENT_THREAD_ID.get(),
        query=query
    )


tools = [
    calculator,
    search_uploaded_documents,
    remember_this,
    recall_memory,
    web_search
]
