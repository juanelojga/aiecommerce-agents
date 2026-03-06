"""Tests for MercadoLibre Pydantic schemas."""

from orchestrator.schemas.mercadolibre import (
    MLListingRequest,
    MLListingResponse,
    MLMediaUploadResponse,
    MLPicture,
    MLTokenResponse,
)

# ---------------------------------------------------------------------------
# MLListingRequest
# ---------------------------------------------------------------------------


def test_ml_listing_request_defaults() -> None:
    """Default values for currency_id, buying_mode, and condition are correct."""
    request = MLListingRequest(
        title="RTX 4090 Gaming PC",
        category_id="MLA1234",
        price=2500.0,
        description="High-end gaming tower.",
    )

    assert request.currency_id == "USD"
    assert request.buying_mode == "buy_it_now"
    assert request.condition == "new"
    assert request.listing_type_id == "gold_special"
    assert request.available_quantity == 1
    assert request.video_id is None


def test_ml_listing_request_full() -> None:
    """Full request with all fields populated stores every value correctly."""
    pictures = [MLPicture(source="https://cdn.example.com/img1.jpg")]
    request = MLListingRequest(
        title="RTX 4090 Gaming PC",
        category_id="MLA1234",
        price=2500.0,
        currency_id="ARS",
        available_quantity=3,
        buying_mode="classified",
        condition="used",
        listing_type_id="gold_pro",
        description="High-end gaming tower with RTX 4090.",
        pictures=pictures,
        video_id="VIDEO123",
    )

    assert request.title == "RTX 4090 Gaming PC"
    assert request.category_id == "MLA1234"
    assert request.price == 2500.0
    assert request.currency_id == "ARS"
    assert request.available_quantity == 3
    assert request.buying_mode == "classified"
    assert request.condition == "used"
    assert request.listing_type_id == "gold_pro"
    assert request.description == "High-end gaming tower with RTX 4090."
    assert len(request.pictures) == 1
    assert request.pictures[0].source == "https://cdn.example.com/img1.jpg"
    assert request.video_id == "VIDEO123"


def test_ml_listing_request_empty_pictures() -> None:
    """Pictures field defaults to an empty list when not provided."""
    request = MLListingRequest(
        title="Basic PC",
        category_id="MLA5678",
        price=999.0,
        description="Entry-level tower.",
    )

    assert request.pictures == []


# ---------------------------------------------------------------------------
# MLListingResponse
# ---------------------------------------------------------------------------


def test_ml_listing_response_parsing() -> None:
    """MLListingResponse is correctly parsed from a dict."""
    data = {
        "id": "MLA123456789",
        "title": "RTX 4090 Gaming PC",
        "price": 2500.0,
        "status": "active",
        "permalink": "https://www.mercadolibre.com.ar/MLA123456789",
    }

    response = MLListingResponse(**data)

    assert response.id == "MLA123456789"
    assert response.title == "RTX 4090 Gaming PC"
    assert response.price == 2500.0
    assert response.status == "active"
    assert response.permalink == "https://www.mercadolibre.com.ar/MLA123456789"


# ---------------------------------------------------------------------------
# MLTokenResponse
# ---------------------------------------------------------------------------


def test_ml_token_response_parsing() -> None:
    """MLTokenResponse is correctly parsed from an OAuth2 token payload."""
    data = {
        "access_token": "APP_USR-abc123",
        "token_type": "bearer",
        "expires_in": 21600,
        "refresh_token": "TG-xyz789",
    }

    token = MLTokenResponse(**data)

    assert token.access_token == "APP_USR-abc123"
    assert token.token_type == "bearer"
    assert token.expires_in == 21600
    assert token.refresh_token == "TG-xyz789"


# ---------------------------------------------------------------------------
# MLMediaUploadResponse
# ---------------------------------------------------------------------------


def test_ml_media_upload_response_parsing() -> None:
    """MLMediaUploadResponse is correctly parsed from a media upload payload."""
    data = {
        "id": "MEDIA-001",
        "status": "processed",
    }

    upload = MLMediaUploadResponse(**data)

    assert upload.id == "MEDIA-001"
    assert upload.status == "processed"
