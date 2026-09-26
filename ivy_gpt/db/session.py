from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ivy_gpt.config import settings


def get_database_url() -> str:
    return settings.async_database_url


DATABASE_URL = get_database_url()

engine = create_async_engine(
    DATABASE_URL
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False
)


async def init_db() -> None:
    return None


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
