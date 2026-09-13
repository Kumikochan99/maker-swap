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
    electronics = page.get_by_role("link", name="Electronics", exact=True)
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
    page.locator("#catalogue-search-query").fill("repair circuit boards")
    page.locator("#catalogue-search-submit").click()
    expect(page.locator("#catalogue-heading")).to_have_text("AI search matches")
    expect(page.locator('[data-listing-id]')).to_have_count(1)
    expect(page.locator("[data-card-status]")).to_be_visible()
    expect(page.locator("[data-card-status]")).to_have_text("Reserved")
    expect(page.locator('[data-listing-status="Reserved"]')).to_have_count(1)

    with page.expect_navigation(wait_until="domcontentloaded"):
        page.locator("#catalogue-search-clear").click()

    expect(page).to_have_url(f"{browser_base_url}/#listings")
    expect(page.locator("#catalogue-heading")).to_have_text("Browse everything")
    expect(page.locator('[data-listing-id]')).to_have_count(16)
    expect(page.locator("#catalogue-search-query")).to_have_value("")
    expect(page.locator("#catalogue-search-clear")).to_have_class(re.compile(r"\bhidden\b"))

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
    expect(page.get_by_role("link", name="All Listings", exact=True)).to_be_visible()
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
