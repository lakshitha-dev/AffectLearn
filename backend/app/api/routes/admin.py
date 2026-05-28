"""Admin API endpoints."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_role
from app.models.user import Role, User
from app.schemas.auth import UserResponse
from app.schemas.base import PaginatedResponse

router = APIRouter()


@router.get("/users", response_model=PaginatedResponse)
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(require_role(Role.admin)),
    db: AsyncSession = Depends(get_db),
):
    """List all users. Requires admin role."""
    offset = (page - 1) * page_size

    total_result = await db.execute(select(func.count()).select_from(User))
    total = total_result.scalar_one()

    result = await db.execute(
        select(User).offset(offset).limit(page_size).order_by(User.created_at.desc())
    )
    users = result.scalars().all()

    return PaginatedResponse(
        items=[
            UserResponse(
                id=u.id,
                email_address=u.email_address,
                first_name=u.first_name,
                last_name=u.last_name,
                role=u.role.value,
            )
            for u in users
        ],
        total=total,
        page=page,
        page_size=page_size,
    )
