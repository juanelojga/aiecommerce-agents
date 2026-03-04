"""SQLAlchemy ORM model for the published_towers table."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, DateTime, Enum, Float, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from orchestrator.models.base import Base


class TowerCategory(StrEnum):
    """Valid categories for a published PC tower build."""

    HOME = "Home"
    BUSINESS = "Business"
    GAMING = "Gaming"


class TowerStatus(StrEnum):
    """Lifecycle status of a published PC tower build."""

    ACTIVE = "Active"
    PAUSED = "Paused"


class PublishedTower(Base):
    """A published PC tower build stored in the Local Registry.

    Attributes:
        bundle_hash: SHA-256 hash of the component set; serves as the primary key.
        ml_id: Optional identifier used by the ML catalogue service.
        category: Target use-case category for the build.
        status: Whether the build is currently active or paused.
        component_skus: JSON mapping of component roles to SKU identifiers.
        total_price: Total price of all components in the build.
        created_at: UTC timestamp when the record was first inserted.
        updated_at: UTC timestamp of the most recent update.
    """

    __tablename__ = "published_towers"

    bundle_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    ml_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    category: Mapped[TowerCategory] = mapped_column(Enum(TowerCategory))
    status: Mapped[TowerStatus] = mapped_column(Enum(TowerStatus), default=TowerStatus.ACTIVE)
    component_skus: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    total_price: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
