"""Shared test fixtures for the AffectLearn backend test suite."""

import pytest
import pytest_asyncio
from collections.abc import AsyncGenerator
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.deps import get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.base import Base
from app.models.course import Course, Module, Lesson, Section
from app.models.enrollment import Enrollment
from app.models.user import Role, User
# Imported so create_all builds their tables (registered on Base):
from app.models.learner_profile import LearnerProfile  # noqa: F401  (Story 4.5)
from app.models.research_event import ResearchEvent  # noqa: F401  (Story 4.7)
from app.models.study_group import StudyGroup  # noqa: F401  (Story 6.1)
from app.models.study_phase import StudyPhase  # noqa: F401  (Story 6.1)
from app.models.questionnaire_response import QuestionnaireResponse  # noqa: F401  (Story 6.3)
from app.models.survey_response import SurveyResponse  # noqa: F401  (Story 6.4)

DATABASE_URL = "sqlite+aiosqlite:///:memory:"

_engine = create_async_engine(DATABASE_URL, connect_args={"check_same_thread": False})
_TestSession = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture(autouse=True)
async def setup_database():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture(autouse=True)
def _reset_fusion_buffer():
    """Story 4.4c: the fusion pairing buffer is module-global; reset it between tests
    so a unimodal result from one test never pairs into another's cycle."""
    from app.services import fusion_buffer

    fusion_buffer._reset()
    yield
    fusion_buffer._reset()


@pytest_asyncio.fixture
async def db() -> AsyncGenerator[AsyncSession, None]:
    async with _TestSession() as session:
        yield session


@pytest_asyncio.fixture
async def client(db: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def test_user(db: AsyncSession) -> User:
    user = User(
        email_address="learner@test.com",
        password_hash=hash_password("Password1!"),
        first_name="Test",
        last_name="Learner",
        role=Role.learner,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_designer(db: AsyncSession) -> User:
    user = User(
        email_address="designer@test.com",
        password_hash=hash_password("Password1!"),
        first_name="Test",
        last_name="Designer",
        role=Role.course_designer,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_admin(db: AsyncSession) -> User:
    user = User(
        email_address="admin@test.com",
        password_hash=hash_password("Password1!"),
        first_name="Test",
        last_name="Admin",
        role=Role.admin,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.fixture
def auth_headers(test_user: User) -> dict:
    token = create_access_token(str(test_user.id))
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def designer_headers(test_designer: User) -> dict:
    token = create_access_token(str(test_designer.id))
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_headers(test_admin: User) -> dict:
    token = create_access_token(str(test_admin.id))
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def test_course(db: AsyncSession) -> Course:
    course = Course(title="Test Course", description="A test course", is_published=True)
    db.add(course)
    await db.commit()
    await db.refresh(course)
    return course


@pytest_asyncio.fixture
async def enrolled_course(db: AsyncSession, test_course: Course, test_user: User):
    """Course with 2 modules x 2 lessons x 3 sections each, plus enrollment."""
    sections = []
    for m_idx in range(2):
        module = Module(
            title=f"Module {m_idx + 1}",
            sort_order=m_idx,
            course_id=test_course.id,
        )
        db.add(module)
        await db.flush()
        for l_idx in range(2):
            lesson = Lesson(
                title=f"Lesson {m_idx + 1}.{l_idx + 1}",
                sort_order=l_idx,
                module_id=module.id,
            )
            db.add(lesson)
            await db.flush()
            for s_idx in range(3):
                section = Section(
                    title=f"Section {m_idx + 1}.{l_idx + 1}.{s_idx + 1}",
                    sort_order=s_idx,
                    lesson_id=lesson.id,
                )
                db.add(section)
                await db.flush()
                sections.append(section)

    enrollment = Enrollment(user_id=test_user.id, course_id=test_course.id)
    db.add(enrollment)
    await db.commit()
    await db.refresh(test_course)
    await db.refresh(enrollment)
    return {"course": test_course, "enrollment": enrollment, "sections": sections}
