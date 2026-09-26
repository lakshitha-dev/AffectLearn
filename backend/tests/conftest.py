"""Shared test fixtures for the AffectLearn backend test suite."""

import pytest
import pytest_asyncio
from collections.abc import AsyncGenerator
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from app.core.deps import get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.base import Base
from app.models.course import Course, Module, Lesson, Section
from app.models.enrollment import Enrollment
from app.models.user import Role, User
# Imported so create_all builds their tables (registered on Base):
from app.models.email_token import EmailToken  # noqa: F401  (email verification + reset)
from app.models.learner_profile import LearnerProfile  # noqa: F401  (Story 4.5)
from app.models.research_event import ResearchEvent  # noqa: F401  (Story 4.7)
from app.models.study_group import StudyGroup  # noqa: F401  (Story 6.1)
from app.models.study_phase import StudyPhase  # noqa: F401  (Story 6.1)
from app.models.questionnaire_response import QuestionnaireResponse  # noqa: F401  (Story 6.3)
from app.models.survey_response import SurveyResponse  # noqa: F401  (Story 6.4)

DATABASE_URL = "sqlite+aiosqlite:///:memory:"


# The models declare `postgresql.UUID`, which SQLite renders as a column of type `UUID` — a name
# SQLite does not recognise, so the column gets NUMERIC affinity. A UUID's hex text is then
# converted to a number whenever it happens to look like one ("4721e9038..." is 4721 x 10^9038,
# stored as `inf`), and reading the row back fails. Roughly one UUID in a million looks like
# that: invisible in small tests, and a periodic CI failure once a test writes a few thousand
# rows (`test_seed_demo.py`). CHAR(32) is what SQLAlchemy's own generic UUID type uses here,
# and TEXT affinity stores the value as written. Postgres has a native UUID and is unaffected.
@compiles(PG_UUID, "sqlite")
def _uuid_as_text_on_sqlite(type_, compiler, **kw):
    return "CHAR(32)"


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


@pytest.fixture(autouse=True)
def _fresh_config_cache():
    """Drop the runtime-config cache around every test.

    `config_service` caches the effective configuration in a module global and rebuilds it from
    the `edges` constants on demand. Tests that monkeypatch those constants would otherwise be
    read through a cache built by an EARLIER test, so a threshold patch would silently not apply
    and the failure would look like a gate bug.
    """
    from app.services import config_service

    config_service._reset()
    yield
    config_service._reset()


@pytest.fixture(autouse=True)
def _no_trial_withholding():
    """Turn the randomised-trial draw OFF by default.

    `ADAPT_WITHHOLD_RATE` withholds ~35% of otherwise-eligible cycles so the study has a matched
    control arm. That is correct in production and wrong as a default in tests: every existing
    test that asserts "these conditions produce an adaptation" would fail on roughly a third of
    its inputs, depending on nothing but the learner/session/cycle ids it happened to pick, and
    the failure would look like a gate bug rather than a coin flip.

    Tests that are ABOUT the trial set the rate themselves -- see tests/agents/test_withholding.py,
    which covers the draw, the arms, and cooldown parity between them.
    """
    from app.agents import edges

    original = edges.ADAPT_WITHHOLD_RATE
    edges.ADAPT_WITHHOLD_RATE = 0.0
    yield
    edges.ADAPT_WITHHOLD_RATE = original


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
        email_verified=True,
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
        email_verified=True,
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
        email_verified=True,
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
async def test_course(db: AsyncSession, test_designer: User) -> Course:
    """A published course OWNED by `test_designer`.

    Ownership matters now that content mutations are scoped: a course with `created_by = NULL` is
    system content that only an admin may edit (see `course_ownership`), so leaving this fixture
    unowned would mean `designer_headers` could not author against it — which is a property of
    seeded pilot content, not of the ordinary designer flows these tests exercise.

    `test_course_ownership.py` builds its own courses and does not use this fixture, so the
    unowned/system case stays covered there.
    """
    course = Course(
        title="Test Course",
        description="A test course",
        is_published=True,
        created_by=test_designer.id,
    )
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
