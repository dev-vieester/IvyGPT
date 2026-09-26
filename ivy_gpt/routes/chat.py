import json
import logging
import re

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from sqlalchemy.ext.asyncio import AsyncSession

from ivy_gpt.core.agent import get_agent
from ivy_gpt.db.crud import create_or_update_conversation, save_chat_message
from ivy_gpt.db.models import User
from ivy_gpt.db.session import get_db
from ivy_gpt.schemas.responses import ErrorResponse
from ivy_gpt.services.auth import get_current_user
from ivy_gpt.services.tools import reset_tool_context, set_tool_context


router = APIRouter()
logger = logging.getLogger(__name__)

RATE_LIMIT_MESSAGE = (
    "The AI provider is receiving too many requests right now. "
    "Please wait a moment, then try again."
)


def sse_data(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def provider_rate_limit_retry_after(error: Exception) -> int | None:
    current: BaseException | None = error

    while current is not None:
        text = str(current).lower()

        if any(
            marker in text
            for marker in (
                "429",
                "rate limit",
                "ratelimit",
                "resource exhausted",
                "quota exceeded",
                "too many requests",
            )
        ):
            retry_match = re.search(r"retry[_ -]?delay[^0-9]*(\d+)", text)

            if retry_match:
                return int(retry_match.group(1))

            return 60

        current = current.__cause__ or current.__context__

    return None


def should_stream_chunk(chunk, metadata) -> bool:
    metadata = metadata or {}

    node_name = str(metadata.get("langgraph_node", "")).lower()

    if "tool" in node_name:
        return False

    if isinstance(chunk, ToolMessage):
        return False

    if not isinstance(chunk, (AIMessage, AIMessageChunk)):
        return False

    if getattr(chunk, "tool_calls", None):
        return False

    if getattr(chunk, "invalid_tool_calls", None):
        return False

    additional_kwargs = getattr(chunk, "additional_kwargs", {}) or {}

    if additional_kwargs.get("tool_calls"):
        return False

    return True


def extract_text_from_chunk(chunk) -> str:
    content = getattr(chunk, "content", "")

    if not content:
        return ""

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        text_parts = []

        for item in content:
            if isinstance(item, str):
                text_parts.append(item)

            elif isinstance(item, dict):
                if item.get("type") == "text" and isinstance(item.get("text"), str):
                    text_parts.append(item["text"])
                elif isinstance(item.get("text"), str):
                    text_parts.append(item["text"])
                elif isinstance(item.get("content"), str):
                    text_parts.append(item["content"])

        return "".join(text_parts)

    return ""


@router.post(
    "/chat/stream",
    responses={400: {"model": ErrorResponse}}
)
async def chat_stream(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        data = await request.json()
    except Exception:
        return JSONResponse(
            ErrorResponse(error="Invalid JSON body.").model_dump(),
            status_code=400
        )

    user_message = data.get("message", "")
    thread_id = data.get("thread_id", "default")
    selected_model = data.get("model", "gemini-2.5-flash")

    if not user_message.strip():
        return JSONResponse(
            ErrorResponse(error="Message is required.").model_dump(),
            status_code=400
        )

    agent = await get_agent(selected_model)

    await create_or_update_conversation(db, current_user.id, thread_id, user_message)
    await save_chat_message(db, current_user.id, thread_id, "user", user_message)

    config = {
        "configurable": {
            "thread_id": thread_id
        }
    }

    async def event_generator():
        final_answer = ""
        context_token = set_tool_context(thread_id, current_user.id, db)

        try:
            inputs = {
                "messages": [
                    HumanMessage(content=user_message)
                ]
            }

            async for chunk, metadata in agent.astream(
                inputs,
                config=config,
                stream_mode="messages"
            ):
                if not should_stream_chunk(chunk, metadata):
                    continue

                token = extract_text_from_chunk(chunk)

                if token:
                    final_answer += token
                    yield sse_data({"token": token})

            if final_answer.strip():
                await save_chat_message(db, current_user.id, thread_id, "assistant", final_answer)

            yield sse_data({"done": True})

        except Exception as e:
            retry_after = provider_rate_limit_retry_after(e)

            if retry_after is not None:
                logger.warning("LLM provider rate limit hit: %s", e)
                yield sse_data({
                    "error": RATE_LIMIT_MESSAGE,
                    "rate_limited": True,
                    "retry_after": retry_after,
                })
            else:
                logger.exception("Chat stream failed")
                yield sse_data({"error": "Something went wrong while generating a response. Please try again."})

            yield sse_data({"done": True})
        finally:
            reset_tool_context(context_token)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
