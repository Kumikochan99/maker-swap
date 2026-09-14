import json
import re
import socket
from pathlib import Path
from threading import Thread
from time import monotonic, sleep
from urllib.request import urlopen

import pytest
import uvicorn
from playwright.sync_api import Browser, Error as PlaywrightError, Page, expect, sync_playwright

from app.catalog import load_listings
from app.main import app


EDGE_PATH = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")


@pytest.fixture(scope="module")
def browser_base_url() -> str:
    with socket.socket() as port_socket:
        port_socket.bind(("127.0.0.1", 0))
        port = port_socket.getsockname()[1]

    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="error",
    )
    server = uvicorn.Server(config)
    server_thread = Thread(target=server.run, daemon=True)
    server_thread.start()
    base_url = f"http://127.0.0.1:{port}"

    deadline = monotonic() + 10
    while monotonic() < deadline:
        try:
            with urlopen(f"{base_url}/health", timeout=1) as response:
                if response.status == 200:
                    break
        except OSError:
            sleep(0.05)
    else:
        server.should_exit = True
        server_thread.join(timeout=5)
        pytest.fail("The local browser-test server did not start.")

    yield base_url

    server.should_exit = True
    server_thread.join(timeout=5)


@pytest.fixture(scope="module")
def browser() -> Browser:
    with sync_playwright() as playwright:
        launch_options = (
            {"executable_path": str(EDGE_PATH)} if EDGE_PATH.is_file() else {}
        )
        try:
            browser_instance = playwright.chromium.launch(
                headless=True,
                **launch_options,
            )
        except PlaywrightError as exc:
            pytest.skip(f"A Chromium browser is not available: {exc}")

        yield browser_instance
        browser_instance.close()


def open_page(
    browser: Browser,
    base_url: str,
    path: str = "/",
    viewport: dict[str, int] | None = None,
) -> Page:
    context = browser.new_context(
        viewport=viewport or {"width": 1280, "height": 720}
    )
    page = context.new_page()
    page.goto(f"{base_url}{path}", wait_until="networkidle")
    return page


def css_channels(color: str) -> tuple[float, float, float, float]:
    values = [float(value) for value in re.findall(r"[\d.]+", color)]
    assert len(values) >= 3
    alpha = values[3] if len(values) >= 4 else 1.0
    return values[0], values[1], values[2], alpha


def relative_luminance(channels: tuple[float, float, float]) -> float:
    def linearize(value: float) -> float:
        normalized = value / 255
        return (
            normalized / 12.92
            if normalized <= 0.04045
            else ((normalized + 0.055) / 1.055) ** 2.4
        )

    red, green, blue = (linearize(channel) for channel in channels)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast_ratio(
    foreground: tuple[float, float, float],
    background: tuple[float, float, float],
) -> float:
    light, dark = sorted(
        (relative_luminance(foreground), relative_luminance(background)),
        reverse=True,
    )
    return (light + 0.05) / (dark + 0.05)


def glass_contrast_over_darkest_background(
    foreground_css: str,
    glass_css: str,
) -> float:
    foreground = css_channels(foreground_css)[:3]
    glass_red, glass_green, glass_blue, glass_alpha = css_channels(glass_css)
    darkest_composite = (
        glass_red * glass_alpha,
        glass_green * glass_alpha,
        glass_blue * glass_alpha,
    )
    return contrast_ratio(foreground, darkest_composite)


def test_category_filter_preserves_catalogue_scroll_position(
    browser: Browser,
    browser_base_url: str,
) -> None:
    page = open_page(browser, browser_base_url)

    page.locator("#category-menu-toggle").click()
    expect(page.locator("#category-menu-toggle")).to_have_attribute(
        "aria-expanded", "true"
    )
    electronics = page.locator(".site-dropdown-panel").get_by_role(
        "link", name="Electronics", exact=True
    )
    assert electronics.get_attribute("href").endswith(
        "/?category=Electronics#listings"
    )
    electronics.click()
    page.wait_for_url(re.compile(r"\?category=Electronics#listings$"))
    expect(page.locator('[data-listing-id]')).to_have_count(4)

    scroll_position = page.evaluate("window.scrollY")
    catalogue_top = page.locator("#listings").evaluate(
        "element => element.getBoundingClientRect().top"
    )
    assert scroll_position > 0
    assert 80 <= catalogue_top <= 130

    page.context.close()


def test_featured_carousel_auto_advances_and_pauses_on_hover(
    browser: Browser,
    browser_base_url: str,
) -> None:
    context = browser.new_context(viewport={"width": 1280, "height": 720})
    page = context.new_page()
    page.goto(browser_base_url, wait_until="networkidle")
    carousel = page.locator("[data-featured-carousel]")
    track = page.locator("[data-featured-track]")

    expect(page.locator("[data-featured-slide]")).to_have_count(4)
    expect(track).to_have_attribute("data-active-index", "0")
    expect(carousel).to_have_attribute("data-auto-state", "running")
    expect(carousel).to_have_attribute("data-auto-advance-count", "0")
    intro_copy_style = page.locator(".hero-intro-copy").evaluate(
        """element => {
            const style = getComputedStyle(element);
            return {
                backgroundColor: style.backgroundColor,
                backgroundImage: style.backgroundImage,
            };
        }"""
    )
    assert intro_copy_style == {
        "backgroundColor": "rgba(0, 0, 0, 0)",
        "backgroundImage": "none",
    }

    expect(track).to_have_attribute("data-active-index", "1", timeout=9_000)
    expect(carousel).to_have_attribute("data-last-advance", "auto")
    expect(carousel).to_have_attribute("data-auto-advance-count", "1")
    expect(
        page.locator('[data-featured-id="original-prusa-mini-plus"]')
    ).to_have_attribute("aria-hidden", "true")
    page.wait_for_timeout(600)
    intro_heading_box = page.locator(".hero-intro-heading").bounding_box()
    carousel_viewport_box = page.locator(".hero-carousel-viewport").bounding_box()
    assert intro_heading_box is not None
    assert carousel_viewport_box is not None
    assert (
        intro_heading_box["x"] + intro_heading_box["width"]
        <= carousel_viewport_box["x"] + 1
    )

    expect(track).to_have_attribute("data-active-index", "2", timeout=9_000)
    expect(carousel).to_have_attribute("data-auto-advance-count", "2")

    carousel.hover()
    expect(carousel).to_have_attribute("data-auto-state", "paused")
    page.wait_for_timeout(7_500)
    expect(track).to_have_attribute("data-active-index", "2")
    expect(carousel).to_have_attribute("data-auto-advance-count", "2")

    page.locator("#catalogue-search-query").hover()
    expect(carousel).to_have_attribute("data-auto-state", "running")
    context.close()


def test_featured_carousel_arrows_and_active_slide_link_work(
    browser: Browser,
    browser_base_url: str,
) -> None:
    page = open_page(browser, browser_base_url)
    track = page.locator("[data-featured-track]")
    slides = page.locator("[data-featured-slide]")

    page.get_by_role("button", name="Next featured listing").click()
    expect(track).to_have_attribute("data-active-index", "1")
    expect(page.locator("[data-featured-current]")).to_have_text("2")
    expect(slides.nth(0)).to_have_attribute("aria-hidden", "true")
    expect(slides.nth(1)).to_have_attribute("aria-hidden", "false")
    expect(page.locator("[data-featured-status]")).to_contain_text(
        "Raspberry Pi 4 Workbench Set"
    )

    page.get_by_role("button", name="Previous featured listing").click()
    expect(track).to_have_attribute("data-active-index", "0")
    with page.expect_navigation(wait_until="domcontentloaded"):
        slides.nth(0).locator("[data-featured-link]").click()
    expect(page).to_have_url(
        re.compile(r"/listings/original-prusa-mini-plus$")
    )
    expect(page.get_by_role("heading", name="Original Prusa MINI+")).to_be_visible()
    page.context.close()


def test_category_chip_preserves_catalogue_scroll_position(
    browser: Browser,
    browser_base_url: str,
) -> None:
    page = open_page(browser, browser_base_url)
    electronics = page.locator(".category-chip-nav").get_by_role(
        "link", name="Electronics", exact=True
    )

    assert electronics.get_attribute("href").endswith(
        "/?category=Electronics#listings"
    )
    electronics.click()
    page.wait_for_url(re.compile(r"\?category=Electronics#listings$"))
    expect(page.locator("#listing-grid > [data-listing-id]")).to_have_count(4)

    scroll_position = page.evaluate("window.scrollY")
    listings_top = page.locator("#listings").evaluate(
        "element => element.getBoundingClientRect().top"
    )
    heading_top = page.locator("#catalogue-heading").evaluate(
        "element => element.getBoundingClientRect().top"
    )
    assert scroll_position > 0
    assert 80 <= listings_top <= 130
    assert 80 <= heading_top <= 180
    page.context.close()


def test_clear_search_restores_the_full_catalogue(
    browser: Browser,
    browser_base_url: str,
) -> None:
    page = open_page(browser, browser_base_url, "/?category=Electronics#listings")
    listing = load_listings()[1]
    search_response = {
        "query": "repair circuit boards",
        "results": [listing.model_dump(mode="json")],
    }
    page.route(
        "**/api/search",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(search_response),
        ),
    )

    expect(page.locator('[data-listing-id]')).to_have_count(4)
    page.get_by_role("button", name="Gallery view").click()
    expect(page.locator("#listing-grid")).to_have_attribute(
        "data-listing-view", "gallery"
    )
    assert page.locator("#listing-grid").evaluate(
        "element => getComputedStyle(element).gridTemplateColumns.split(' ').length"
    ) == 5
    page.locator("#catalogue-search-query").fill("repair circuit boards")
    page.locator("#catalogue-search-submit").click()
    expect(page.locator("#catalogue-heading")).to_have_text("AI search matches")
    expect(page.locator('[data-listing-id]')).to_have_count(1)
    expect(page.locator("[data-card-status]")).to_be_visible()
    expect(page.locator("[data-card-status]")).to_have_text("Reserved")
    expect(page.locator('[data-listing-status="Reserved"]')).to_have_count(1)
    expect(page.locator("[data-card-description]")).to_be_hidden()
    expect(page.locator("[data-card-condition]")).to_be_visible()

    with page.expect_navigation(wait_until="domcontentloaded"):
        page.locator("#catalogue-search-clear").click()

    expect(page).to_have_url(f"{browser_base_url}/#listings")
    expect(page.locator("#catalogue-heading")).to_have_text("Browse everything")
    expect(page.locator('[data-listing-id]')).to_have_count(16)
    expect(page.locator("#listing-grid")).to_have_attribute(
        "data-listing-view", "gallery"
    )
    expect(page.locator("#catalogue-search-query")).to_have_value("")
    expect(page.locator("#catalogue-search-clear")).to_have_class(re.compile(r"\bhidden\b"))

    page.context.close()


def test_nav_search_reuses_main_search_and_scrolls_to_its_results(
    browser: Browser,
    browser_base_url: str,
) -> None:
    page = open_page(browser, browser_base_url)
    listing = load_listings()[0]
    submitted_queries: list[str] = []

    def answer_search(route) -> None:
        query = route.request.post_data_json["query"]
        submitted_queries.append(query)
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {"query": query, "results": [listing.model_dump(mode="json")]}
            ),
        )

    page.route("**/api/search", answer_search)
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    assert page.evaluate("window.scrollY") > 500

    nav_input = page.get_by_label("Search Maker Swap catalogue")
    expect(nav_input).to_be_visible()
    nav_input.fill("  beginner   3D printer  ")
    nav_input.press("Enter")

    expect(page.locator("#catalogue-search-query")).to_have_value(
        "beginner 3D printer"
    )
    expect(page.locator("#catalogue-heading")).to_have_text("AI search matches")
    expect(page.locator("#listing-grid > [data-listing-id]")).to_have_count(1)
    expect(page.locator("#listing-grid > [data-listing-id]")).to_have_attribute(
        "data-listing-id", listing.id
    )
    page.wait_for_function(
        """() => {
            const top = document.querySelector('#catalogue-search')
                .getBoundingClientRect().top;
            return top >= 90 && top <= 130;
        }""",
        timeout=4_000,
    )
    assert submitted_queries == ["beginner 3D printer"]
    page.context.close()


def test_suggested_question_sends_and_stays_hidden_with_persisted_conversation(
    browser: Browser,
    browser_base_url: str,
) -> None:
    page = open_page(browser, browser_base_url)
    submitted_payloads: list[dict] = []

    def answer_question(route) -> None:
        submitted_payloads.append(route.request.post_data_json)
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "answer": "No listing includes warranty information.",
                    "sources": [],
                }
            ),
        )

    page.route("**/api/qa", answer_question)
    page.get_by_role("button", name="Open catalogue chat").click()
    empty_state = page.locator("#catalogue-chat-empty")
    suggestions = page.locator("[data-suggested-question]")
    expect(empty_state).to_be_visible()
    expect(suggestions).to_have_count(3)

    suggestion = page.get_by_role(
        "button", name="Does anything include a warranty?", exact=True
    )
    suggestion.click()

    expect(empty_state).to_be_hidden()
    for index in range(suggestions.count()):
        expect(suggestions.nth(index)).to_be_hidden()
    expect(
        page.locator('.catalogue-chat-message[data-role="user"]')
    ).to_contain_text("Does anything include a warranty?")
    expect(
        page.locator('.catalogue-chat-message[data-role="assistant"]')
    ).to_contain_text("No listing includes warranty information.")
    assert submitted_payloads == [
        {"question": "Does anything include a warranty?", "history": []}
    ]

    page.locator("#catalogue-chat-close").click()
    page.locator("#catalogue-chat-toggle").click()
    expect(empty_state).to_be_hidden()
    for index in range(suggestions.count()):
        expect(suggestions.nth(index)).to_be_hidden()

    page.reload(wait_until="networkidle")
    page.locator("#catalogue-chat-toggle").click()
    expect(page.locator(".catalogue-chat-message")).to_have_count(2)
    expect(empty_state).to_be_hidden()
    for index in range(suggestions.count()):
        expect(suggestions.nth(index)).to_be_hidden()
    page.context.close()


@pytest.mark.parametrize("width,height", [(390, 844), (430, 932)])
def test_suggested_questions_fit_chat_empty_state_on_mobile(
    browser: Browser,
    browser_base_url: str,
    width: int,
    height: int,
) -> None:
    page = open_page(
        browser,
        browser_base_url,
        viewport={"width": width, "height": height},
    )
    page.get_by_role("button", name="Open catalogue chat").click()
    panel = page.locator("#catalogue-chat-panel")
    empty_state = page.locator("#catalogue-chat-empty")
    scroll_region = page.locator(".catalogue-chat-scroll")
    suggestions = page.locator("[data-suggested-question]")

    expect(suggestions).to_have_count(3)
    panel_box = panel.bounding_box()
    empty_box = empty_state.bounding_box()
    scroll_metrics = scroll_region.evaluate(
        "element => ({clientHeight: element.clientHeight, scrollHeight: element.scrollHeight})"
    )
    suggestion_boxes = suggestions.evaluate_all(
        """elements => elements.map((element) => {
            const rect = element.getBoundingClientRect();
            return {x: rect.x, y: rect.y, width: rect.width, height: rect.height};
        })"""
    )
    assert panel_box is not None
    assert empty_box is not None
    assert scroll_metrics["scrollHeight"] <= scroll_metrics["clientHeight"] + 1
    for box in suggestion_boxes:
        assert box["x"] >= empty_box["x"]
        assert box["x"] + box["width"] <= empty_box["x"] + empty_box["width"] + 1
        assert box["height"] >= 40

    dimensions = page.evaluate(
        """() => ({
            viewport: window.innerWidth,
            document: document.documentElement.scrollWidth,
            body: document.body.scrollWidth,
        })"""
    )
    assert dimensions["document"] <= dimensions["viewport"] + 1
    assert dimensions["body"] <= dimensions["viewport"] + 1
    page.context.close()


def test_nav_search_from_detail_returns_to_the_same_home_search_flow(
    browser: Browser,
    browser_base_url: str,
) -> None:
    page = open_page(
        browser,
        browser_base_url,
        "/listings/original-prusa-mini-plus",
    )
    listing = load_listings()[4]
    submitted_queries: list[str] = []

    def answer_search(route) -> None:
        query = route.request.post_data_json["query"]
        submitted_queries.append(query)
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {"query": query, "results": [listing.model_dump(mode="json")]}
            ),
        )

    page.route("**/api/search", answer_search)
    page.get_by_label("Search Maker Swap catalogue").fill("soldering station")
    page.get_by_role("button", name="Search Maker Swap").click()

    expect(page).to_have_url(re.compile(r"/#catalogue-search$"))
    expect(page.locator("#catalogue-search-query")).to_have_value(
        "soldering station"
    )
    expect(page.locator("#catalogue-heading")).to_have_text("AI search matches")
    expect(page.locator("#listing-grid > [data-listing-id]")).to_have_count(1)
    assert submitted_queries == ["soldering station"]
    page.context.close()


@pytest.mark.parametrize("width,height", [(390, 844), (430, 932)])
def test_nav_search_expands_without_crowding_and_submits_on_mobile(
    browser: Browser,
    browser_base_url: str,
    width: int,
    height: int,
) -> None:
    page = open_page(
        browser,
        browser_base_url,
        viewport={"width": width, "height": height},
    )
    listing = load_listings()[0]
    submitted_queries: list[str] = []

    def answer_search(route) -> None:
        query = route.request.post_data_json["query"]
        submitted_queries.append(query)
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {"query": query, "results": [listing.model_dump(mode="json")]}
            ),
        )

    page.route("**/api/search", answer_search)
    nav = page.locator(".site-glass-nav")
    brand = page.locator(".site-brand")
    category_menu = page.locator("#site-category-menu")
    toggle = page.get_by_role("button", name="Open navigation search")
    nav_form = page.locator("#nav-search-form")

    expect(brand).to_be_visible()
    expect(category_menu).to_be_visible()
    expect(toggle).to_be_visible()
    expect(nav_form).to_be_hidden()
    collapsed_boxes = [
        element.bounding_box() for element in (brand, toggle, category_menu)
    ]
    assert all(box is not None for box in collapsed_boxes)
    for left, right in zip(collapsed_boxes, collapsed_boxes[1:]):
        assert left is not None and right is not None
        assert left["x"] + left["width"] <= right["x"] + 1
    toggle_box = toggle.bounding_box()
    assert toggle_box is not None
    assert toggle_box["width"] >= 44
    assert toggle_box["height"] >= 44

    toggle.click()
    expect(nav).to_have_class(re.compile(r"\bnav-search-expanded\b"))
    expect(nav_form).to_be_visible()
    expect(brand).to_be_hidden()
    expect(category_menu).to_be_hidden()
    nav_input = page.get_by_label("Search Maker Swap catalogue")
    expect(nav_input).to_be_focused()
    expanded_box = nav_form.bounding_box()
    assert expanded_box is not None
    assert expanded_box["x"] >= 0
    assert expanded_box["x"] + expanded_box["width"] <= width + 1

    nav_input.press("Escape")
    expect(nav_form).to_be_hidden()
    expect(toggle).to_be_focused()
    toggle.click()
    nav_input.fill("beginner printer")
    page.get_by_role("button", name="Search Maker Swap").click()

    expect(nav_form).to_be_hidden()
    expect(brand).to_be_visible()
    expect(category_menu).to_be_visible()
    expect(page.locator("#catalogue-search-query")).to_have_value(
        "beginner printer"
    )
    expect(page.locator("#catalogue-heading")).to_have_text("AI search matches")
    assert submitted_queries == ["beginner printer"]
    dimensions = page.evaluate(
        """() => ({
            viewport: window.innerWidth,
            document: document.documentElement.scrollWidth,
            body: document.body.scrollWidth,
        })"""
    )
    assert dimensions["document"] <= dimensions["viewport"] + 1
    assert dimensions["body"] <= dimensions["viewport"] + 1
    page.context.close()


def test_gallery_preference_survives_category_filtering(
    browser: Browser,
    browser_base_url: str,
) -> None:
    page = open_page(browser, browser_base_url)

    expect(page.locator("#listing-grid")).to_have_attribute("data-listing-view", "list")
    page.get_by_role("button", name="Gallery view").click()
    expect(page.locator("#listing-grid")).to_have_attribute(
        "data-listing-view", "gallery"
    )

    page.locator("#category-menu-toggle").click()
    page.locator(".site-dropdown-panel").get_by_role(
        "link", name="Electronics", exact=True
    ).click()
    page.wait_for_url(re.compile(r"\?category=Electronics#listings$"))

    expect(page.locator("#listing-grid")).to_have_attribute(
        "data-listing-view", "gallery"
    )
    expect(page.locator('[data-listing-id]')).to_have_count(4)
    expect(page.locator("#catalogue-heading")).to_have_text("Electronics")
    assert page.locator("#listing-grid").evaluate(
        "element => getComputedStyle(element).gridTemplateColumns.split(' ').length"
    ) == 5
    expect(page.get_by_role("button", name="Gallery view")).to_have_attribute(
        "aria-pressed", "true"
    )
    page.context.close()


def test_category_chips_and_dropdown_stay_synchronized(
    browser: Browser,
    browser_base_url: str,
) -> None:
    page = open_page(browser, browser_base_url)
    chips = page.locator(".category-chip-nav")
    dropdown = page.locator(".site-dropdown-panel")

    expect(chips.get_by_role("link", name="All", exact=True)).to_have_attribute(
        "aria-current", "page"
    )
    page.locator("#category-menu-toggle").click()
    expect(
        dropdown.get_by_role("link", name="All Listings", exact=True)
    ).to_have_attribute("aria-current", "page")
    page.keyboard.press("Escape")

    chips.get_by_role("link", name="Electronics", exact=True).click()
    page.wait_for_url(re.compile(r"\?category=Electronics#listings$"))
    expect(page.locator("#listing-grid > [data-listing-id]")).to_have_count(4)
    expect(
        page.locator(".category-chip-nav").get_by_role(
            "link", name="Electronics", exact=True
        )
    ).to_have_attribute("aria-current", "page")
    page.locator("#category-menu-toggle").click()
    expect(
        page.locator(".site-dropdown-panel").get_by_role(
            "link", name="Electronics", exact=True
        )
    ).to_have_attribute("aria-current", "page")

    page.locator(".site-dropdown-panel").get_by_role(
        "link", name="Art Supplies", exact=True
    ).click()
    page.wait_for_url(re.compile(r"\?category=Art(%20|\+)%26(%20|\+)Craft#listings$"))
    expect(page.locator("#listing-grid > [data-listing-id]")).to_have_count(3)
    expect(
        page.locator(".category-chip-nav").get_by_role(
            "link", name="Art & Craft", exact=True
        )
    ).to_have_attribute("aria-current", "page")
    page.locator("#category-menu-toggle").click()
    expect(
        page.locator(".site-dropdown-panel").get_by_role(
            "link", name="Art Supplies", exact=True
        )
    ).to_have_attribute("aria-current", "page")
    page.context.close()


@pytest.mark.parametrize("width,height", [(390, 844), (430, 932)])
def test_compact_catalogue_gallery_is_two_columns_and_readable_on_mobile(
    browser: Browser,
    browser_base_url: str,
    width: int,
    height: int,
) -> None:
    page = open_page(
        browser,
        browser_base_url,
        "/#listings",
        {"width": width, "height": height},
    )
    grid = page.locator("#listing-grid")
    first_card = page.locator('[data-listing-id="original-prusa-mini-plus"]')
    list_button = page.get_by_role("button", name="List view")
    gallery_button = page.get_by_role("button", name="Gallery view")

    expect(grid).to_have_attribute("data-listing-view", "list")
    expect(list_button).to_have_attribute("aria-pressed", "true")
    expect(first_card.locator("[data-card-description]")).to_be_visible()
    list_state = grid.evaluate(
        """element => ({
            columns: getComputedStyle(element).gridTemplateColumns.split(' ').length,
            cardWidth: element.querySelector('[data-listing-id]').getBoundingClientRect().width,
            image: (() => {
                const box = element.querySelector('[data-card-image-frame]').getBoundingClientRect();
                return { width: box.width, height: box.height };
            })(),
        })"""
    )
    assert list_state["columns"] == 1
    assert list_state["image"]["width"] / list_state["image"]["height"] == pytest.approx(
        4 / 3, rel=0.02
    )

    gallery_button.focus()
    gallery_button.press("Enter")
    expect(grid).to_have_attribute("data-listing-view", "gallery")
    expect(gallery_button).to_have_attribute("aria-pressed", "true")
    expect(list_button).to_have_attribute("aria-pressed", "false")
    expect(page.locator("#listing-view-status")).to_have_text("Gallery view selected.")

    gallery_state = grid.evaluate(
        """element => ({
            columns: getComputedStyle(element).gridTemplateColumns.split(' ').length,
            documentWidth: document.documentElement.scrollWidth,
            viewportWidth: window.innerWidth,
            cards: [...element.querySelectorAll('[data-listing-id]')].slice(0, 2).map(card => {
                const box = card.getBoundingClientRect();
                return { x: box.x, y: box.y, width: box.width };
            }),
            image: (() => {
                const box = element.querySelector('[data-card-image-frame]').getBoundingClientRect();
                return { width: box.width, height: box.height };
            })(),
        })"""
    )
    assert gallery_state["columns"] == 2
    assert gallery_state["documentWidth"] <= gallery_state["viewportWidth"] + 1
    assert gallery_state["cards"][0]["y"] == pytest.approx(
        gallery_state["cards"][1]["y"], abs=1
    )
    assert gallery_state["cards"][0]["x"] < gallery_state["cards"][1]["x"]
    assert gallery_state["cards"][0]["width"] < list_state["cardWidth"] * 0.55
    assert gallery_state["image"]["width"] / gallery_state["image"]["height"] == pytest.approx(
        1, rel=0.02
    )

    expect(first_card.locator("[data-card-title]")).to_be_visible()
    expect(first_card.locator("[data-card-price]")).to_be_visible()
    expect(first_card.locator("[data-card-condition]")).to_be_visible()
    expect(first_card.locator("[data-card-description]")).to_be_hidden()
    expect(first_card.locator("[data-card-category]")).to_be_hidden()
    expect(first_card.locator("[data-card-pickup-block]")).to_be_hidden()

    for listing_id, expected_status in (
        ("bambu-lab-a1-mini", "Reserved"),
        ("arduino-sensor-starter-kit", "Sold"),
    ):
        card = page.locator(f'[data-listing-id="{listing_id}"]')
        badge = card.locator(f'[data-status="{expected_status}"]')
        expect(badge).to_be_visible()
        badge_state = badge.evaluate(
            """element => {
                const style = getComputedStyle(element);
                const badge = element.getBoundingClientRect();
                const frame = element.closest('[data-card-image-frame]').getBoundingClientRect();
                return {
                    color: style.color,
                    background: style.backgroundColor,
                    fontSize: parseFloat(style.fontSize),
                    badge: { x: badge.x, y: badge.y, width: badge.width, height: badge.height },
                    frame: { x: frame.x, y: frame.y, width: frame.width, height: frame.height },
                };
            }"""
        )
        assert badge_state["fontSize"] >= 10
        assert contrast_ratio(
            css_channels(badge_state["color"])[:3],
            css_channels(badge_state["background"])[:3],
        ) >= 4.5
        assert badge_state["badge"]["x"] >= badge_state["frame"]["x"]
        assert (
            badge_state["badge"]["x"] + badge_state["badge"]["width"]
            <= badge_state["frame"]["x"] + badge_state["frame"]["width"] + 1
        )

    list_button.click()
    expect(grid).to_have_attribute("data-listing-view", "list")
    restored_state = grid.evaluate(
        """element => ({
            columns: getComputedStyle(element).gridTemplateColumns.split(' ').length,
            cardWidth: element.querySelector('[data-listing-id]').getBoundingClientRect().width,
        })"""
    )
    assert restored_state["columns"] == 1
    assert restored_state["cardWidth"] == pytest.approx(list_state["cardWidth"], abs=1)
    expect(first_card.locator("[data-card-description]")).to_be_visible()
    page.context.close()


@pytest.mark.parametrize("width,height", [(390, 844), (430, 932)])
def test_featured_carousel_controls_fit_mobile_viewports(
    browser: Browser,
    browser_base_url: str,
    width: int,
    height: int,
) -> None:
    page = open_page(
        browser,
        browser_base_url,
        "/",
        {"width": width, "height": height},
    )
    carousel = page.locator("[data-featured-carousel]")
    intro_slide = page.locator("[data-hero-intro-slide]")
    intro_heading = intro_slide.get_by_role(
        "heading", name="Good tools deserve a second project."
    )
    previous_button = page.get_by_role("button", name="Previous featured listing")
    next_button = page.get_by_role("button", name="Next featured listing")
    expect(page.locator("[data-featured-track]")).to_have_attribute(
        "data-active-index", "0"
    )
    next_button.scroll_into_view_if_needed()

    dimensions = page.evaluate(
        """() => ({
            viewport: window.innerWidth,
            document: document.documentElement.scrollWidth,
            body: document.body.scrollWidth,
        })"""
    )
    assert dimensions["document"] <= dimensions["viewport"] + 1
    assert dimensions["body"] <= dimensions["viewport"] + 1
    assert carousel.get_attribute("data-interval-ms") == "7000"
    assert 6_000 <= int(carousel.get_attribute("data-interval-ms")) <= 9_000
    intro_geometry = intro_slide.evaluate(
        """element => {
            const slide = element.getBoundingClientRect();
            const heading = element.querySelector('h1').getBoundingClientRect();
            const copy = element.querySelector('.hero-intro-copy');
            return {
                slide: { x: slide.x, y: slide.y, width: slide.width, height: slide.height },
                heading: {
                    x: heading.x,
                    y: heading.y,
                    width: heading.width,
                    height: heading.height,
                },
                copyClientHeight: copy.clientHeight,
                copyScrollHeight: copy.scrollHeight,
            };
        }"""
    )
    assert intro_geometry["heading"]["x"] >= intro_geometry["slide"]["x"]
    assert (
        intro_geometry["heading"]["x"] + intro_geometry["heading"]["width"]
        <= intro_geometry["slide"]["x"] + intro_geometry["slide"]["width"] + 1
    )
    assert intro_geometry["heading"]["y"] >= intro_geometry["slide"]["y"]
    assert (
        intro_geometry["heading"]["y"] + intro_geometry["heading"]["height"]
        <= intro_geometry["slide"]["y"] + intro_geometry["slide"]["height"] + 1
    )
    assert intro_geometry["copyScrollHeight"] <= intro_geometry["copyClientHeight"] + 1
    expect(intro_heading).to_be_visible()

    for button in (previous_button, next_button):
        box = button.bounding_box()
        assert box is not None
        assert box["width"] >= 44
        assert box["height"] >= 44
        assert box["x"] >= 0
        assert box["x"] + box["width"] <= width + 1
        assert box["y"] >= 0
        assert box["y"] + box["height"] <= height + 1

    next_button.click()
    expect(page.locator("[data-featured-track]")).to_have_attribute(
        "data-active-index", "1"
    )
    expect(
        page.locator('[data-featured-id="raspberry-pi-4-workbench"]')
    ).to_have_attribute("aria-hidden", "false")
    page.context.close()


@pytest.mark.parametrize(
    "path",
    ["/", "/listings/original-prusa-mini-plus", "/notes"],
)
def test_glass_navigation_remains_legible_across_page_backgrounds(
    browser: Browser,
    browser_base_url: str,
    path: str,
) -> None:
    page = open_page(browser, browser_base_url, path)

    nav_state = page.locator(".site-glass-nav").evaluate(
        """element => {
            const style = getComputedStyle(element);
            const rect = element.getBoundingClientRect();
            return {
                background: style.backgroundColor,
                backdrop: style.backdropFilter || style.webkitBackdropFilter,
                top: rect.top,
                position: getComputedStyle(element.closest('header')).position,
                brandColor: getComputedStyle(element.querySelector('.site-brand')).color,
                toggleColor: getComputedStyle(element.querySelector('.site-nav-pill')).color,
            };
        }"""
    )
    assert nav_state["position"] == "fixed"
    assert "rgba" in nav_state["background"]
    assert "blur" in nav_state["backdrop"]
    assert 0 <= nav_state["top"] <= 20
    assert glass_contrast_over_darkest_background(
        nav_state["brandColor"], nav_state["background"]
    ) >= 4.5
    assert glass_contrast_over_darkest_background(
        nav_state["toggleColor"], nav_state["background"]
    ) >= 4.5
    expect(page.get_by_label("Maker Swap, view all listings")).to_be_visible()
    expect(page.locator("#category-menu-toggle")).to_be_visible()

    page.evaluate("window.scrollTo(0, Math.min(500, document.body.scrollHeight / 2))")
    assert page.locator(".site-glass-nav").evaluate(
        "element => element.getBoundingClientRect().top"
    ) <= 20

    page.locator("#category-menu-toggle").click()
    panel = page.locator(".site-dropdown-panel")
    expect(panel).to_be_visible()
    expect(panel.get_by_role("link", name="All Listings", exact=True)).to_be_visible()
    panel_state = panel.evaluate(
        """element => {
            const style = getComputedStyle(element);
            return {
                background: style.backgroundColor,
                backdrop: style.backdropFilter || style.webkitBackdropFilter,
                color: getComputedStyle(element.querySelector('a')).color,
            };
        }"""
    )
    assert "rgba" in panel_state["background"]
    assert "blur" in panel_state["backdrop"]
    assert css_channels(panel_state["background"])[3] > css_channels(
        nav_state["background"]
    )[3]
    assert glass_contrast_over_darkest_background(
        panel_state["color"], panel_state["background"]
    ) >= 4.5
    text_channels = [int(value) for value in re.findall(r"\d+", panel_state["color"])[:3]]
    assert len(text_channels) == 3
    assert sum(text_channels) <= 230

    page.keyboard.press("Escape")
    expect(panel).to_be_hidden()
    expect(page.locator("#category-menu-toggle")).to_be_focused()
    page.context.close()


def test_simulated_checkout_confirms_without_network_or_catalogue_mutation(
    browser: Browser,
    browser_base_url: str,
) -> None:
    page = open_page(
        browser,
        browser_base_url,
        "/listings/original-prusa-mini-plus",
    )
    trigger = page.get_by_role("button", name="Simulated Buy / Reserve")
    dialog = page.locator("#simulated-checkout-dialog")

    expect(trigger).to_be_visible()
    expect(dialog).to_be_hidden()
    trigger.focus()
    trigger.press("Enter")
    expect(dialog).to_be_visible()
    expect(dialog).to_have_attribute("open", "")
    expect(page.locator("body")).to_have_class(re.compile("simulated-checkout-open"))
    expect(dialog.get_by_role("heading", name="Review your pickup")).to_be_visible()
    expect(dialog).to_contain_text("Original Prusa MINI+")
    expect(dialog).to_contain_text("Good")
    expect(dialog).to_contain_text("S$420")
    expect(dialog).to_contain_text("Local pickup")
    expect(dialog).to_contain_text("Jurong East")
    expect(dialog).to_contain_text(
        "This is a simulated demo checkout — no real payment is processed."
    )
    expect(dialog.locator("form, input, select, textarea")).to_have_count(0)

    page.keyboard.press("Escape")
    expect(dialog).to_be_hidden()
    expect(trigger).to_be_focused()

    requests_after_open: list[str] = []
    page.on("request", lambda request: requests_after_open.append(request.url))
    trigger.click()
    dialog.get_by_role("button", name="Confirm Order").click()
    expect(page.locator("[data-checkout-review]")).to_be_hidden()
    success = page.locator("[data-checkout-success]")
    expect(success).to_be_visible()
    expect(success).to_contain_text("Reservation Confirmed!")
    expect(success).to_contain_text(re.compile(r"Reference #\d{6}"))
    expect(page.locator('[data-status="Available"]')).to_be_visible()
    assert requests_after_open == []

    dialog.get_by_role("button", name="Done").click()
    expect(dialog).to_be_hidden()
    expect(trigger).to_be_focused()
    page.reload(wait_until="networkidle")
    expect(page.locator('[data-status="Available"]')).to_be_visible()
    expect(page.get_by_role("button", name="Simulated Buy / Reserve")).to_be_visible()
    page.context.close()


@pytest.mark.parametrize("width,height", [(390, 844), (430, 932)])
def test_simulated_checkout_fits_mobile_viewports(
    browser: Browser,
    browser_base_url: str,
    width: int,
    height: int,
) -> None:
    page = open_page(
        browser,
        browser_base_url,
        "/listings/original-prusa-mini-plus",
        {"width": width, "height": height},
    )
    trigger = page.get_by_role("button", name="Simulated Buy / Reserve")
    trigger.scroll_into_view_if_needed()
    trigger.click()

    dialog = page.locator("#simulated-checkout-dialog")
    expect(dialog).to_be_visible()
    dialog_box = dialog.bounding_box()
    assert dialog_box is not None
    assert dialog_box["x"] >= 0
    assert dialog_box["y"] >= 0
    assert dialog_box["x"] + dialog_box["width"] <= width + 1
    assert dialog_box["y"] + dialog_box["height"] <= height + 1
    dialog_dimensions = dialog.evaluate(
        """element => ({
            clientWidth: element.clientWidth,
            scrollWidth: element.scrollWidth,
            clientHeight: element.clientHeight,
            scrollHeight: element.scrollHeight,
        })"""
    )
    assert dialog_dimensions["scrollWidth"] <= dialog_dimensions["clientWidth"] + 1

    confirm = dialog.get_by_role("button", name="Confirm Order")
    confirm.scroll_into_view_if_needed()
    confirm_box = confirm.bounding_box()
    assert confirm_box is not None
    assert confirm_box["width"] >= 44
    assert confirm_box["height"] >= 44
    confirm.click()
    expect(page.locator("[data-checkout-success]")).to_be_visible()
    done = dialog.get_by_role("button", name="Done")
    done_box = done.bounding_box()
    assert done_box is not None
    assert done_box["width"] >= 44
    assert done_box["height"] >= 44
    done.click()
    expect(trigger).to_be_focused()
    page.context.close()


@pytest.mark.parametrize("width,height", [(390, 844), (430, 932)])
def test_polished_navigation_and_gallery_fit_mobile_viewports(
    browser: Browser,
    browser_base_url: str,
    width: int,
    height: int,
) -> None:
    page = open_page(
        browser,
        browser_base_url,
        "/listings/bambu-lab-a1-mini",
        {"width": width, "height": height},
    )

    dimensions = page.evaluate(
        """() => ({
            viewport: window.innerWidth,
            document: document.documentElement.scrollWidth,
            body: document.body.scrollWidth,
        })"""
    )
    assert dimensions["document"] <= dimensions["viewport"] + 1
    assert dimensions["body"] <= dimensions["viewport"] + 1

    page.locator("#category-menu-toggle").click()
    panel_box = page.locator(".site-dropdown-panel").bounding_box()
    assert panel_box is not None
    assert panel_box["x"] >= 0
    assert panel_box["x"] + panel_box["width"] <= width + 1
    page.keyboard.press("Escape")

    expect(page.locator('[data-status="Reserved"]')).to_be_visible()
    expect(page.locator("[data-checkout-open]")).to_have_count(0)
    expect(page.locator("[data-checkout-dialog]")).to_have_count(0)
    thumbnails = page.locator("[data-gallery-thumbnail]")
    expect(thumbnails).to_have_count(3)
    original_source = page.locator("[data-gallery-main]").get_attribute("src")
    page.locator("[data-gallery-next]").click()
    expect(page.locator("[data-gallery-counter]")).to_have_text("2 / 3")
    assert page.locator("[data-gallery-main]").get_attribute("src") != original_source

    thumbnails.nth(0).click()
    thumbnails.nth(0).press("ArrowRight")
    expect(thumbnails.nth(1)).to_have_attribute("aria-pressed", "true")
    expect(thumbnails.nth(1)).to_be_focused()
    page.context.close()


def test_qa_renders_only_direct_citation_links(
    browser: Browser,
    browser_base_url: str,
) -> None:
    page = open_page(browser, browser_base_url)

    def answer_question(route) -> None:
        question = route.request.post_data_json["question"]
        if question == "What products are in here?":
            response = {
                "question": question,
                "answer": "Maker Swap has items across five maker categories.",
                "sources": [],
            }
        else:
            response = {
                "question": question,
                "answer": "The Hakko station costs S$115.",
                "sources": [
                    {
                        "id": "hakko-fx888d-station",
                        "title": "Hakko FX-888D Soldering Station",
                    }
                ],
            }
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(response),
        )

    page.route("**/api/qa", answer_question)
    page.locator("#catalogue-chat-toggle").click()

    question_input = page.locator("#catalogue-chat-question")
    question_input.fill("What products are in here?")
    page.locator("#catalogue-chat-submit").click()
    answers = page.locator('.catalogue-chat-message[data-role="assistant"]')
    expect(answers).to_have_count(1)
    expect(answers.nth(0).locator(".catalogue-chat-source")).to_have_count(0)

    question_input.fill("How much is the Hakko station?")
    page.locator("#catalogue-chat-submit").click()
    expect(answers).to_have_count(2)
    direct_link = answers.nth(1).locator(".catalogue-chat-source")
    expect(direct_link).to_have_count(1)
    expect(direct_link).to_have_text("Hakko FX-888D Soldering Station")
    expect(direct_link).to_have_attribute("href", "/listings/hakko-fx888d-station")

    with page.expect_navigation(wait_until="domcontentloaded"):
        direct_link.click()
    expect(page).to_have_url(
        re.compile(r"/listings/hakko-fx888d-station$")
    )
    expect(page.get_by_role("heading", name="Hakko FX-888D Soldering Station")).to_be_visible()

    page.context.close()
