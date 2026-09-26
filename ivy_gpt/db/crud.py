from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ivy_gpt.db.models import ChatMessage, Conversation, LongTermMemory, RefreshToken, User


async def create_or_update_conversation(
    db: AsyncSession,
    user_id: str,
    thread_id: str,
    first_message: str | None = None
) -> None:
    result = await db.execute(
        select(Conversation).where(
            Conversation.thread_id == thread_id,
            Conversation.user_id == user_id
        )
    )
    conversation = result.scalar_one_or_none()

    if not conversation:
        title = "New Chat"

        if first_message:
            title = first_message.strip()[:40]
            if len(first_message.strip()) > 40:
                title += "..."

        conversation = Conversation(
            user_id=user_id,
            thread_id=thread_id,
            title=title,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(conversation)
    else:
        conversation.updated_at = datetime.utcnow()

    await db.commit()


async def list_conversations(db: AsyncSession, user_id: str) -> list[Conversation]:
    result = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(Conversation.updated_at.desc())
    )
    return list(result.scalars().all())


async def save_chat_message(
    db: AsyncSession,
    user_id: str,
    thread_id: str,
    role: str,
    content: str
) -> None:
    msg = ChatMessage(
        user_id=user_id,
        thread_id=thread_id,
        role=role,
        content=content,
        created_at=datetime.utcnow()
    )
    db.add(msg)

    result = await db.execute(
        select(Conversation).where(
            Conversation.thread_id == thread_id,
            Conversation.user_id == user_id
        )
    )
    conversation = result.scalar_one_or_none()

    if conversation:
        conversation.updated_at = datetime.utcnow()

    await db.commit()


async def get_chat_history(db: AsyncSession, user_id: str, thread_id: str) -> list[ChatMessage]:
    result = await db.execute(
        select(ChatMessage)
        .where(
            ChatMessage.thread_id == thread_id,
            ChatMessage.user_id == user_id
        )
        .order_by(ChatMessage.created_at.asc())
    )
    return list(result.scalars().all())


async def save_memory(db: AsyncSession, user_id: str, thread_id: str, memory: str) -> str:
    item = LongTermMemory(
        user_id=user_id,
        thread_id=thread_id,
        memory=memory,
        created_at=datetime.utcnow()
    )

    db.add(item)
    await db.commit()

    return "Memory saved successfully."


async def search_memory(
    db: AsyncSession,
    user_id: str,
    thread_id: str,
    query: str | None = None
) -> str:
    stmt = select(LongTermMemory).where(
        LongTermMemory.thread_id == thread_id,
        LongTermMemory.user_id == user_id
    )

    if query:
        stmt = stmt.where(LongTermMemory.memory.contains(query))

    result = await db.execute(
        stmt.order_by(LongTermMemory.created_at.desc()).limit(20)
    )
    memories = result.scalars().all()

    if not memories:
        return "No saved memory found."

    return "\n".join([f"- {item.memory}" for item in memories])


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email.lower()))
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: str) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_user_by_google_sub(db: AsyncSession, google_sub: str) -> User | None:
    result = await db.execute(select(User).where(User.google_sub == google_sub))
    return result.scalar_one_or_none()


async def create_user(
    db: AsyncSession,
    email: str,
    name: str | None,
    age: int | None = None,
    provider: str = "email",
    google_sub: str | None = None
) -> User:
    user = User(
        email=email.lower(),
        name=name,
        age=age,
        provider=provider,
        google_sub=google_sub,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def update_user_profile(db: AsyncSession, user: User, name: str, age: int) -> User:
    user.name = name
    user.age = age
    user.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(user)
    return user


async def upsert_google_user(
    db: AsyncSession,
    email: str,
    name: str | None,
    google_sub: str
) -> User:
    user = await get_user_by_google_sub(db, google_sub)

    if user:
        user.email = email.lower()
        user.name = user.name or name
        user.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(user)
        return user

    user = await get_user_by_email(db, email)

    if user:
        user.google_sub = google_sub
        user.provider = "google"
        user.name = user.name or name
        user.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(user)
        return user

    return await create_user(
        db=db,
        email=email,
        name=name,
        provider="google",
        google_sub=google_sub
    )


async def create_refresh_token(
    db: AsyncSession,
    user_id: str,
    token_hash: str,
    expires_at: datetime
) -> RefreshToken:
    item = RefreshToken(
        user_id=user_id,
        token_hash=token_hash,
        expires_at=expires_at,
        created_at=datetime.utcnow()
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


async def get_refresh_token(db: AsyncSession, token_hash: str) -> RefreshToken | None:
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    return result.scalar_one_or_none()


async def revoke_refresh_token(db: AsyncSession, token_hash: str) -> None:
    token = await get_refresh_token(db, token_hash)

    if token:
        token.revoked = True
        await db.commit()
