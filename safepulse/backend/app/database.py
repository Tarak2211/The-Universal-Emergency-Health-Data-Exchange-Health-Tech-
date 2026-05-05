import logging
from sqlalchemy.ext.asyncio import (
    create_async_engine, AsyncSession, async_sessionmaker, AsyncEngine
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool, AsyncAdaptedQueuePool
from app.config import settings

logger = logging.getLogger(__name__)

def _build_engine() -> AsyncEngine:
    is_sqlite = "sqlite" in settings.DATABASE_URL

    if is_sqlite:
        # SQLite: single-file, no pool needed
        return create_async_engine(
            settings.DATABASE_URL,
            echo=settings.ENVIRONMENT == "development",
            connect_args={"check_same_thread": False},
            poolclass=NullPool,   # no pool for SQLite — avoids threading issues
        )
    else:
        # PostgreSQL: full connection pool for high concurrency
        return create_async_engine(
            settings.DATABASE_URL,
            echo=False,
            pool_size=settings.DB_POOL_SIZE,
            max_overflow=settings.DB_MAX_OVERFLOW,
            pool_timeout=settings.DB_POOL_TIMEOUT,
            pool_recycle=settings.DB_POOL_RECYCLE,
            pool_pre_ping=True,   # test connections before use — prevents stale conn errors
        )

engine = _build_engine()

AsyncSessionLocal = async_sessionmaker(
    engine,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)

class Base(DeclarativeBase):
    pass

async def get_db() -> AsyncSession:
    """Dependency — yields a DB session, always closes it."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

async def init_db():
    """Create all tables on startup (idempotent)."""
    try:
        async with engine.begin() as conn:
            from app import models  # noqa — registers all ORM models
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables initialised successfully")
    except Exception as e:
        logger.error(f"Database init failed: {e}")
        raise

async def close_db():
    """Dispose engine on shutdown — releases all connections."""
    await engine.dispose()
    logger.info("Database connections closed")
