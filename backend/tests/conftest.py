import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.deps import get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.base import Base
from app.models.user import Role, User

# Use SQLite async for testing (aiosqlite)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSession = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(autouse=True)
async def setup_database():
    """Create all tables before each test, drop after."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def override_get_db():
    async with TestSession() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture
async def test_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
async def db_session():
    async with TestSession() as session:
        yield session


@pytest.fixture
async def test_user(db_session: AsyncSession):
    """Pre-created learner user for testing."""
    user = User(
        id=uuid.uuid4(),
        email_address="learner@test.com",
        password_hash=hash_password("TestPass123!"),
        first_name="Test",
        last_name="Learner",
        role=Role.learner,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def test_designer(db_session: AsyncSession):
    """Pre-created designer user for testing."""
    user = User(
        id=uuid.uuid4(),
        email_address="designer@test.com",
        password_hash=hash_password("TestPass123!"),
        first_name="Test",
        last_name="Designer",
        role=Role.course_designer,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def test_admin(db_session: AsyncSession):
    """Pre-created admin user for testing."""
    user = User(
        id=uuid.uuid4(),
        email_address="admin@test.com",
        password_hash=hash_password("TestPass123!"),
        first_name="Test",
        last_name="Admin",
        role=Role.admin,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def auth_headers(test_user):
    """Auth headers with valid access token for test_user."""
    token = create_access_token(str(test_user.id))
    return {"Authorization": f"Bearer {token}"}
