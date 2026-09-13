"""Continuous live-site reviewer flow in a fresh browser context.

Run with:
    python tests/reviewer_flow_phase6.py
Set MAKER_SWAP_TEST_URL to target a different deployment.
"""

import json
import os
import re
import tempfile
from pathlib import Path

from playwright.sync_api import Page, expect, sync_playwright


BASE_URL = os.environ.get(
    "MAKER_SWAP_TEST_URL",
    "https://maker-swap.onrender.com",
).rstrip("/")
EDGE_PATH = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
ARTIFACT_DIR = Path(tempfile.gettempdir()) / "maker-swap-phase6-reviewer"


def wait_for_answer(page: Page, expected_count: int) -> str:
    answers = page.locator('.catalogue-chat-message[data-role="assistant"]')
    expect(answers).to_have_count(expected_count, timeout=90_000)
    return answers.nth(expected_count - 1).locator(
        ".catalogue-chat-message-copy"
    ).inner_text()


def run_reviewer_flow(page: Page) -> dict[str, object]:
    console_errors: list[str] = []
    page_errors: list[str] = []
    page.on(
        "console",
        lambda message: (
            console_errors.append(message.text) if message.type == "error" else None
        ),
    )
    page.on("pageerror", lambda error: page_errors.append(str(error)))

    home_response = page.goto(f"{BASE_URL}/", wait_until="networkidle")
    assert home_response is not None and home_response.ok
    expect(page.get_by_role("heading", name="Good tools deserve a second project.")).to_be_visible()
    expect(page.locator("#listing-grid > [data-listing-id]")).to_have_count(16)

    page.get_by_role("link", name="Electronics", exact=True).click()
    page.wait_for_url(re.compile(r"\?category=Electronics#listings$"))
    expect(page.locator("#listing-grid > [data-listing-id]")).to_have_count(4)
    category_scroll_y = page.evaluate("window.scrollY")
    assert category_scroll_y > 0

    page.get_by_role("link", name="All", exact=True).click()
    page.wait_for_url(re.compile(r"/#listings$"))
    expect(page.locator("#listing-grid > [data-listing-id]")).to_have_count(16)

    search_query = "I need a temperature-controlled tool for electronics repair"
    page.locator("#catalogue-search-query").fill(search_query)
    page.locator("#catalogue-search-submit").click()
    expect(page.locator("#search-status")).to_have_attribute(
        "data-state",
        "success",
        timeout=90_000,
    )
    search_cards = page.locator("#listing-grid > [data-listing-id]")
    search_result_count = search_cards.count()
    assert 1 <= search_result_count <= 4
    expect(
        page.locator('[data-listing-id="hakko-fx888d-station"]')
    ).to_be_visible()
    search_titles = search_cards.locator("h3").all_inner_texts()
    page.screenshot(path=ARTIFACT_DIR / "01-search-results.png", full_page=False)

    page.locator('[data-listing-id="hakko-fx888d-station"] a').click()
    page.wait_for_url(re.compile(r"/listings/hakko-fx888d-station$"))
    expect(
        page.get_by_role("heading", name="Hakko FX-888D Soldering Station")
    ).to_be_visible()

    page.locator("#catalogue-chat-toggle").click()
    expect(page.locator("#catalogue-chat-panel")).to_be_visible()
    question_input = page.locator("#catalogue-chat-question")
    question_input.fill(
        "What is the price and pickup area for the Hakko FX-888D Soldering Station?"
    )
    page.locator("#catalogue-chat-submit").click()
    factual_answer = wait_for_answer(page, 1)
    assert "S$115" in factual_answer
    assert "Toa Payoh" in factual_answer
    factual_source = page.locator(
        '.catalogue-chat-message[data-role="assistant"]'
    ).nth(0).locator(".catalogue-chat-source")
    expect(factual_source).to_have_count(1)
    expect(factual_source).to_have_attribute(
        "href",
        "/listings/hakko-fx888d-station",
    )

    question_input.fill("What warranty does it include?")
    page.locator("#catalogue-chat-submit").click()
    unknown_answer = wait_for_answer(page, 2)
    assert "i don't know based on the maker swap catalogue" in unknown_answer.lower()
    expect(
        page.locator('.catalogue-chat-message[data-role="assistant"]')
        .nth(1)
        .locator(".catalogue-chat-source")
    ).to_have_count(0)
    page.screenshot(path=ARTIFACT_DIR / "02-detail-qa.png", full_page=False)

    page.locator("#catalogue-chat-close").click()
    page.get_by_role("link", name="/notes", exact=True).click()
    page.wait_for_url(re.compile(r"/notes$"))
    expect(page.get_by_text("Build notes / Phase 5", exact=True)).to_be_visible()
    expect(page.locator("main section[id]")).to_have_count(5)
    expect(page.get_by_text("gpt-5.6-sol max", exact=True)).to_be_visible()
    expect(page.get_by_text("Budget language is approximate.", exact=True)).to_be_visible()

    page.locator("#catalogue-chat-toggle").click()
    expect(page.locator(".catalogue-chat-message")).to_have_count(4)
    page.screenshot(path=ARTIFACT_DIR / "03-notes-persisted-chat.png", full_page=False)

    assert console_errors == []
    assert page_errors == []
    return {
        "base_url": BASE_URL,
        "private_context": True,
        "browse_listing_count": 16,
        "category_listing_count": 4,
        "category_scroll_y": category_scroll_y,
        "search_query": search_query,
        "search_results": search_titles,
        "factual_answer": factual_answer,
        "unknown_answer": unknown_answer,
        "notes_sections": 5,
        "persisted_chat_messages": 4,
        "console_errors": console_errors,
        "page_errors": page_errors,
        "artifacts": str(ARTIFACT_DIR),
    }


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
        result = run_reviewer_flow(page)
        context.close()
        browser.close()

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
