from datetime import datetime
from pathlib import Path

from sqlalchemy.dialects.sqlite import DATETIME, TEXT
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Mapped, mapped_column
from sqlalchemy import create_engine, String
from dotenv import load_dotenv
import os
import uuid


load_dotenv()
Path("data").mkdir(exist_ok=True)

engine = create_engine(
    os.getenv("DATABASE_URL"),
    connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

class Base(DeclarativeBase):
    pass

class Conversation(Base):
    __tablename__ = "conversation"

    id: Mapped[str] = mapped_column(String, primary_key=True, index=True, default=lambda :str(uuid.uuid4()))
    thread_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    title: Mapped[str] = mapped_column(String, default="New Chat")
    created_at: Mapped[datetime] = mapped_column(DATETIME, default=datetime.utcnow())
    updated_at: Mapped[datetime] = mapped_column(DATETIME, default=datetime.utcnow())

class ChatMessage(Base):
    __tablename__ = "chat_message"

    id: Mapped[str] = mapped_column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    thread_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    role: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(TEXT)
    created_at: Mapped[str] = mapped_column(DATETIME, default=datetime.utcnow())

class LongTermMemory(Base):
    __tablename__ = "long_term_memory"

    id: Mapped[str] = mapped_column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    thread_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    memory: Mapped[str] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(DATETIME, default=datetime.utcnow())

def init_db():
    Base.metadata.create_all(bind=engine)

def create_or_update_conversation(thread_id: str, first_message: str | None = None):
    db = SessionLocal()

    try:
        conversation = (
            db.query(Conversation)
            .filter(Conversation.thread_id == thread_id)
            .first()
        )
        if not conversation:
            title = "New Chat"

            if first_message:
                title = first_message.strip()[:40]
                if len(first_message.strip()) > 40:
                    title +="..."

            conversation = Conversation(
                thread_id=thread_id,
                title=title,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(conversation)
        else:
            conversation.updated_at = datetime.utcnow()

        db.commit()

    finally:
        db.close()

def list_conversations():
    db = SessionLocal()

    try:
        return (
            db.query(Conversation)
            .order_by(Conversation.updated_at.desc())
            .all()
        )
    finally:
        db.close()

def save_chat_message(thread_id: str, role: str, content: str):
    db = SessionLocal()

    try:
        msg = ChatMessage(
            thread_id=thread_id,
            role=role,
            content=content,
            created_at=datetime.utcnow()
        )
        db.add(msg)

        conversation = (
            db.query(Conversation)
            .filter(Conversation.thread_id == thread_id).first()
        )
        if conversation:
            conversation.updated_at = datetime.utcnow()

        db.commit()

    finally:
        db.close()

def get_chat_history(thread_id: str):
    db = SessionLocal()

    try:
        return (
            db.query(ChatMessage)
            .filter(ChatMessage.thread_id == thread_id)
            .order_by(ChatMessage.created_at.asc())
            .all()
        )

    finally:
        db.close()


def save_memory(thread_id: str, memory: str):
    db = SessionLocal()

    try:
        item = LongTermMemory(
            thread_id=thread_id,
            memory=memory,
            created_at=datetime.utcnow()
        )

        db.add(item)
        db.commit()

        return "Memory saved successfully."

    finally:
        db.close()

def search_memory(thread_id: str, query: str | None = None):
    db = SessionLocal()

    try:
        query_obj = (
            db.query(LongTermMemory)
            .filter(LongTermMemory.thread_id == thread_id)
        )

        if query:
            query_obj = query_obj.filter(
                LongTermMemory.memory.contains(query)
            )

        memories = (
            query_obj
            .order_by(LongTermMemory.created_at.desc())
            .limit(20)
            .all()
        )

        if not memories:
            return "No saved memory found."

        return "\n".join([f"- {m.memory}" for m in memories])

    finally:
        db.close()