from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.core.config import settings

# pool_pre_ping validates a pooled connection with a lightweight ping before each
# use, transparently replacing one Neon has dropped after idle (the cause of
# intermittent "connection is closed" 500s). pool_recycle retires connections older
# than 5 min so they never outlive Neon's idle timeout.
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_recycle=300,
)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
