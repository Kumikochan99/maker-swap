import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError


DATA_PATH = Path(__file__).resolve().parent / "data" / "listings.json"

Condition = Literal["New in box", "Like new", "Excellent", "Good", "Fair"]


class Listing(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    title: str = Field(min_length=3, max_length=100)
    price: int = Field(gt=0, le=100_000)
    category: str = Field(min_length=2, max_length=50)
    condition: Condition
    description: str = Field(min_length=20, max_length=1_000)
    image: str = Field(pattern=r"^/static/images/[a-z0-9-]+\.svg$")
    pickup_area: str = Field(min_length=2, max_length=80)
    tags: tuple[str, ...] = Field(min_length=1, max_length=8)


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
