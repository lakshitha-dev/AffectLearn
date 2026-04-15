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
    CourseCreate,
    CourseDetailResponse,
    CourseListResponse,
    CourseResponse,
    CourseUpdate,
    LessonCreate,
    LessonResponse,
    LessonUpdate,
    ModuleCreate,
    ModuleResponse,
    ModuleUpdate,
    SectionCreate,
    SectionResponse,
    SectionUpdate,
)
from app.services import course_service

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
    course = await course_service.create_course(
        db, title=body.title, description=body.description,
        estimated_duration_minutes=body.estimated_duration_minutes, is_published=body.is_published,
    )
    return course


@router.get("", response_model=CourseListResponse)
async def list_courses(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items, total = await course_service.list_courses(db, page=page, page_size=page_size)
    return CourseListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{course_id}", response_model=CourseDetailResponse)
async def get_course(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await course_service.get_course(db, course_id)


@router.put("/{course_id}", response_model=CourseResponse)
async def update_course(
    course_id: uuid.UUID,
    body: CourseUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.course_designer, Role.admin)),
):
    fields = body.model_dump(exclude_unset=True)
    return await course_service.update_course(db, course_id, **fields)


@router.delete("/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_course(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.course_designer, Role.admin)),
):
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
    return await course_service.create_module(
        db, course_id, title=body.title, description=body.description, sort_order=body.sort_order,
    )


@router.get("/{course_id}/modules", response_model=list[ModuleResponse])
async def list_modules(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
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
    fields = body.model_dump(exclude_unset=True)
    return await course_service.update_module(db, module_id, **fields)


@router.delete("/modules/{module_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_module(
    module_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.course_designer, Role.admin)),
):
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
    return await course_service.create_lesson(
        db, module_id, title=body.title, description=body.description, sort_order=body.sort_order,
    )


@router.get("/modules/{module_id}/lessons", response_model=list[LessonResponse])
async def list_lessons(
    module_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await course_service.list_lessons(db, module_id)


@router.put("/lessons/{lesson_id}", response_model=LessonResponse)
async def update_lesson(
    lesson_id: uuid.UUID,
    body: LessonUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.course_designer, Role.admin)),
):
    fields = body.model_dump(exclude_unset=True)
    return await course_service.update_lesson(db, lesson_id, **fields)


@router.delete("/lessons/{lesson_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lesson(
    lesson_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.course_designer, Role.admin)),
):
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
    return await course_service.list_sections(db, lesson_id)


@router.put("/sections/{section_id}", response_model=SectionResponse)
async def update_section(
    section_id: uuid.UUID,
    body: SectionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.course_designer, Role.admin)),
):
    fields = body.model_dump(exclude_unset=True)
    return await course_service.update_section(db, section_id, **fields)


@router.delete("/sections/{section_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_section(
    section_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.course_designer, Role.admin)),
):
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
    return await course_service.list_content_blocks(db, section_id)


@router.put("/content-blocks/{block_id}", response_model=ContentBlockResponse)
async def update_content_block(
    block_id: uuid.UUID,
    body: ContentBlockUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.course_designer, Role.admin)),
):
    fields = body.model_dump(exclude_unset=True)
    return await course_service.update_content_block(db, block_id, **fields)


@router.delete("/content-blocks/{block_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_content_block(
    block_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.course_designer, Role.admin)),
):
    await course_service.delete_content_block(db, block_id)
