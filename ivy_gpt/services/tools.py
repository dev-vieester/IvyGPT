import math
from contextvars import ContextVar, Token

from langchain_core.tools import tool
from langchain_community.tools import (
    ArxivQueryRun,
    DuckDuckGoSearchResults,
    PubmedQueryRun,
    WikipediaQueryRun,
)
from langchain_community.utilities import (
    ArxivAPIWrapper,
    DuckDuckGoSearchAPIWrapper,
    PubMedAPIWrapper,
    WikipediaAPIWrapper,
)
from langchain_tavily import TavilySearch
from langchain_tavily._utilities import TavilySearchAPIWrapper
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession
import wikipedia

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

wikipedia.wikipedia.API_URL = "https://en.wikipedia.org/w/api.php"
wikipedia.wikipedia.USER_AGENT = "IvyGPT/0.1"

wikipedia_search = WikipediaQueryRun(
    api_wrapper=WikipediaAPIWrapper(
        top_k_results=3,
        doc_content_chars_max=1200
    )
)

arxiv_search = ArxivQueryRun(
    api_wrapper=ArxivAPIWrapper(
        top_k_results=3,
        doc_content_chars_max=1600
    )
)

pubmed_search = PubmedQueryRun(
    api_wrapper=PubMedAPIWrapper(
        top_k_results=3,
        doc_content_chars_max=1600
    )
)

duckduckgo_search = DuckDuckGoSearchResults(
    api_wrapper=DuckDuckGoSearchAPIWrapper(
        max_results=5,
        backend="duckduckgo"
    ),
    max_results=5,
    output_format="list"
)


def run_external_tool(tool_name: str, query: str, runnable) -> str:
    try:
        result = runnable.invoke(query)
    except Exception as e:
        return f"{tool_name} search failed: {str(e)}"

    if not result:
        return f"No {tool_name} results found."

    return str(result)


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
def search_wikipedia(query: str) -> str:
    """
    Search Wikipedia for concise encyclopedia-style background information.
    Use this for people, places, historical topics, concepts, and general factual summaries.
    Do not use it for current news or time-sensitive questions.
    """

    return run_external_tool("Wikipedia", query, wikipedia_search)


@tool
def search_arxiv(query: str) -> str:
    """
    Search arXiv for academic papers and technical research summaries.
    Use this for AI, machine learning, physics, math, computer science, and research-paper questions.
    """

    return run_external_tool("arXiv", query, arxiv_search)


@tool
def search_pubmed(query: str) -> str:
    """
    Search PubMed for biomedical and life-sciences research summaries.
    Use this for medical research, biology, clinical studies, and health-science literature.
    Do not provide medical diagnosis; summarize sources and advise professional consultation when appropriate.
    """

    return run_external_tool("PubMed", query, pubmed_search)


@tool
def search_duckduckgo(query: str) -> str:
    """
    Search the public web using DuckDuckGo as a fallback general web search.
    Use this when Tavily is unavailable, quota-limited, or when broad web results are enough.
    Prefer Tavily for current events when it is available.
    """

    return run_external_tool("DuckDuckGo", query, duckduckgo_search)


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
    search_wikipedia,
    search_arxiv,
    search_pubmed,
    search_duckduckgo,
    remember_this,
    recall_memory,
    web_search
]
