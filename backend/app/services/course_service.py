"""Async CRUD service functions for course content hierarchy."""

import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.course import ContentBlock, Course, Lesson, Module, Section
from app.models.enrollment import Enrollment


# ---------------------------------------------------------------------------
# Course CRUD
# ---------------------------------------------------------------------------

async def create_course(db: AsyncSession, *, title: str, description: str | None = None,
                        estimated_duration_minutes: int | None = None, is_published: bool = False,
                        learning_objectives: str | None = None,
                        created_by: uuid.UUID | None = None) -> Course:
    # `created_by` is optional so `seed_courses.py` can keep creating system content with no
    # owner, which is what makes seeded courses admin-only (migration 024).
    course = Course(title=title, description=description,
                    estimated_duration_minutes=estimated_duration_minutes, is_published=is_published,
                    learning_objectives=learning_objectives, created_by=created_by)
    db.add(course)
    await db.commit()
    await db.refresh(course)
    return course


async def get_course(db: AsyncSession, course_id: uuid.UUID) -> Course:
    stmt = (
        select(Course)
        .where(Course.id == course_id)
        .options(
            selectinload(Course.modules)
            .selectinload(Module.lessons)
            .selectinload(Lesson.sections)
            .selectinload(Section.content_blocks)
        )
    )
    result = await db.execute(stmt)
    course = result.scalar_one_or_none()
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail={"error": {"code": "NOT_FOUND", "message": "Course not found"}})
    return course


async def list_courses(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    published_only: bool = False,
    search: str | None = None,
    learner_id: uuid.UUID | None = None,
) -> tuple[list[dict], int]:
    """List courses with optional filtering and learner enrollment annotation.

    Returns dicts (one per course) carrying the SQLAlchemy Course plus the
    annotation fields ``module_count``, ``is_enrolled``, ``enrollment_progress``.
    Designers/admins typically pass ``published_only=False`` and ``learner_id=None``.
    """
    filters = []
    if published_only:
        filters.append(Course.is_published.is_(True))
    if search:
        like = f"%{search}%"
        filters.append(or_(Course.title.ilike(like), Course.description.ilike(like)))

    count_stmt = select(func.count()).select_from(Course)
    for f in filters:
        count_stmt = count_stmt.where(f)
    total = (await db.execute(count_stmt)).scalar_one()

    module_count_subq = (
        select(Module.course_id, func.count(Module.id).label("module_count"))
        .group_by(Module.course_id)
        .subquery()
    )

    columns = [
        Course,
        func.coalesce(module_count_subq.c.module_count, 0).label("module_count"),
    ]
    if learner_id is not None:
        columns.append(Enrollment.id.label("enrollment_id"))
        columns.append(Enrollment.progress_percentage.label("progress_percentage"))

    stmt = select(*columns).outerjoin(
        module_count_subq, module_count_subq.c.course_id == Course.id
    )
    if learner_id is not None:
        stmt = stmt.outerjoin(
            Enrollment,
            (Enrollment.course_id == Course.id) & (Enrollment.user_id == learner_id),
        )
    for f in filters:
        stmt = stmt.where(f)
    stmt = (
        stmt.order_by(Course.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)

    items: list[dict] = []
    for row in result.all():
        course = row[0]
        module_count = row[1]
        item = {"course": course, "module_count": module_count}
        if learner_id is not None:
            enrollment_id = row[2]
            progress = row[3]
            item["is_enrolled"] = enrollment_id is not None
            item["enrollment_progress"] = progress if enrollment_id is not None else None
        items.append(item)
    return items, total


async def update_course(db: AsyncSession, course_id: uuid.UUID, **fields) -> Course:
    course = await _get_or_404(db, Course, course_id, "Course not found")
    for key, value in fields.items():
        setattr(course, key, value)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail={"error": {"code": "CONFLICT", "message": "Sort order already exists"}})
    await db.refresh(course)
    return course


async def delete_course(db: AsyncSession, course_id: uuid.UUID) -> None:
    course = await _get_or_404(db, Course, course_id, "Course not found")
    await db.delete(course)
    await db.commit()


# ---------------------------------------------------------------------------
# Module CRUD
# ---------------------------------------------------------------------------

async def create_module(db: AsyncSession, course_id: uuid.UUID, *, title: str,
                        description: str | None = None, sort_order: int) -> Module:
    await _get_or_404(db, Course, course_id, "Course not found")
    module = Module(title=title, description=description, sort_order=sort_order, course_id=course_id)
    db.add(module)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail={"error": {"code": "CONFLICT", "message": "Sort order already exists"}})
    await db.refresh(module)
    return module


async def list_modules(db: AsyncSession, course_id: uuid.UUID) -> list[Module]:
    await _get_or_404(db, Course, course_id, "Course not found")
    stmt = select(Module).where(Module.course_id == course_id).order_by(Module.sort_order)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def update_module(db: AsyncSession, module_id: uuid.UUID, **fields) -> Module:
    module = await _get_or_404(db, Module, module_id, "Module not found")
    for key, value in fields.items():
        setattr(module, key, value)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail={"error": {"code": "CONFLICT", "message": "Sort order already exists"}})
    await db.refresh(module)
    return module


async def delete_module(db: AsyncSession, module_id: uuid.UUID) -> None:
    module = await _get_or_404(db, Module, module_id, "Module not found")
    await db.delete(module)
    await db.commit()


# ---------------------------------------------------------------------------
# Lesson CRUD
# ---------------------------------------------------------------------------

async def create_lesson(db: AsyncSession, module_id: uuid.UUID, *, title: str,
                        description: str | None = None, sort_order: int) -> Lesson:
    await _get_or_404(db, Module, module_id, "Module not found")
    lesson = Lesson(title=title, description=description, sort_order=sort_order, module_id=module_id)
    db.add(lesson)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail={"error": {"code": "CONFLICT", "message": "Sort order already exists"}})
    await db.refresh(lesson)
    return lesson


async def list_lessons(db: AsyncSession, module_id: uuid.UUID) -> list[Lesson]:
    await _get_or_404(db, Module, module_id, "Module not found")
    stmt = select(Lesson).where(Lesson.module_id == module_id).order_by(Lesson.sort_order)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def update_lesson(db: AsyncSession, lesson_id: uuid.UUID, **fields) -> Lesson:
    lesson = await _get_or_404(db, Lesson, lesson_id, "Lesson not found")
    for key, value in fields.items():
        setattr(lesson, key, value)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail={"error": {"code": "CONFLICT", "message": "Sort order already exists"}})
    await db.refresh(lesson)
    return lesson


async def delete_lesson(db: AsyncSession, lesson_id: uuid.UUID) -> None:
    lesson = await _get_or_404(db, Lesson, lesson_id, "Lesson not found")
    await db.delete(lesson)
    await db.commit()


#: The variant every learner sees unless the adaptation loop swaps one in. A block created
#: without an explicit key gets this, so pre-variant content keeps working untouched.
ORIGINAL_VARIANT = "original"


async def get_lesson_detail(
    db: AsyncSession, lesson_id: uuid.UUID, *, originals_only: bool = False
) -> Lesson:
    """Return a lesson with its sections and content blocks eagerly loaded.

    `originals_only` filters to `variant_key == "original"` and is what the LEARNER reader passes.
    Without it every authored alternative — the simpler explanation, the harder variant — would
    render inline alongside the block it is an alternative TO, so a section with two variants
    would read as the same idea explained twice in a row.

    Designers get the unfiltered tree, because they are the ones authoring the alternatives and
    need to see that they exist.
    """
    blocks = selectinload(Lesson.sections).selectinload(Section.content_blocks)
    if originals_only:
        blocks = selectinload(Lesson.sections).selectinload(
            Section.content_blocks.and_(ContentBlock.variant_key == ORIGINAL_VARIANT)
        )

    stmt = select(Lesson).where(Lesson.id == lesson_id).options(blocks)
    lesson = (await db.execute(stmt)).scalar_one_or_none()
    if lesson is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "NOT_FOUND", "message": "Lesson not found"}},
        )
    return lesson


# ---------------------------------------------------------------------------
# Section CRUD
# ---------------------------------------------------------------------------

async def create_section(db: AsyncSession, lesson_id: uuid.UUID, *, title: str,
                         sort_order: int, estimated_duration_minutes: int | None = 5) -> Section:
    await _get_or_404(db, Lesson, lesson_id, "Lesson not found")
    section = Section(title=title, sort_order=sort_order,
                      estimated_duration_minutes=estimated_duration_minutes, lesson_id=lesson_id)
    db.add(section)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail={"error": {"code": "CONFLICT", "message": "Sort order already exists"}})
    await db.refresh(section)
    return section


async def list_sections(db: AsyncSession, lesson_id: uuid.UUID) -> list[Section]:
    await _get_or_404(db, Lesson, lesson_id, "Lesson not found")
    stmt = select(Section).where(Section.lesson_id == lesson_id).order_by(Section.sort_order)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def update_section(db: AsyncSession, section_id: uuid.UUID, **fields) -> Section:
    section = await _get_or_404(db, Section, section_id, "Section not found")
    for key, value in fields.items():
        setattr(section, key, value)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail={"error": {"code": "CONFLICT", "message": "Sort order already exists"}})
    await db.refresh(section)
    return section


async def delete_section(db: AsyncSession, section_id: uuid.UUID) -> None:
    section = await _get_or_404(db, Section, section_id, "Section not found")
    await db.delete(section)
    await db.commit()


# ---------------------------------------------------------------------------
# ContentBlock CRUD
# ---------------------------------------------------------------------------

async def create_content_block(db: AsyncSession, section_id: uuid.UUID, *, block_type: str,
                               content: dict, sort_order: int, variant_key: str = "original",
                               variant_group: uuid.UUID | None = None) -> ContentBlock:
    await _get_or_404(db, Section, section_id, "Section not found")
    block = ContentBlock(
        block_type=block_type, content=content, sort_order=sort_order,
        variant_key=variant_key, section_id=section_id,
    )
    if variant_group is not None:
        block.variant_group = variant_group
    db.add(block)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail={"error": {"code": "CONFLICT", "message": "Sort order already exists"}})
    await db.refresh(block)
    return block


async def list_content_blocks(
    db: AsyncSession, section_id: uuid.UUID, *, originals_only: bool = False
) -> list[ContentBlock]:
    await _get_or_404(db, Section, section_id, "Section not found")
    stmt = select(ContentBlock).where(ContentBlock.section_id == section_id)
    if originals_only:
        stmt = stmt.where(ContentBlock.variant_key == ORIGINAL_VARIANT)
    result = await db.execute(stmt.order_by(ContentBlock.sort_order))
    return list(result.scalars().all())


async def list_block_variants(
    db: AsyncSession, block_id: uuid.UUID
) -> list[ContentBlock]:
    """Every block sharing this one's `variant_group`, the original first.

    Variants live in the same section as the block they alternate for and are distinguished by
    `variant_key`; the group id is what ties a family together.
    """
    block = await _get_or_404(db, ContentBlock, block_id, "Content block not found")
    stmt = (
        select(ContentBlock)
        .where(ContentBlock.variant_group == block.variant_group)
        .order_by(ContentBlock.variant_key != ORIGINAL_VARIANT, ContentBlock.variant_key)
    )
    return list((await db.execute(stmt)).scalars().all())


async def upsert_block_variant(
    db: AsyncSession,
    block_id: uuid.UUID,
    *,
    variant_key: str,
    content: dict,
) -> ContentBlock:
    """Create or replace one alternative of `block_id`.

    Idempotent on `(variant_group, variant_key)`. The loop selects a variant BY KEY, so allowing
    two blocks to answer to the same key would make which one a learner receives arbitrary — and
    a designer editing "the simpler version" twice plainly means to edit it, not to fork it.

    The variant inherits the original's section, block type and sort order: it is a substitute for
    that block in that position, not a new piece of content elsewhere in the lesson.
    """
    original = await _get_or_404(db, ContentBlock, block_id, "Content block not found")

    existing = (
        await db.execute(
            select(ContentBlock).where(
                ContentBlock.variant_group == original.variant_group,
                ContentBlock.variant_key == variant_key,
            )
        )
    ).scalars().first()

    if existing is not None:
        existing.content = content
        await db.commit()
        await db.refresh(existing)
        return existing

    variant = ContentBlock(
        block_type=original.block_type,
        content=content,
        sort_order=original.sort_order,
        variant_key=variant_key,
        section_id=original.section_id,
    )
    variant.variant_group = original.variant_group
    db.add(variant)
    await db.commit()
    await db.refresh(variant)
    return variant


async def find_variant(
    db: AsyncSession, *, section_id: uuid.UUID | str, variant_key: str
) -> ContentBlock | None:
    """The authored `variant_key` alternative in this section, if one exists.

    This is the read the adaptation loop makes before falling back to generated text. It returns
    None rather than raising: no authored variant is the ordinary case, not an error.

    ACCEPTS A STRING ID ON PURPOSE. The only caller in the loop reads `section_id` out of
    `content_context`, which stores it as `str(section_id)` — so the value arriving here is a
    string, while `content_blocks.section_id` is a UUID column. Comparing the two raises inside
    the driver, and because the calling node swallows exceptions to satisfy NFR22, the failure
    would have surfaced as "no variant was ever authored" rather than as an error: the feature
    silently never selecting anything. Coercing here fixes it for every caller at once.
    """
    if isinstance(section_id, str):
        try:
            section_id = uuid.UUID(section_id)
        except ValueError:
            # A malformed id matches nothing. Returning None keeps the caller on its existing
            # fallback path rather than raising inside the agent loop.
            return None

    stmt = (
        select(ContentBlock)
        .where(
            ContentBlock.section_id == section_id,
            ContentBlock.variant_key == variant_key,
        )
        .order_by(ContentBlock.sort_order)
        .limit(1)
    )
    return (await db.execute(stmt)).scalars().first()


async def update_content_block(db: AsyncSession, block_id: uuid.UUID, **fields) -> ContentBlock:
    block = await _get_or_404(db, ContentBlock, block_id, "Content block not found")
    for key, value in fields.items():
        setattr(block, key, value)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail={"error": {"code": "CONFLICT", "message": "Sort order already exists"}})
    await db.refresh(block)
    return block


async def delete_content_block(db: AsyncSession, block_id: uuid.UUID) -> None:
    block = await _get_or_404(db, ContentBlock, block_id, "Content block not found")
    await db.delete(block)
    await db.commit()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_or_404(db: AsyncSession, model, entity_id: uuid.UUID, message: str):
    result = await db.execute(select(model).where(model.id == entity_id))
    entity = result.scalar_one_or_none()
    if entity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail={"error": {"code": "NOT_FOUND", "message": message}})
    return entity
