from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ivy_gpt.db.crud import get_chat_history, list_conversations
from ivy_gpt.db.models import User
from ivy_gpt.db.session import get_db
from ivy_gpt.schemas.responses import (
    ChatHistoryResponse,
    ChatMessageResponse,
    ConversationListResponse,
    ConversationResponse
)
from ivy_gpt.services.auth import get_current_user


router = APIRouter()


@router.get("/conversations", response_model=ConversationListResponse)
async def conversations(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> ConversationListResponse:
    items = await list_conversations(db, current_user.id)

    return ConversationListResponse(
        conversations=[
            ConversationResponse.model_validate(item)
            for item in items
        ]
    )


@router.get("/history/{thread_id}", response_model=ChatHistoryResponse)
async def history(
    thread_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> ChatHistoryResponse:
    messages = await get_chat_history(db, current_user.id, thread_id)

    return ChatHistoryResponse(
        messages=[
            ChatMessageResponse.model_validate(message)
            for message in messages
        ]
    )
