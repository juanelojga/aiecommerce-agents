"""SQLAlchemy declarative base for the Local Registry."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models.

    Inherit from this class to define database entities.
    """
