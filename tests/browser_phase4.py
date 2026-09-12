"""Real-browser Phase 4 smoke test.

Run against a local server with:
    python tests/browser_phase4.py
Set MAKER_SWAP_TEST_URL to target another deployment.
"""

import json
import os
import re
import tempfile
from pathlib import Path

from playwright.sync_api import Locator, Page, expect, sync_playwright


BASE_URL = os.environ.get("MAKER_SWAP_TEST_URL", "http://127.0.0.1:8765").rstrip("/")
EDGE_PATH = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
ARTIFACT_DIR = Path(tempfile.gettempdir()) / "maker-swap-phase4"


def assert_inside_viewport(page: Page, locator: Locator) -> dict[str, float]:
    box = locator.bounding_box()
    assert box is not None
    viewport = page.viewport_size
    assert viewport is not None
    assert box["x"] >= 0
    assert box["y"] >= 0
    assert box["x"] + box["width"] <= viewport["width"] + 1
    assert box["y"] + box["height"] <= viewport["height"] + 1
    return box


def boxes_overlap(left: dict[str, float], right: dict[str, float]) -> bool:
    return not (
        left["x"] + left["width"] <= right["x"]
        or right["x"] + right["width"] <= left["x"]
        or left["y"] + left["height"] <= right["y"]
        or right["y"] + right["height"] <= left["y"]
    )


def ask(page: Page, question: str, expected_answer_count: int) -> str:
    page.locator("#catalogue-chat-question").fill(question)
    page.locator("#catalogue-chat-submit").click()
    answers = page.locator('.catalogue-chat-message[data-role="assistant"]')
    expect(answers).to_have_count(expected_answer_count, timeout=60_000)
    return answers.nth(expected_answer_count - 1).locator(
        ".catalogue-chat-message-copy"
    ).inner_text()


def test_real_conversation_and_persistence(page: Page) -> dict[str, str]:
    page.goto(f"{BASE_URL}/", wait_until="networkidle")
    toggle = page.locator("#catalogue-chat-toggle")
    panel = page.locator("#catalogue-chat-panel")
    expect(toggle).to_be_visible()
    expect(panel).to_be_hidden()
    expect(toggle).to_have_attribute("aria-expanded", "false")

    toggle.click()
    expect(panel).to_be_visible()
    expect(toggle).to_have_attribute("aria-expanded", "true")
    assert_inside_viewport(page, panel)

    broad = ask(page, "what products are in here", 1)
    assert "don't know" not in broad.lower()
    assert len(broad.strip()) >= 40
    broad_message = page.locator('.catalogue-chat-message[data-role="assistant"]').nth(0)
    expect(broad_message.locator(".catalogue-chat-source")).to_have_count(0)

    factual = ask(
        page,
        "What is the price and pickup area for the Hakko FX-888D Soldering Station?",
        2,
    )
    assert "S$115" in factual
    assert "Toa Payoh" in factual
    factual_message = page.locator('.catalogue-chat-message[data-role="assistant"]').nth(1)
    expect(factual_message.locator(".catalogue-chat-source")).to_have_count(1)
    expect(factual_message.locator(".catalogue-chat-source")).to_have_attribute(
        "href", "/listings/hakko-fx888d-station"
    )

    page.locator("#catalogue-chat-close").click()
    expect(panel).to_be_hidden()
    expect(toggle).to_have_attribute("aria-expanded", "false")

    page.locator('[data-listing-id="hakko-fx888d-station"] a').click()
    expect(page).to_have_url(re.compile(r"/listings/hakko-fx888d-station$"))

    panel = page.locator("#catalogue-chat-panel")
    toggle = page.locator("#catalogue-chat-toggle")
    expect(panel).to_be_hidden()
    expect(toggle).to_have_attribute("aria-expanded", "false")
    toggle.click()
    expect(page.locator(".catalogue-chat-message")).to_have_count(4)
    expect(page.locator('.catalogue-chat-message[data-role="user"]').nth(1)).to_contain_text(
        "Hakko FX-888D"
    )
    expect(
        page.locator('.catalogue-chat-message[data-role="assistant"]').nth(1)
    ).to_contain_text("S$115")

    comparison = ask(
        page,
        "Compare the Yamaha Pacifica 112V Guitar and Roland FP-10 Digital Piano, including price and condition.",
        3,
    )
    assert "Yamaha" in comparison
    assert "Roland" in comparison
    assert "S$280" in comparison
    assert "S$420" in comparison
    comparison_message = page.locator('.catalogue-chat-message[data-role="assistant"]').nth(2)
    comparison_links = comparison_message.locator(".catalogue-chat-source")
    expect(comparison_links).to_have_count(2)
    assert set(comparison_links.evaluate_all("links => links.map(link => link.getAttribute('href'))")) == {
        "/listings/yamaha-pacifica-112v",
        "/listings/roland-fp-10-keyboard",
    }

    unknown = ask(
        page,
        "What warranty does the Cricut Maker 3 Cutting Machine include?",
        4,
    )
    assert "don't know based on the Maker Swap catalogue" in unknown
    unknown_message = page.locator('.catalogue-chat-message[data-role="assistant"]').nth(3)
    expect(unknown_message.locator(".catalogue-chat-source")).to_have_count(0)

    page.screenshot(path=ARTIFACT_DIR / "desktop-conversation.png", full_page=False)
    return {
        "broad": broad,
        "factual": factual,
        "comparison": comparison,
        "unknown": unknown,
    }


def test_mobile_layout_and_footer(page: Page) -> dict[str, object]:
    page.set_viewport_size({"width": 375, "height": 667})
    page.goto(f"{BASE_URL}/notes", wait_until="networkidle")

    toggle = page.locator("#catalogue-chat-toggle")
    panel = page.locator("#catalogue-chat-panel")
    expect(toggle).to_be_visible()
    expect(panel).to_be_hidden()
    toggle_box = assert_inside_viewport(page, toggle)

    toggle.click()
    expect(panel).to_be_visible()
    panel_box = assert_inside_viewport(page, panel)
    assert not boxes_overlap(panel_box, toggle_box)
    expect(page.locator("#catalogue-chat-question")).to_be_visible()
    expect(page.locator("#catalogue-chat-submit")).to_be_visible()
    assert page.locator("body").evaluate(
        "element => getComputedStyle(element).overflow"
    ) == "hidden"
    expect(page.locator(".catalogue-chat-message")).to_have_count(8)
    page.screenshot(path=ARTIFACT_DIR / "mobile-open.png", full_page=False)

    page.locator("#catalogue-chat-close").click()
    expect(panel).to_be_hidden()
    page.locator(".site-footer").scroll_into_view_if_needed()
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(150)
    toggle_box = assert_inside_viewport(page, toggle)

    footer_targets = page.locator(".site-footer p, .site-footer a")
    for index in range(footer_targets.count()):
        target_box = footer_targets.nth(index).bounding_box()
        if target_box is not None:
            assert not boxes_overlap(toggle_box, target_box)

    page.screenshot(path=ARTIFACT_DIR / "mobile-footer.png", full_page=False)
    return {
        "viewport": page.viewport_size,
        "panel": panel_box,
        "toggle": toggle_box,
        "footer_targets_checked": footer_targets.count(),
    }


def test_visible_provider_error(browser) -> str:
    context = browser.new_context(viewport={"width": 390, "height": 720})
    page = context.new_page()
    page.route(
        "**/api/qa",
        lambda route: route.fulfill(
            status=503,
            content_type="application/json",
            body=json.dumps(
                {
                    "detail": {
                        "code": "qa_gateway_unavailable",
                        "message": "The catalogue Q&A provider is unavailable. Please try again.",
                    }
                }
            ),
        ),
    )
    page.goto(f"{BASE_URL}/", wait_until="networkidle")
    page.locator("#catalogue-chat-toggle").click()
    page.locator("#catalogue-chat-question").fill("What electronics are available?")
    page.locator("#catalogue-chat-submit").click()
    status = page.locator("#catalogue-chat-status")
    expect(status).to_have_attribute("data-state", "error")
    expect(status).to_contain_text("provider is unavailable")
    expect(page.locator('.catalogue-chat-message[data-role="assistant"]')).to_have_count(0)
    message = status.inner_text()
    context.close()
    return message


def main() -> None:
    if not EDGE_PATH.is_file():
        raise SystemExit(f"Microsoft Edge was not found at {EDGE_PATH}")
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=str(EDGE_PATH),
            headless=True,
        )
        context = browser.new_context(viewport={"width": 1365, "height": 768})
        page = context.new_page()
        answers = test_real_conversation_and_persistence(page)
        mobile = test_mobile_layout_and_footer(page)
        provider_error = test_visible_provider_error(browser)
        context.close()
        browser.close()

    print(
        json.dumps(
            {
                "base_url": BASE_URL,
                "answers": answers,
                "mobile": mobile,
                "provider_error": provider_error,
                "screenshots": str(ARTIFACT_DIR),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
