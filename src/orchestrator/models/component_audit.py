"""SQLAlchemy ORM model for the component_audit table."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from orchestrator.models.base import Base


class ComponentAudit(Base):
    """Tracks component usage across builds for catalog rotation.

    Attributes:
        sku: Unique stock-keeping unit identifier; serves as the primary key.
        category: Component category (e.g. "CPU", "GPU").
        last_bundled_date: UTC timestamp of the most recent bundle that included this SKU.
        bundle_count: Total number of builds in which this SKU has appeared.
        stock_level: Current stock quantity reported by the catalogue service.
        updated_at: UTC timestamp of the most recent update to this record.
    """

    __tablename__ = "component_audit"

    sku: Mapped[str] = mapped_column(String(100), primary_key=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    last_bundled_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    bundle_count: Mapped[int] = mapped_column(Integer, default=0)
    stock_level: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
