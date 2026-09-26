from datetime import datetime

from pydantic import BaseModel


class ConversationResponse(BaseModel):
    thread_id: str
    title: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConversationListResponse(BaseModel):
    conversations: list[ConversationResponse]


class ChatMessageResponse(BaseModel):
    role: str
    content: str

    model_config = {"from_attributes": True}


class ChatHistoryResponse(BaseModel):
    messages: list[ChatMessageResponse]


class UploadResponse(BaseModel):
    success: bool
    message: str


class ErrorResponse(BaseModel):
    error: str
