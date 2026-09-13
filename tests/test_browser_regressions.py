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


def open_page(browser: Browser, base_url: str, path: str = "/") -> Page:
    context = browser.new_context(viewport={"width": 1280, "height": 720})
    page = context.new_page()
    page.goto(f"{base_url}{path}", wait_until="networkidle")
    return page


def test_category_filter_preserves_catalogue_scroll_position(
    browser: Browser,
    browser_base_url: str,
) -> None:
    page = open_page(browser, browser_base_url)

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
    assert -1 <= catalogue_top < 100

    page.context.close()


def test_clear_search_restores_the_full_catalogue(
    browser: Browser,
    browser_base_url: str,
) -> None:
    page = open_page(browser, browser_base_url, "/?category=Electronics#listings")
    listing = load_listings()[4]
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

    with page.expect_navigation(wait_until="domcontentloaded"):
        page.locator("#catalogue-search-clear").click()

    expect(page).to_have_url(f"{browser_base_url}/#listings")
    expect(page.locator("#catalogue-heading")).to_have_text("Browse everything")
    expect(page.locator('[data-listing-id]')).to_have_count(16)
    expect(page.locator("#catalogue-search-query")).to_have_value("")
    expect(page.locator("#catalogue-search-clear")).to_have_class(re.compile(r"\bhidden\b"))

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
