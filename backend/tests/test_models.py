"""Tests for SQLAlchemy base model definition."""


async def test_base_model_is_abstract():
    """Verify BaseModel is abstract and cannot be instantiated as a table."""
    from app.models.base import BaseModel

    assert BaseModel.__abstract__ is True


async def test_base_model_has_required_columns():
    """Verify BaseModel defines id, created_at, updated_at columns."""
    from app.models.base import BaseModel

    column_names = {col.name for col in BaseModel.__table__.columns} if hasattr(BaseModel, "__table__") else set()

    # Since it's abstract, check via class attributes
    assert hasattr(BaseModel, "id")
    assert hasattr(BaseModel, "created_at")
    assert hasattr(BaseModel, "updated_at")


async def test_base_model_id_is_uuid():
    """Verify id column uses UUID type."""
    from app.models.base import BaseModel
    from sqlalchemy.dialects.postgresql import UUID as PG_UUID

    id_col = BaseModel.__dict__["id"]
    assert isinstance(id_col.type, PG_UUID) or "UUID" in str(id_col.type)


async def test_base_declarative_base():
    """Verify Base is a proper DeclarativeBase."""
    from app.models.base import Base
    from sqlalchemy.orm import DeclarativeBase

    assert issubclass(Base, DeclarativeBase)
