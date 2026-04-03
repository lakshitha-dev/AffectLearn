import enum

from sqlalchemy import Boolean, Column, Enum, String
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import BaseModel


class Role(enum.Enum):
    learner = "learner"
    designer = "designer"
    admin = "admin"


class User(BaseModel):
    __tablename__ = "users"

    email_address = Column(String(320), unique=True, nullable=False, index=True)
    password_hash = Column(String(128), nullable=False)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    role = Column(Enum(Role), nullable=False, default=Role.learner)
    is_active = Column(Boolean, nullable=False, default=True)
