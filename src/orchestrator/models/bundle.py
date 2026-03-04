"""SQLAlchemy ORM model for the published_bundles table."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from orchestrator.models.base import Base


class PublishedBundle(Base):
    """A published PC bundle (tower + peripherals) in the Local Registry.

    Attributes:
        bundle_id: SHA-256 hash of the full bundle; serves as the primary key.
        tower_hash: Foreign key referencing the associated ``PublishedTower``.
        peripheral_skus: JSON mapping of peripheral roles to SKU identifiers.
        ml_id: Optional identifier used by the ML catalogue service.
        created_at: UTC timestamp when the record was first inserted.
        updated_at: UTC timestamp of the most recent update.
    """

    __tablename__ = "published_bundles"

    bundle_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tower_hash: Mapped[str] = mapped_column(
        String(64), ForeignKey("published_towers.bundle_hash"), nullable=False
    )
    peripheral_skus: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    ml_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
