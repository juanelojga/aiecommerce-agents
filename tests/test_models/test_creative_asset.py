"""Tests for the CreativeAsset ORM model."""

import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession

from orchestrator.models.creative_asset import CreativeAsset


def test_creative_asset_table_name() -> None:
    """Table name is 'creative_assets'."""
    assert CreativeAsset.__tablename__ == "creative_assets"


def test_creative_asset_columns() -> None:
    """All required columns exist on the mapper with correct attribute names."""
    mapper = inspect(CreativeAsset)
    column_names = {col.key for col in mapper.columns}

    expected = {
        "id",
        "tower_hash",
        "bundle_id",
        "media_type",
        "url",
        "mime_type",
        "width",
        "height",
        "duration_seconds",
        "style",
        "prompt_used",
        "created_at",
        "updated_at",
    }
    assert expected.issubset(column_names)


@pytest.mark.asyncio
async def test_creative_asset_image_instance(db_session: AsyncSession) -> None:
    """Image asset can be instantiated and persisted without duration."""
    asset = CreativeAsset(
        tower_hash="a" * 64,
        media_type="image",
        url="https://cdn.example.com/img/abc.png",
        mime_type="image/png",
        width=1920,
        height=1080,
    )
    db_session.add(asset)
    await db_session.commit()
    await db_session.refresh(asset)

    assert asset.id is not None
    assert asset.tower_hash == "a" * 64
    assert asset.media_type == "image"
    assert asset.duration_seconds is None
    assert asset.bundle_id is None


@pytest.mark.asyncio
async def test_creative_asset_video_instance(db_session: AsyncSession) -> None:
    """Video asset with a duration can be persisted and read back correctly."""
    asset = CreativeAsset(
        tower_hash="b" * 64,
        bundle_id="bundle-001",
        media_type="video",
        url="https://cdn.example.com/video/xyz.mp4",
        mime_type="video/mp4",
        width=1280,
        height=720,
        duration_seconds=15.5,
        style="cinematic",
        prompt_used="A cinematic view of a gaming PC tower",
    )
    db_session.add(asset)
    await db_session.commit()
    await db_session.refresh(asset)

    fetched = await db_session.get(CreativeAsset, asset.id)
    assert fetched is not None
    assert fetched.media_type == "video"
    assert fetched.duration_seconds == pytest.approx(15.5)
    assert fetched.bundle_id == "bundle-001"
    assert fetched.style == "cinematic"
    assert fetched.prompt_used == "A cinematic view of a gaming PC tower"


def test_creative_asset_tower_hash_indexed() -> None:
    """An index exists on the tower_hash column."""
    from sqlalchemy import Table

    table: Table = CreativeAsset.__table__  # type: ignore[assignment]
    indexed_columns: set[str] = set()
    for index in table.indexes:
        for col in index.columns:
            indexed_columns.add(col.name)

    assert "tower_hash" in indexed_columns
