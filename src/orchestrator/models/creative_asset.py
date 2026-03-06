"""SQLAlchemy ORM model for the creative_assets table."""

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from orchestrator.models.base import Base


class CreativeAsset(Base):
    """A generated media asset (image or video) linked to a tower build.

    Each row represents a single creative asset produced for a ``PublishedTower``
    (and optionally a ``PublishedBundle``).  The ``tower_hash`` and ``bundle_id``
    columns are indexed for efficient look-ups by tower or bundle.

    Attributes:
        id: Auto-incrementing surrogate primary key.
        tower_hash: SHA-256 hash of the associated tower build.
        bundle_id: Optional identifier of the associated bundle.
        media_type: Kind of media, e.g. ``"image"`` or ``"video"``.
        url: Public URL where the asset can be retrieved.
        mime_type: MIME type of the asset, e.g. ``"image/png"``.
        width: Pixel width of the asset.
        height: Pixel height of the asset.
        duration_seconds: Duration in seconds for video assets; ``None`` for images.
        style: Visual style descriptor applied during generation.
        prompt_used: The full text prompt that was sent to the generation service.
        created_at: UTC timestamp when the record was first inserted.
        updated_at: UTC timestamp of the most recent update.
    """

    __tablename__ = "creative_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tower_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    bundle_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    media_type: Mapped[str] = mapped_column(String(10), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(50), nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    style: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    prompt_used: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
