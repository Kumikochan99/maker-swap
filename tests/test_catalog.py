from pathlib import Path

from fastapi.testclient import TestClient

from app.catalog import get_categories, get_listing, load_listings
from app.main import app


client = TestClient(app)
STATIC_DIR = Path(__file__).resolve().parents[1] / "app" / "static"


def test_seeded_catalog_is_valid_and_complete() -> None:
    listings = load_listings()
    listing_ids = [listing.id for listing in listings]

    assert len(listings) == 16
    assert len(listing_ids) == len(set(listing_ids))
    assert get_categories() == (
        "3D Printing",
        "Art & Craft",
        "Electronics",
        "Instruments",
        "Workshop Tools",
    )
    assert all((STATIC_DIR / listing.image.removeprefix("/static/")).is_file() for listing in listings)


def test_browse_page_renders_every_listing() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.text.count('data-listing-id="') == 16
    assert "Original Prusa MINI+" in response.text
    assert "Bosch Router with Compact Table" in response.text
    assert '<meta name="viewport"' in response.text
    assert "sm:grid-cols-2" in response.text


def test_category_filter_limits_visible_listings() -> None:
    response = client.get("/", params={"category": "Electronics"})

    assert response.status_code == 200
    assert response.text.count('data-listing-id="') == 4
    assert "Hakko FX-888D Soldering Station" in response.text
    assert "Yamaha Pacifica 112V Guitar" not in response.text


def test_category_filters_return_to_catalogue_anchor() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert 'id="listings"' in response.text
    assert response.text.count("#listings\"") == 6
    assert "?category=Electronics#listings" in response.text


def test_unknown_category_has_a_useful_empty_state() -> None:
    response = client.get("/", params={"category": "Imaginary Gear"})

    assert response.status_code == 200
    assert "No listings in that category yet." in response.text
    assert "Browse all items" in response.text


def test_listing_detail_uses_plain_pickup_area_data() -> None:
    response = client.get("/listings/original-prusa-mini-plus")

    assert response.status_code == 200
    assert "Original Prusa MINI+" in response.text
    assert "S$420" in response.text
    assert "Jurong East" in response.text
    assert "No seller profile or messaging is available." in response.text


def test_unknown_listing_returns_friendly_404() -> None:
    response = client.get("/listings/not-a-real-listing")

    assert response.status_code == 404
    assert "That item has left the workbench." in response.text
    assert "Browse available items" in response.text


def test_lookup_returns_none_for_unknown_id() -> None:
    assert get_listing("not-a-real-listing") is None
