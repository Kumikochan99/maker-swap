import re
from collections import Counter
from pathlib import Path

from fastapi.testclient import TestClient

from app.catalog import get_categories, get_listing, load_listings
from app.main import FEATURED_LISTING_IDS, app


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
    assert Counter(listing.status for listing in listings) == {
        "Available": 13,
        "Reserved": 2,
        "Sold": 1,
    }
    assert all(2 <= len(listing.images) <= 4 for listing in listings)
    assert all(listing.images[0] == listing.image for listing in listings)
    assert all(len(listing.specs) >= 2 for listing in listings)
    assert all(
        (STATIC_DIR / image.removeprefix("/static/")).is_file()
        for listing in listings
        for image in listing.images
    )


def test_browse_page_renders_every_listing() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.text.count('data-listing-id="') == 16
    assert "Original Prusa MINI+" in response.text
    assert "Bosch Router with Compact Table" in response.text
    assert '<meta name="viewport"' in response.text
    assert "sm:grid-cols-2" in response.text
    assert 'href="http://testserver/notes"' in response.text
    assert 'href="https://github.com/Kumikochan99/maker-swap"' in response.text
    assert 'href="https://github.com/Kumikochan99"' in response.text
    assert "A public second-hand maker marketplace demo" in response.text
    assert response.text.count('data-listing-status="Reserved"') == 2
    assert response.text.count('data-listing-status="Sold"') == 1


def test_home_page_carousel_features_four_available_category_representatives() -> None:
    response = client.get("/")
    listings_by_id = {listing.id: listing for listing in load_listings()}
    featured = tuple(listings_by_id[listing_id] for listing_id in FEATURED_LISTING_IDS)

    assert response.status_code == 200
    assert FEATURED_LISTING_IDS == (
        "original-prusa-mini-plus",
        "raspberry-pi-4-workbench",
        "yamaha-pacifica-112v",
        "watercolour-studio-set",
    )
    assert tuple(listing.category for listing in featured) == (
        "3D Printing",
        "Electronics",
        "Instruments",
        "Art & Craft",
    )
    assert all(listing.status == "Available" for listing in featured)
    assert re.findall(r'data-featured-id="([a-z0-9-]+)"', response.text) == list(
        FEATURED_LISTING_IDS
    )
    assert response.text.count("data-featured-slide") == 4
    assert 'data-interval-ms="7000"' in response.text
    assert 'aria-label="Previous featured listing"' in response.text
    assert 'aria-label="Next featured listing"' in response.text
    assert ">Art Supplies</p>" in response.text
    assert (
        'src="http://testserver/static/featured-carousel.js?v=landing-polish-1"'
        in response.text
    )
    for listing in featured:
        assert f'href="http://testserver/listings/{listing.id}"' in response.text


def test_browse_page_has_navigation_and_on_page_category_controls() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert 'class="site-header fixed' in response.text
    assert 'id="site-category-menu"' in response.text
    assert 'id="category-menu-toggle"' in response.text
    assert "All Listings" in response.text
    assert ">3D Printing</a>" in response.text
    assert ">Electronics</a>" in response.text
    assert ">Instruments</a>" in response.text
    assert ">Art Supplies</a>" in response.text
    assert ">Workshop Tools</a>" in response.text
    assert 'aria-label="Browse-page categories"' in response.text
    assert response.text.count('class="category-pill ') == 6
    assert (
        'class="category-pill category-pill-active" aria-current="page">All</a>'
        in response.text
    )
    assert response.text.count("?category=Electronics#listings\"") == 2
    assert ">Browse</a>" not in response.text


def test_category_controls_reflect_the_same_active_filter() -> None:
    response = client.get("/", params={"category": "Electronics"})

    assert response.status_code == 200
    assert (
        'href="http://testserver/?category=Electronics#listings" '
        'class="site-dropdown-link block rounded-2xl px-4 py-2.5 text-sm '
        'font-semibold text-slate-700" aria-current="page">Electronics</a>'
    ) in response.text
    assert (
        'href="http://testserver/?category=Electronics#listings" '
        'class="category-pill category-pill-active" aria-current="page"'
    ) in response.text
    assert (
        'class="category-pill category-pill-active" aria-current="page">All</a>'
        not in response.text
    )


def test_browse_page_defaults_to_the_existing_list_layout_with_view_controls() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert 'id="listing-grid" data-listing-view="list"' in response.text
    assert "mt-9 grid gap-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4" in response.text
    assert 'data-listing-view-button="list"' in response.text
    assert 'data-listing-view-button="gallery"' in response.text
    assert 'aria-label="Choose listing view"' in response.text
    assert 'aria-pressed="true" title="List view"' in response.text
    assert 'aria-pressed="false" title="Gallery view"' in response.text
    assert 'src="http://testserver/static/catalogue-view.js?v=gallery-view-1"' in response.text
    assert "data-card-image-frame" in response.text
    assert "data-card-content" in response.text


def test_category_filter_limits_visible_listings() -> None:
    response = client.get("/", params={"category": "Electronics"})

    assert response.status_code == 200
    assert response.text.count('data-listing-id="') == 4
    assert "Hakko FX-888D Soldering Station" in response.text
    assert 'data-listing-id="yamaha-pacifica-112v"' not in response.text


def test_category_filters_return_to_catalogue_anchor() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert 'id="listings"' in response.text
    assert response.text.count("#listings\"") >= 6
    assert "?category=Electronics#listings" in response.text
    assert response.text.index('id="catalogue-search-form"') < response.text.index(
        'id="listings"'
    ) < response.text.index('id="listing-grid"')


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
    assert "Availability and location are seeded display data" in response.text
    assert 'href="http://testserver/#listings"' in response.text
    assert 'data-catalogue-url="http://testserver/#listings"' in response.text
    assert "data-listing-card" in response.text
    assert 'src="http://testserver/static/detail.js?v=gallery-1"' in response.text


def test_listing_detail_renders_gallery_specs_and_static_status() -> None:
    reserved = client.get("/listings/bambu-lab-a1-mini")
    sold = client.get("/listings/arduino-sensor-starter-kit")

    assert reserved.status_code == 200
    assert reserved.text.count("data-gallery-thumbnail") == 3
    assert "data-gallery-main" in reserved.text
    assert "Build volume" in reserved.text
    assert 'data-status="Reserved"' in reserved.text
    assert "There is no seller messaging or interactive reservation flow." in reserved.text
    assert "not photographs of a seller's item" in reserved.text

    assert sold.status_code == 200
    assert 'data-status="Sold"' in sold.text
    assert "stays visible as catalogue history" in sold.text
    assert "There is no seller profile, messaging or purchase flow." in sold.text


def test_unknown_listing_returns_friendly_404() -> None:
    response = client.get("/listings/not-a-real-listing")

    assert response.status_code == 404
    assert "That item has left the workbench." in response.text
    assert "Browse available items" in response.text


def test_lookup_returns_none_for_unknown_id() -> None:
    assert get_listing("not-a-real-listing") is None
