"""Pydantic schemas for MercadoLibre API request and response payloads."""

from pydantic import BaseModel, Field


class MLPicture(BaseModel):
    """Image reference for a MercadoLibre listing.

    Attributes:
        source: Public URL pointing to the image to be uploaded to ML.
    """

    source: str


class MLListingRequest(BaseModel):
    """Request payload for creating a MercadoLibre listing.

    Attributes:
        title: Listing title visible to buyers.
        category_id: MercadoLibre category identifier (e.g. ``"MLA1234"``).
        price: Listing price in the specified currency.
        currency_id: ISO 4217 currency code. Defaults to ``"USD"``.
        available_quantity: Units available for sale. Defaults to ``1``.
        buying_mode: Purchase modality (e.g. ``"buy_it_now"``). Defaults to
            ``"buy_it_now"``.
        condition: Item condition. Defaults to ``"new"``.
        listing_type_id: ML listing tier. Defaults to ``"gold_special"``.
        description: Long-form item description shown on the listing page.
        pictures: List of image references to attach to the listing. Defaults
            to an empty list.
        video_id: Optional ML video identifier to attach to the listing.
    """

    title: str
    category_id: str
    price: float
    currency_id: str = "USD"
    available_quantity: int = 1
    buying_mode: str = "buy_it_now"
    condition: str = "new"
    listing_type_id: str = "gold_special"
    description: str
    pictures: list[MLPicture] = Field(default_factory=list)
    video_id: str | None = None


class MLListingResponse(BaseModel):
    """Response from ML after creating or updating a listing.

    Attributes:
        id: MercadoLibre listing identifier (e.g. ``"MLA123456789"``).
        title: Listing title as stored by MercadoLibre.
        price: Current listing price.
        status: Listing status (e.g. ``"active"``, ``"paused"``).
        permalink: Public URL of the listing on MercadoLibre.
    """

    id: str
    title: str
    price: float
    status: str
    permalink: str


class MLTokenResponse(BaseModel):
    """Response from ML OAuth2 token refresh.

    Attributes:
        access_token: New short-lived access token.
        token_type: Token type string (typically ``"bearer"``).
        expires_in: Lifetime of the access token in seconds.
        refresh_token: Long-lived token used to obtain a new access token.
    """

    access_token: str
    token_type: str
    expires_in: int
    refresh_token: str


class MLMediaUploadResponse(BaseModel):
    """Response from ML media/video upload.

    Attributes:
        id: Identifier assigned by MercadoLibre to the uploaded media asset.
        status: Processing status of the uploaded asset (e.g. ``"processed"``).
    """

    id: str
    status: str
