"""Course content API endpoints."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db, require_role
from app.models.user import Role, User
from app.schemas.course import (
    ContentBlockCreate,
    ContentBlockResponse,
    ContentBlockUpdate,
    ContentBlockVariantCreate,
    ContentVersionDetail,
    ContentVersionSummary,
    CourseCreate,
    CourseDetailResponse,
    CourseListResponse,
    CourseResponse,
    CourseUpdate,
    LessonCreate,
    LessonDetailResponse,
    LessonResponse,
    LessonUpdate,
    ModuleCreate,
    ModuleResponse,
    ModuleUpdate,
    SectionCreate,
    SectionResponse,
    SectionUpdate,
)
from app.services import content_version_service, course_ownership, course_service

router = APIRouter()


# ---------------------------------------------------------------------------
# Course endpoints
# ---------------------------------------------------------------------------

@router.post("", response_model=CourseResponse, status_code=status.HTTP_201_CREATED)
async def create_course(
    body: CourseCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.course_designer, Role.admin)),
):
    # An admin creating a course still owns it: leaving it NULL would make it system content
    # that even its own author could not edit as a designer later.
    course = await course_service.create_course(
        db, title=body.title, description=body.description,
        estimated_duration_minutes=body.estimated_duration_minutes, is_published=body.is_published,
        learning_objectives=body.learning_objectives, created_by=current_user.id,
    )
    return course


@router.get("", response_model=CourseListResponse)
async def list_courses(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None, min_length=2, max_length=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    is_learner = current_user.role == Role.learner
    items, total = await course_service.list_courses(
        db,
        page=page,
        page_size=page_size,
        published_only=is_learner,
        search=search,
        learner_id=current_user.id if is_learner else None,
    )
    response_items = []
    for item in items:
        course = item["course"]
        response_items.append(
            CourseResponse(
                id=course.id,
                title=course.title,
                description=course.description,
                estimated_duration_minutes=course.estimated_duration_minutes,
                is_published=course.is_published,
                created_at=course.created_at,
                updated_at=course.updated_at,
                module_count=item.get("module_count"),
                is_enrolled=item.get("is_enrolled") if is_learner else None,
                enrollment_progress=item.get("enrollment_progress") if is_learner else None,
                # Ownership, for authors only. A learner has no use for it, and telling them who
                # wrote a course is not theirs to know.
                created_by=course.created_by if not is_learner else None,
                can_edit=(
                    None if is_learner
                    else course_ownership.can_edit(current_user, course)
                ),
            )
        )
    return CourseListResponse(items=response_items, total=total, page=page, page_size=page_size)


@router.get("/{course_id}", response_model=CourseDetailResponse)
async def get_course(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await course_ownership.assert_can_read_course(db, current_user, course_id)
    course = await course_service.get_course(db, course_id)
    response = CourseDetailResponse.model_validate(course)
    # Same annotation as the list view, and for the same reason: the structure builder decides
    # whether to render destructive actions from this, and must not offer what the API refuses.
    #
    # `created_by` is CLEARED for learners rather than simply not set: `model_validate` reads it
    # straight off the ORM object, so leaving it alone would leak the author's user id to every
    # enrolled learner. Who wrote a course is not theirs to know.
    if current_user.role == Role.learner:
        response.created_by = None
        response.can_edit = None
    else:
        response.created_by = course.created_by
        response.can_edit = course_ownership.can_edit(current_user, course)
    return response


@router.put("/{course_id}", response_model=CourseResponse)
async def update_course(
    course_id: uuid.UUID,
    body: CourseUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.course_designer, Role.admin)),
):
    await course_ownership.assert_can_edit_course(db, current_user, course_id)
    fields = body.model_dump(exclude_unset=True)
    course = await course_service.update_course(db, course_id, **fields)

    # Publishing is the moment a designer asserts the content is ready for learners, so it is the
    # boundary worth freezing. Snapshotting on every edit instead would produce hundreds of
    # versions per paragraph, because the content editor autosaves as you type.
    #
    # Only on the false -> true transition: `fields` carries `is_published` only when the caller
    # sent it, so a title change never triggers a version.
    if fields.get("is_published") is True:
        await content_version_service.snapshot_on_publish(
            db, course_id=course_id, published_by=current_user.id
        )
        await db.commit()
        await db.refresh(course)
    return course


@router.delete("/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_course(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.course_designer, Role.admin)),
):
    await course_ownership.assert_can_edit_course(db, current_user, course_id)
    await course_service.delete_course(db, course_id)


# ---------------------------------------------------------------------------
# Module endpoints
# ---------------------------------------------------------------------------

@router.post("/{course_id}/modules", response_model=ModuleResponse, status_code=status.HTTP_201_CREATED)
async def create_module(
    course_id: uuid.UUID,
    body: ModuleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.course_designer, Role.admin)),
):
    await course_ownership.assert_can_edit_course(db, current_user, course_id)
    return await course_service.create_module(
        db, course_id, title=body.title, description=body.description, sort_order=body.sort_order,
    )


@router.get("/{course_id}/modules", response_model=list[ModuleResponse])
async def list_modules(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await course_ownership.assert_can_read_course(db, current_user, course_id)
    return await course_service.list_modules(db, course_id)


# ---------------------------------------------------------------------------
# Module direct endpoints (update/delete by module ID)
# ---------------------------------------------------------------------------

@router.put("/modules/{module_id}", response_model=ModuleResponse)
async def update_module(
    module_id: uuid.UUID,
    body: ModuleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.course_designer, Role.admin)),
):
    await course_ownership.assert_can_edit_module(db, current_user, module_id)
    fields = body.model_dump(exclude_unset=True)
    return await course_service.update_module(db, module_id, **fields)


@router.delete("/modules/{module_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_module(
    module_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.course_designer, Role.admin)),
):
    await course_ownership.assert_can_edit_module(db, current_user, module_id)
    await course_service.delete_module(db, module_id)


# ---------------------------------------------------------------------------
# Lesson endpoints
# ---------------------------------------------------------------------------

@router.post("/modules/{module_id}/lessons", response_model=LessonResponse, status_code=status.HTTP_201_CREATED)
async def create_lesson(
    module_id: uuid.UUID,
    body: LessonCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.course_designer, Role.admin)),
):
    await course_ownership.assert_can_edit_module(db, current_user, module_id)
    return await course_service.create_lesson(
        db, module_id, title=body.title, description=body.description, sort_order=body.sort_order,
    )


@router.get("/modules/{module_id}/lessons", response_model=list[LessonResponse])
async def list_lessons(
    module_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await course_ownership.assert_can_read_module(db, current_user, module_id)
    return await course_service.list_lessons(db, module_id)


@router.get("/lessons/{lesson_id}/detail", response_model=LessonDetailResponse)
async def get_lesson_detail(
    lesson_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return a lesson with all sections and content blocks (single query)."""
    await course_ownership.assert_can_read_lesson(db, current_user, lesson_id)
    return await course_service.get_lesson_detail(
        db, lesson_id, originals_only=current_user.role == Role.learner
    )


@router.put("/lessons/{lesson_id}", response_model=LessonResponse)
async def update_lesson(
    lesson_id: uuid.UUID,
    body: LessonUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.course_designer, Role.admin)),
):
    await course_ownership.assert_can_edit_lesson(db, current_user, lesson_id)
    fields = body.model_dump(exclude_unset=True)
    return await course_service.update_lesson(db, lesson_id, **fields)


@router.delete("/lessons/{lesson_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lesson(
    lesson_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.course_designer, Role.admin)),
):
    await course_ownership.assert_can_edit_lesson(db, current_user, lesson_id)
    await course_service.delete_lesson(db, lesson_id)


# ---------------------------------------------------------------------------
# Section endpoints
# ---------------------------------------------------------------------------

@router.post("/lessons/{lesson_id}/sections", response_model=SectionResponse, status_code=status.HTTP_201_CREATED)
async def create_section(
    lesson_id: uuid.UUID,
    body: SectionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.course_designer, Role.admin)),
):
    await course_ownership.assert_can_edit_lesson(db, current_user, lesson_id)
    return await course_service.create_section(
        db, lesson_id, title=body.title, sort_order=body.sort_order,
        estimated_duration_minutes=body.estimated_duration_minutes,
    )


@router.get("/lessons/{lesson_id}/sections", response_model=list[SectionResponse])
async def list_sections(
    lesson_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await course_ownership.assert_can_read_lesson(db, current_user, lesson_id)
    return await course_service.list_sections(db, lesson_id)


@router.put("/sections/{section_id}", response_model=SectionResponse)
async def update_section(
    section_id: uuid.UUID,
    body: SectionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.course_designer, Role.admin)),
):
    await course_ownership.assert_can_edit_section(db, current_user, section_id)
    fields = body.model_dump(exclude_unset=True)
    return await course_service.update_section(db, section_id, **fields)


@router.delete("/sections/{section_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_section(
    section_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.course_designer, Role.admin)),
):
    await course_ownership.assert_can_edit_section(db, current_user, section_id)
    await course_service.delete_section(db, section_id)


# ---------------------------------------------------------------------------
# ContentBlock endpoints
# ---------------------------------------------------------------------------

@router.post("/sections/{section_id}/content-blocks", response_model=ContentBlockResponse, status_code=status.HTTP_201_CREATED)
async def create_content_block(
    section_id: uuid.UUID,
    body: ContentBlockCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.course_designer, Role.admin)),
):
    await course_ownership.assert_can_edit_section(db, current_user, section_id)
    return await course_service.create_content_block(
        db, section_id, block_type=body.block_type, content=body.content,
        sort_order=body.sort_order, variant_key=body.variant_key, variant_group=body.variant_group,
    )


@router.get("/sections/{section_id}/content-blocks", response_model=list[ContentBlockResponse])
async def list_content_blocks(
    section_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await course_ownership.assert_can_read_section(db, current_user, section_id)
    return await course_service.list_content_blocks(
        db, section_id, originals_only=current_user.role == Role.learner
    )


@router.put("/content-blocks/{block_id}", response_model=ContentBlockResponse)
async def update_content_block(
    block_id: uuid.UUID,
    body: ContentBlockUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.course_designer, Role.admin)),
):
    await course_ownership.assert_can_edit_block(db, current_user, block_id)
    fields = body.model_dump(exclude_unset=True)
    return await course_service.update_content_block(db, block_id, **fields)


@router.delete("/content-blocks/{block_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_content_block(
    block_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.course_designer, Role.admin)),
):
    await course_ownership.assert_can_edit_block(db, current_user, block_id)
    await course_service.delete_content_block(db, block_id)


# ---------------------------------------------------------------------------
# Content-block variants (FR19 / FR21)
# ---------------------------------------------------------------------------
#
# `content_blocks` has carried `variant_key` and `variant_group` since migration 005, and until
# now nothing wrote anything but `"original"` into them. The adaptation loop consequently had no
# alternative content to reach for: `show_alternative` and `increase_difficulty` fell through to
# generated text, and `skip_ahead` degraded to "the next section".
#
# A variant is a sibling block in the SAME section sharing the original's `variant_group` and
# carrying a different `variant_key`. Learner-facing reads filter to `"original"`, so authoring
# one adds nothing to the ordinary reading experience — it only gives the loop something to swap
# in when it decides to.


@router.get("/content-blocks/{block_id}/variants", response_model=list[ContentBlockResponse])
async def list_content_block_variants(
    block_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.course_designer, Role.admin)),
):
    """Every alternative authored for this block, the original first."""
    await course_ownership.assert_can_edit_block(db, current_user, block_id)
    return await course_service.list_block_variants(db, block_id)


@router.post(
    "/content-blocks/{block_id}/variants",
    response_model=ContentBlockResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upsert_content_block_variant(
    block_id: uuid.UUID,
    body: ContentBlockVariantCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.course_designer, Role.admin)),
):
    """Create or replace one alternative of a block.

    Idempotent on `(variant_group, variant_key)`: saving the "simpler" variant twice edits it
    rather than accumulating duplicates, which matters because the loop selects by key and two
    blocks answering to the same key would make which one a learner sees arbitrary.
    """
    await course_ownership.assert_can_edit_block(db, current_user, block_id)
    return await course_service.upsert_block_variant(
        db, block_id, variant_key=body.variant_key, content=body.content
    )


# ---------------------------------------------------------------------------
# Published version history
# ---------------------------------------------------------------------------
#
# `content_version_service.snapshot_on_publish` has captured the whole content tree on every
# publish since migration 025, and nothing could read one back. The feature was write-only: a
# designer could accumulate twenty snapshots and had no way to see that any existed, let alone
# what changed between them.
#
# Gated on the EDIT rule rather than the read rule, which keeps it consistent with the course
# editor that surfaces it: a designer who sees no Edit action on a course sees no history either.


@router.get("/{course_id}/versions", response_model=list[ContentVersionSummary])
async def list_course_versions(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.course_designer, Role.admin)),
):
    """Published versions of a course, newest first."""
    await course_ownership.assert_can_edit_course(db, current_user, course_id)
    rows = await content_version_service.list_versions(db, course_id)
    return [
        ContentVersionSummary(
            id=version.id,
            version_number=version.version_number,
            published_at=version.published_at,
            published_by_name=name,
        )
        for version, name in rows
    ]


@router.get("/versions/{version_id}", response_model=ContentVersionDetail)
async def get_course_version(
    version_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.course_designer, Role.admin)),
):
    """One published version, including the content tree captured at the time."""
    version = await content_version_service.get_version(db, version_id)
    await course_ownership.assert_can_edit_course(db, current_user, version.course_id)
    return ContentVersionDetail(
        id=version.id,
        version_number=version.version_number,
        published_at=version.published_at,
        snapshot=version.snapshot,
    )
