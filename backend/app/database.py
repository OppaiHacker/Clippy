from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session, DeclarativeBase
from backend.app.config import settings

class Base(DeclarativeBase):
    pass

async_engine = create_async_engine(
    settings.database_url,
    echo=False,
    future=True,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

sync_engine = create_engine(
    settings.sync_database_url,
    echo=False,
    future=True,
    pool_size=5,
    max_overflow=10,
)

SyncSessionLocal = sessionmaker(
    bind=sync_engine,
    class_=Session,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

def get_sync_db() -> Session:
    return SyncSessionLocal()
