import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    ValidationError,
    model_validator,
)


DATA_PATH = Path(__file__).resolve().parent / "data" / "listings.json"

Condition = Literal["New in box", "Like new", "Excellent", "Good", "Fair"]
ListingStatus = Literal["Available", "Reserved", "Sold"]
ImagePath = Annotated[str, Field(pattern=r"^/static/images/[a-z0-9-]+\.svg$")]


class ListingSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    label: str = Field(min_length=2, max_length=40)
    value: str = Field(min_length=1, max_length=120)


class Listing(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    title: str = Field(min_length=3, max_length=100)
    price: int = Field(gt=0, le=100_000)
    category: str = Field(min_length=2, max_length=50)
    condition: Condition
    status: ListingStatus
    description: str = Field(min_length=20, max_length=1_000)
    image: ImagePath
    images: tuple[ImagePath, ...] = Field(min_length=2, max_length=4)
    pickup_area: str = Field(min_length=2, max_length=80)
    tags: tuple[str, ...] = Field(min_length=1, max_length=12)
    specs: tuple[ListingSpec, ...] = Field(min_length=2, max_length=6)

    @model_validator(mode="after")
    def validate_gallery(self) -> "Listing":
        if self.images[0] != self.image:
            raise ValueError("The primary image must be the first gallery image.")
        if len(self.images) != len(set(self.images)):
            raise ValueError("Gallery image paths must be unique within a listing.")
        return self


class CatalogLoadError(RuntimeError):
    """Raised when the seeded catalogue cannot be loaded safely."""


@lru_cache(maxsize=1)
def load_listings() -> tuple[Listing, ...]:
    try:
        raw_listings = json.loads(DATA_PATH.read_text(encoding="utf-8"))
        listings = tuple(TypeAdapter(list[Listing]).validate_python(raw_listings))
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise CatalogLoadError("The catalogue data is unavailable or invalid.") from exc

    listing_ids = [listing.id for listing in listings]
    if len(listing_ids) != len(set(listing_ids)):
        raise CatalogLoadError("Every catalogue listing must have a unique id.")
    if not listings:
        raise CatalogLoadError("The catalogue must contain at least one listing.")

    return listings


def get_listing(listing_id: str) -> Listing | None:
    return next(
        (listing for listing in load_listings() if listing.id == listing_id),
        None,
    )


def get_categories() -> tuple[str, ...]:
    return tuple(sorted({listing.category for listing in load_listings()}))
