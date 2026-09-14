"""Live mobile-layout and basic accessibility checks for Phase 6."""

import json
import os
import re
import tempfile
from pathlib import Path

import pytest
from playwright.sync_api import Browser, Page, expect, sync_playwright


BASE_URL = os.environ.get(
    "MAKER_SWAP_TEST_URL",
    "https://maker-swap.onrender.com",
).rstrip("/")
EDGE_PATH = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
ARTIFACT_DIR = Path(tempfile.gettempdir()) / "maker-swap-phase6-mobile"
VIEWPORTS = (
    {"width": 390, "height": 844},
    {"width": 430, "height": 932},
)


def boxes_overlap(left: dict[str, float], right: dict[str, float]) -> bool:
    return not (
        left["x"] + left["width"] <= right["x"]
        or right["x"] + right["width"] <= left["x"]
        or left["y"] + left["height"] <= right["y"]
        or right["y"] + right["height"] <= left["y"]
    )


def assert_no_horizontal_page_overflow(page: Page) -> None:
    dimensions = page.evaluate(
        """() => ({
            viewport: window.innerWidth,
            document: document.documentElement.scrollWidth,
            body: document.body.scrollWidth,
        })"""
    )
    assert dimensions["document"] <= dimensions["viewport"] + 1
    assert dimensions["body"] <= dimensions["viewport"] + 1


def assert_inside_viewport(page: Page, selector: str) -> dict[str, float]:
    box = page.locator(selector).bounding_box()
    assert box is not None
    viewport = page.viewport_size
    assert viewport is not None
    assert box["x"] >= 0
    assert box["y"] >= 0
    assert box["x"] + box["width"] <= viewport["width"] + 1
    assert box["y"] + box["height"] <= viewport["height"] + 1
    return box


def parse_rgb(color: str) -> tuple[float, float, float]:
    channels = re.findall(r"[\d.]+", color)
    if len(channels) < 3:
        raise AssertionError(f"Could not parse browser color {color!r}")
    return tuple(float(channel) / 255 for channel in channels[:3])


def relative_luminance(color: str) -> float:
    def linearize(channel: float) -> float:
        return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4

    red, green, blue = (linearize(channel) for channel in parse_rgb(color))
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast_ratio(foreground: str, background: str) -> float:
    light, dark = sorted(
        (relative_luminance(foreground), relative_luminance(background)),
        reverse=True,
    )
    return (light + 0.05) / (dark + 0.05)


def measured_contrast(
    page: Page,
    foreground_selector: str,
    background_selector: str | None = None,
) -> float:
    foreground = page.locator(foreground_selector).first.evaluate(
        "element => getComputedStyle(element).color"
    )
    background = page.locator(background_selector or foreground_selector).first.evaluate(
        "element => getComputedStyle(element).backgroundColor"
    )
    return contrast_ratio(foreground, background)


def focused_element_state(page: Page) -> dict[str, object]:
    return page.evaluate(
        """() => {
            const element = document.activeElement;
            const style = getComputedStyle(element);
            const box = element.getBoundingClientRect();
            return {
                id: element.id,
                className: String(element.className),
                tagName: element.tagName,
                outlineStyle: style.outlineStyle,
                outlineWidth: parseFloat(style.outlineWidth),
                box: { x: box.x, y: box.y, width: box.width, height: box.height },
            };
        }"""
    )


def verify_keyboard_and_labels(page: Page) -> dict[str, object]:
    search_input = page.get_by_label("Search the catalogue in natural language")
    expect(search_input).to_have_attribute("id", "catalogue-search-query")
    expect(page.get_by_role("button", name="Find matches")).to_be_visible()
    assert page.locator("img:not([alt])").count() == 0
    assert page.locator("button").evaluate_all(
        """buttons => buttons.every(button =>
            Boolean(button.getAttribute('aria-label') || button.textContent.trim())
        )"""
    )

    page.keyboard.press("Tab")
    skip_focus = focused_element_state(page)
    assert "skip-link" in skip_focus["className"]
    assert skip_focus["outlineStyle"] != "none"
    assert skip_focus["outlineWidth"] >= 3
    assert skip_focus["box"]["y"] >= 0

    input_focus = None
    for _ in range(20):
        page.keyboard.press("Tab")
        candidate = focused_element_state(page)
        if candidate["id"] == "catalogue-search-query":
            input_focus = candidate
            break

    assert input_focus is not None
    assert input_focus["id"] == "catalogue-search-query"
    assert input_focus["outlineStyle"] != "none"
    assert input_focus["outlineWidth"] >= 3

    toggle_focus = None
    for _ in range(40):
        page.keyboard.press("Tab")
        candidate = focused_element_state(page)
        if candidate["id"] == "catalogue-chat-toggle":
            toggle_focus = candidate
            break

    assert toggle_focus is not None
    assert toggle_focus["id"] == "catalogue-chat-toggle"
    assert toggle_focus["outlineStyle"] != "none"
    assert toggle_focus["outlineWidth"] >= 3

    page.keyboard.press("Enter")
    expect(page.locator("#catalogue-chat-panel")).to_be_visible()
    expect(page.get_by_label("Ask a question about the catalogue")).to_be_focused()
    page.keyboard.press("Escape")
    expect(page.locator("#catalogue-chat-panel")).to_be_hidden()
    expect(page.locator("#catalogue-chat-toggle")).to_be_focused()

    return {
        "skip_link": skip_focus,
        "search_input": input_focus,
        "chat_toggle": toggle_focus,
        "chat_keyboard_open_and_escape": True,
    }


def verify_glass_navigation(page: Page) -> dict[str, object]:
    nav = page.locator(".site-glass-nav")
    style = nav.evaluate(
        """element => {
            const style = getComputedStyle(element);
            return {
                background: style.backgroundColor,
                backdrop: style.backdropFilter || style.webkitBackdropFilter,
                position: getComputedStyle(element.closest('header')).position,
            };
        }"""
    )
    assert style["position"] == "fixed"
    assert "rgba" in style["background"]
    assert "blur" in style["backdrop"]

    toggle = page.locator("#category-menu-toggle")
    toggle.click()
    expect(toggle).to_have_attribute("aria-expanded", "true")
    panel = page.locator(".site-dropdown-panel")
    panel_box = assert_inside_viewport(page, ".site-dropdown-panel")
    expect(panel.get_by_role("link", name="All Listings", exact=True)).to_be_visible()
    expect(panel.get_by_role("link", name="Art Supplies", exact=True)).to_be_visible()
    page.keyboard.press("Escape")
    expect(panel).to_be_hidden()
    expect(toggle).to_be_focused()

    return {"style": style, "panel": panel_box, "escape_returns_focus": True}


def verify_viewport(
    browser: Browser,
    viewport: dict[str, int],
) -> dict[str, object]:
    context = browser.new_context(viewport=viewport)
    page = context.new_page()
    response = page.goto(f"{BASE_URL}/", wait_until="networkidle")
    assert response is not None and response.ok
    assert_no_horizontal_page_overflow(page)
    expect(page.locator("#catalogue-search-query")).to_be_visible()
    expect(page.locator("#catalogue-search-submit")).to_be_visible()
    expect(page.locator("#listing-grid > [data-listing-id]")).to_have_count(16)
    first_card_box = page.locator("#listing-grid > [data-listing-id]").first.bounding_box()
    assert first_card_box is not None and first_card_box["width"] <= viewport["width"]

    featured_carousel = page.locator("[data-featured-carousel]")
    featured_track = page.locator("[data-featured-track]")
    intro_slide = page.locator("[data-hero-intro-slide]")
    intro_heading = intro_slide.get_by_role(
        "heading", name="Good tools deserve a second project."
    )
    expect(featured_carousel).to_be_visible()
    expect(page.locator("[data-featured-slide]")).to_have_count(4)
    expect(featured_track).to_have_attribute("data-active-index", "0")
    featured_interval = int(featured_carousel.get_attribute("data-interval-ms"))
    assert 6_000 <= featured_interval <= 9_000
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
    intro_heading.scroll_into_view_if_needed()
    page.screenshot(
        path=ARTIFACT_DIR / f"hero-carousel-intro-{viewport['width']}.png",
        full_page=False,
    )

    expect(featured_track).to_have_attribute(
        "data-active-index", "1", timeout=featured_interval + 2_500
    )
    expect(featured_carousel).to_have_attribute("data-last-advance", "auto")
    expect(
        page.locator('[data-featured-id="original-prusa-mini-plus"]')
    ).to_have_attribute("aria-hidden", "true")

    featured_next = page.get_by_role("button", name="Next featured listing")
    featured_next.scroll_into_view_if_needed()
    featured_previous_box = assert_inside_viewport(
        page, "[data-featured-previous]"
    )
    featured_next_box = assert_inside_viewport(page, "[data-featured-next]")
    assert featured_previous_box["width"] >= 44
    assert featured_previous_box["height"] >= 44
    assert featured_next_box["width"] >= 44
    assert featured_next_box["height"] >= 44
    page.get_by_role("button", name="Previous featured listing").click()
    expect(featured_track).to_have_attribute("data-active-index", "0")
    featured_next.click()
    expect(featured_track).to_have_attribute("data-active-index", "1")
    expect(
        page.locator('[data-featured-id="raspberry-pi-4-workbench"]')
    ).to_have_attribute("aria-hidden", "false")
    page.wait_for_timeout(600)
    featured_geometry = featured_carousel.evaluate(
        """element => {
            const viewportElement = element.querySelector('.hero-carousel-viewport');
            const viewport = viewportElement.getBoundingClientRect();
            const active = element.querySelector('[aria-hidden="false"]')
                .getBoundingClientRect();
            return {
                viewport: {
                    x: viewport.x + viewportElement.clientLeft,
                    width: viewportElement.clientWidth,
                },
                active: { x: active.x, width: active.width },
            };
        }"""
    )
    assert featured_geometry["active"]["x"] == pytest.approx(
        featured_geometry["viewport"]["x"], abs=1
    ), featured_geometry
    assert featured_geometry["active"]["width"] == pytest.approx(
        featured_geometry["viewport"]["width"], abs=1
    ), featured_geometry
    assert_no_horizontal_page_overflow(page)
    page.screenshot(
        path=ARTIFACT_DIR / f"hero-carousel-product-{viewport['width']}.png",
        full_page=False,
    )

    chip_nav = page.locator(".category-chip-nav")
    expect(chip_nav).to_be_visible()
    chip_metrics = chip_nav.evaluate(
        """element => {
            const box = element.getBoundingClientRect();
            return {
                x: box.x,
                width: box.width,
                clientWidth: element.clientWidth,
                scrollWidth: element.scrollWidth,
                pillCount: element.querySelectorAll('.category-pill').length,
            };
        }"""
    )
    assert chip_metrics["x"] >= 0
    assert chip_metrics["x"] + chip_metrics["width"] <= viewport["width"] + 1
    assert chip_metrics["pillCount"] == 6
    assert chip_metrics["scrollWidth"] >= chip_metrics["clientWidth"]
    expect(chip_nav.get_by_role("link", name="All", exact=True)).to_have_attribute(
        "aria-current", "page"
    )
    chip_nav.scroll_into_view_if_needed()
    page.screenshot(
        path=ARTIFACT_DIR / f"browse-chips-list-{viewport['width']}.png",
        full_page=False,
    )

    glass_navigation = verify_glass_navigation(page)
    page.goto(f"{BASE_URL}/", wait_until="networkidle")
    keyboard = verify_keyboard_and_labels(page)
    contrast = {
        "hero_heading": measured_contrast(page, ".hero-grid h1", ".hero-grid"),
        "search_input": measured_contrast(page, "#catalogue-search-query"),
        "search_button": measured_contrast(page, "#catalogue-search-submit"),
        "nav_brand": measured_contrast(page, ".site-brand", ".site-glass-nav"),
        "footer_copy": measured_contrast(page, ".site-footer p", ".site-footer"),
        "chat_toggle": measured_contrast(page, "#catalogue-chat-toggle"),
        "featured_title": measured_contrast(
            page, ".hero-product-copy h2", ".hero-product-copy"
        ),
    }
    assert all(ratio >= 4.5 for ratio in contrast.values())

    gallery_button = page.get_by_role("button", name="Gallery view")
    gallery_button.click()
    expect(page.locator("#listing-grid")).to_have_attribute(
        "data-listing-view", "gallery"
    )
    gallery_metrics = page.locator("#listing-grid").evaluate(
        """element => ({
            columns: getComputedStyle(element).gridTemplateColumns.split(' ').length,
            cardWidths: [...element.querySelectorAll(':scope > [data-listing-id]')]
                .slice(0, 2)
                .map(card => card.getBoundingClientRect().width),
            firstRowY: [...element.querySelectorAll(':scope > [data-listing-id]')]
                .slice(0, 2)
                .map(card => card.getBoundingClientRect().y),
        })"""
    )
    assert gallery_metrics["columns"] == 2
    assert gallery_metrics["firstRowY"][0] == pytest.approx(
        gallery_metrics["firstRowY"][1], abs=1
    )
    assert all(width < first_card_box["width"] * 0.55 for width in gallery_metrics["cardWidths"])
    assert_no_horizontal_page_overflow(page)
    gallery_chip_metrics = page.locator(".category-chip-nav").evaluate(
        """element => {
            const box = element.getBoundingClientRect();
            return {
                x: box.x,
                width: box.width,
                clientWidth: element.clientWidth,
                scrollWidth: element.scrollWidth,
                pillCount: element.querySelectorAll('.category-pill').length,
            };
        }"""
    )
    assert gallery_chip_metrics["x"] >= 0
    assert (
        gallery_chip_metrics["x"] + gallery_chip_metrics["width"]
        <= viewport["width"] + 1
    )
    assert gallery_chip_metrics["pillCount"] == 6
    assert gallery_chip_metrics["scrollWidth"] >= gallery_chip_metrics["clientWidth"]
    page.locator(".category-chip-nav").scroll_into_view_if_needed()
    page.screenshot(
        path=ARTIFACT_DIR / f"browse-chips-gallery-{viewport['width']}.png",
        full_page=False,
    )

    badge_contrast = {}
    for listing_id, status_name in (
        ("bambu-lab-a1-mini", "Reserved"),
        ("arduino-sensor-starter-kit", "Sold"),
    ):
        selector = f'[data-listing-id="{listing_id}"] [data-status="{status_name}"]'
        expect(page.locator(selector)).to_be_visible()
        font_size = page.locator(selector).evaluate(
            "element => parseFloat(getComputedStyle(element).fontSize)"
        )
        assert font_size >= 10
        badge_contrast[status_name.lower()] = measured_contrast(page, selector)
    assert all(ratio >= 4.5 for ratio in badge_contrast.values())

    reserved_card = page.locator('[data-listing-id="bambu-lab-a1-mini"]')
    reserved_card.scroll_into_view_if_needed()
    page.screenshot(
        path=ARTIFACT_DIR / f"browse-gallery-{viewport['width']}.png",
        full_page=False,
    )

    page.get_by_role("button", name="List view").click()
    expect(page.locator("#listing-grid")).to_have_attribute("data-listing-view", "list")
    restored_width = page.locator("#listing-grid > [data-listing-id]").first.bounding_box()
    assert restored_width is not None
    assert restored_width["width"] == pytest.approx(first_card_box["width"], abs=1)

    reserved_card.scroll_into_view_if_needed()
    expect(reserved_card.locator('[data-status="Reserved"]')).to_be_visible()
    page.screenshot(
        path=ARTIFACT_DIR / f"browse-status-{viewport['width']}.png",
        full_page=False,
    )

    page.locator(".site-footer").scroll_into_view_if_needed()
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    toggle_box = assert_inside_viewport(page, "#catalogue-chat-toggle")
    footer_targets = page.locator(".site-footer p, .site-footer a")
    for index in range(footer_targets.count()):
        target_box = footer_targets.nth(index).bounding_box()
        if target_box is not None:
            assert not boxes_overlap(toggle_box, target_box)

    page.goto(f"{BASE_URL}/notes", wait_until="networkidle")
    assert_no_horizontal_page_overflow(page)
    expect(page.locator("main section[id]")).to_have_count(5)
    page.screenshot(
        path=ARTIFACT_DIR / f"notes-{viewport['width']}.png",
        full_page=False,
    )

    page.goto(
        f"{BASE_URL}/listings/original-prusa-mini-plus",
        wait_until="networkidle",
    )
    assert_no_horizontal_page_overflow(page)
    expect(page.get_by_role("heading", name="Original Prusa MINI+")).to_be_visible()
    expect(page.locator("[data-gallery-thumbnail]")).to_have_count(3)
    page.locator("[data-gallery-next]").click()
    expect(page.locator("[data-gallery-counter]")).to_have_text("2 / 3")
    page.screenshot(
        path=ARTIFACT_DIR / f"detail-{viewport['width']}.png",
        full_page=False,
    )

    checkout_trigger = page.get_by_role("button", name="Simulated Buy / Reserve")
    checkout_trigger.scroll_into_view_if_needed()
    checkout_trigger.click()
    checkout_dialog = page.locator("#simulated-checkout-dialog")
    expect(checkout_dialog).to_be_visible()
    checkout_box = checkout_dialog.bounding_box()
    assert checkout_box is not None
    assert checkout_box["x"] >= 0
    assert checkout_box["y"] >= 0
    assert checkout_box["x"] + checkout_box["width"] <= viewport["width"] + 1
    assert checkout_box["y"] + checkout_box["height"] <= viewport["height"] + 1
    expect(checkout_dialog).to_contain_text("Original Prusa MINI+")
    expect(checkout_dialog).to_contain_text("Good")
    expect(checkout_dialog).to_contain_text("S$420")
    expect(checkout_dialog).to_contain_text("Local pickup")
    expect(checkout_dialog).to_contain_text("Jurong East")
    expect(checkout_dialog).to_contain_text(
        "This is a simulated demo checkout — no real payment is processed."
    )
    checkout_confirm = checkout_dialog.get_by_role("button", name="Confirm Order")
    checkout_confirm.scroll_into_view_if_needed()
    checkout_confirm_box = checkout_confirm.bounding_box()
    assert checkout_confirm_box is not None
    assert checkout_confirm_box["width"] >= 44
    assert checkout_confirm_box["height"] >= 44
    page.screenshot(
        path=ARTIFACT_DIR / f"checkout-review-{viewport['width']}.png",
        full_page=False,
    )

    checkout_confirm.click()
    checkout_success = page.locator("[data-checkout-success]")
    expect(checkout_success).to_be_visible()
    expect(checkout_success).to_contain_text("Reservation Confirmed!")
    expect(checkout_success).to_contain_text(re.compile(r"Reference #\d{6}"))
    expect(page.locator('[data-status="Available"]')).to_be_visible()
    page.screenshot(
        path=ARTIFACT_DIR / f"checkout-success-{viewport['width']}.png",
        full_page=False,
    )
    checkout_dialog.get_by_role("button", name="Done").click()
    expect(checkout_dialog).to_be_hidden()
    expect(checkout_trigger).to_be_focused()

    page.locator("#catalogue-chat-toggle").click()
    panel_box = assert_inside_viewport(page, "#catalogue-chat-panel")
    expect(page.get_by_label("Ask a question about the catalogue")).to_be_visible()
    expect(page.get_by_role("button", name="Ask the catalogue")).to_be_visible()
    expect(page.get_by_role("button", name="Close catalogue chat").first).to_be_visible()
    page.screenshot(
        path=ARTIFACT_DIR / f"chat-{viewport['width']}.png",
        full_page=False,
    )

    result = {
        "viewport": viewport,
        "horizontal_overflow": False,
        "first_card_width": first_card_box["width"],
        "chat_panel": panel_box,
        "footer_targets_checked": footer_targets.count(),
        "labels": {
            "search": True,
            "chat": True,
            "buttons_named": True,
            "images_have_alt": True,
        },
        "keyboard": keyboard,
        "glass_navigation": glass_navigation,
        "browse_gallery": {
            "columns": gallery_metrics["columns"],
            "card_widths": gallery_metrics["cardWidths"],
            "badge_contrast": {
                name: round(ratio, 2) for name, ratio in badge_contrast.items()
            },
            "list_width_restored": restored_width["width"],
        },
        "category_chips": {
            "count": chip_metrics["pillCount"],
            "container_width": chip_metrics["width"],
            "scroll_width": chip_metrics["scrollWidth"],
            "fits_list_and_gallery": True,
        },
        "featured_carousel": {
            "slides": 4,
            "interval_ms": featured_interval,
            "unattended_auto_advance": True,
            "intro_geometry": intro_geometry,
            "previous_control": featured_previous_box,
            "next_control": featured_next_box,
            "manual_advance": True,
            "active_slide_geometry": featured_geometry,
            "horizontal_overflow": False,
        },
        "simulated_checkout": {
            "review_dialog": checkout_box,
            "confirm_target": checkout_confirm_box,
            "summary_fields": True,
            "success_reference": True,
            "status_unchanged": True,
        },
        "contrast_ratios": {
            name: round(ratio, 2) for name, ratio in contrast.items()
        },
    }
    context.close()
    return result


def main() -> None:
    if not EDGE_PATH.is_file():
        raise SystemExit(f"Microsoft Edge was not found at {EDGE_PATH}")
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=str(EDGE_PATH),
            headless=True,
        )
        results = [verify_viewport(browser, viewport) for viewport in VIEWPORTS]
        browser.close()

    print(
        json.dumps(
            {
                "base_url": BASE_URL,
                "results": results,
                "artifacts": str(ARTIFACT_DIR),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
