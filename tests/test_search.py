from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from openai import APIConnectionError, APITimeoutError, PermissionDeniedError

from app.catalog import load_listings
from app.main import app
from app.search import (
    GatewayEmbedder,
    SearchGatewayError,
    SearchKeyError,
    SearchModelError,
    SearchTimeoutError,
    SemanticCatalogSearch,
    get_search_service,
    listing_discovery_text,
    listing_search_text,
)


client = TestClient(app)


class MeaningAwareFakeEmbedder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def embed(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        self.calls.append(tuple(texts))
        return tuple(self._vector(text) for text in texts)

    @staticmethod
    def _vector(text: str) -> tuple[float, ...]:
        if any(term in text for term in ("electronics", "circuit", "repair")):
            return (1.0, 0.0, 0.0)
        if any(term in text for term in ("instrument", "music", "piano")):
            return (0.0, 1.0, 0.0)
        return (0.0, 0.0, 1.0)


class ThresholdFakeEmbedder:
    def embed(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        if len(texts) > 1:
            return tuple(
                (1.0, 0.0) if "hakko fx-888d" in text else (-1.0, 0.0)
                for text in texts
            )

        query_vectors = {
            "kayak": (0.20, 0.98),
            "washing machine": (0.31, 0.95),
            "kids going back to school": (0.216, 0.976),
            "soldering iron": (0.80, 0.60),
        }
        return (query_vectors[texts[0]],)


class FocusedViewFakeEmbedder:
    def embed(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        if len(texts) > 1:
            midpoint = len(texts) // 2
            detailed = tuple((0.30, 0.954) for _ in texts[:midpoint])
            focused = tuple(
                (1.0, 0.0) if "renovation" in text else (-1.0, 0.0)
                for text in texts[midpoint:]
            )
            return detailed + focused
        return ((1.0, 0.0),)


class LowScoreFakeEmbedder:
    def embed(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        if len(texts) == 1:
            return ((0.0, 1.0),)
        return tuple((1.0, 0.0) for _ in texts)


class StubSearch:
    def __init__(self, result=(), error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.queries: list[str] = []

    def search(self, query: str):
        self.queries.append(query)
        if self.error is not None:
            raise self.error
        return self.result


def override_search(stub: StubSearch) -> None:
    app.dependency_overrides[get_search_service] = lambda: stub


@pytest.fixture(autouse=True)
def clear_dependency_overrides():
    yield
    app.dependency_overrides.clear()


def test_listing_embedding_text_contains_every_searchable_field() -> None:
    listing = load_listings()[0]
    text = listing_search_text(listing)

    assert listing.title.casefold() in text
    assert listing.category.casefold() in text
    assert listing.condition.casefold() in text
    assert listing.status.casefold() in text
    assert listing.description.casefold() in text
    assert listing.pickup_area.casefold() in text
    assert all(tag.casefold() in text for tag in listing.tags)
    assert all(spec.label.casefold() in text for spec in listing.specs)
    assert all(spec.value.casefold() in text for spec in listing.specs)


def test_discovery_embedding_focuses_on_title_category_and_tags() -> None:
    listing = load_listings()[-1]
    text = listing_discovery_text(listing)

    assert listing.title.casefold() in text
    assert listing.category.casefold() in text
    assert listing.status.casefold() in text
    assert all(tag.casefold() in text for tag in listing.tags)


def test_semantic_search_ranks_exact_catalogue_records() -> None:
    listings = load_listings()
    embedder = MeaningAwareFakeEmbedder()
    search = SemanticCatalogSearch(embedder=embedder)

    matches = search.search("repair a circuit board", listings=listings, limit=4)

    assert [match.listing.id for match in matches] == [
        "hakko-fx888d-station",
        "arduino-sensor-starter-kit",
        "rigol-ds1054z-oscilloscope",
        "raspberry-pi-4-workbench",
    ]
    assert matches[0].listing is listings[4]


def test_catalogue_embeddings_are_cached_between_queries() -> None:
    embedder = MeaningAwareFakeEmbedder()
    search = SemanticCatalogSearch(embedder=embedder)

    search.search("electronics repair")
    search.search("music practice")

    assert len(embedder.calls) == 3
    assert len(embedder.calls[0]) == 32
    assert len(embedder.calls[1]) == 1
    assert len(embedder.calls[2]) == 1


@pytest.mark.parametrize(
    "query",
    ["kayak", "washing machine", "kids going back to school"],
)
def test_similarity_threshold_returns_no_forced_matches(query: str) -> None:
    search = SemanticCatalogSearch(embedder=ThresholdFakeEmbedder())

    assert search.search(query) == ()


def test_similarity_threshold_keeps_a_strong_match_and_removes_weak_tail() -> None:
    search = SemanticCatalogSearch(embedder=ThresholdFakeEmbedder())

    matches = search.search("soldering iron")

    assert [match.listing.id for match in matches] == ["hakko-fx888d-station"]
    assert matches[0].score == pytest.approx(0.8)


def test_focused_metadata_view_can_rescue_relevant_use_case() -> None:
    search = SemanticCatalogSearch(embedder=FocusedViewFakeEmbedder())

    matches = search.search("used for renovation")

    assert [match.listing.id for match in matches] == [
        "makita-cordless-drill-set",
        "bosch-router-table",
    ]


@pytest.mark.parametrize(
    ("query", "expected_category", "expected_count"),
    [
        ("art", "Art & Craft", 3),
        ("Art & Craft", "Art & Craft", 3),
        ("3d", "3D Printing", 4),
        ("electronics", "Electronics", 4),
        ("instruments", "Instruments", 3),
        ("workshop", "Workshop Tools", 2),
    ],
)
def test_literal_category_phrase_is_guaranteed_below_similarity_floor(
    query: str,
    expected_category: str,
    expected_count: int,
) -> None:
    search = SemanticCatalogSearch(embedder=LowScoreFakeEmbedder())

    matches = search.search(query)

    assert [match.listing.category for match in matches] == [
        expected_category
    ] * expected_count
    assert all(match.score == 0.0 for match in matches)


def test_literal_title_phrase_is_guaranteed_below_similarity_floor() -> None:
    search = SemanticCatalogSearch(embedder=LowScoreFakeEmbedder())

    matches = search.search("Cricut Maker 3")

    assert [match.listing.id for match in matches] == ["cricut-maker-3"]


def test_partial_cross_category_word_is_not_a_guaranteed_match() -> None:
    search = SemanticCatalogSearch(embedder=LowScoreFakeEmbedder())

    assert search.search("art tools") == ()


def test_gateway_embedder_requires_server_side_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLASSGW_KEY", raising=False)

    with pytest.raises(SearchKeyError):
        GatewayEmbedder().embed(("maker tools",))


@pytest.mark.parametrize(
    ("provider_error", "expected_error"),
    [
        (
            APITimeoutError(request=httpx.Request("POST", "https://gateway.test")),
            SearchTimeoutError,
        ),
        (
            APIConnectionError(request=httpx.Request("POST", "https://gateway.test")),
            SearchGatewayError,
        ),
    ],
)
def test_gateway_embedder_maps_provider_failures(provider_error, expected_error) -> None:
    embeddings = SimpleNamespace(create=lambda **kwargs: (_ for _ in ()).throw(provider_error))
    gateway = GatewayEmbedder(client=SimpleNamespace(embeddings=embeddings))

    with pytest.raises(expected_error):
        gateway.embed(("maker tools",))


def test_gateway_embedder_maps_model_access_failure() -> None:
    request = httpx.Request("POST", "https://gateway.test")
    response = httpx.Response(403, request=request)
    provider_error = PermissionDeniedError(
        "Embedding model unavailable",
        response=response,
        body={"error": "model unavailable"},
    )
    embeddings = SimpleNamespace(create=lambda **kwargs: (_ for _ in ()).throw(provider_error))
    gateway = GatewayEmbedder(client=SimpleNamespace(embeddings=embeddings))

    with pytest.raises(SearchModelError):
        gateway.embed(("maker tools",))


def test_gateway_embedder_rejects_malformed_vectors() -> None:
    response = SimpleNamespace(
        data=[SimpleNamespace(index=0, embedding=[])],
    )
    embeddings = SimpleNamespace(create=lambda **kwargs: response)
    gateway = GatewayEmbedder(client=SimpleNamespace(embeddings=embeddings))

    with pytest.raises(SearchModelError):
        gateway.embed(("maker tools",))


def test_gateway_embedder_uses_provider_qualified_model_id() -> None:
    request: dict = {}

    def create_embedding(**kwargs):
        request.update(kwargs)
        return SimpleNamespace(
            data=[SimpleNamespace(index=0, embedding=[1.0, 0.0])]
        )

    gateway = GatewayEmbedder(
        client=SimpleNamespace(embeddings=SimpleNamespace(create=create_embedding))
    )

    gateway.embed(("maker tools",))

    assert request == {
        "model": "openai/text-embedding-3-small",
        "input": ["maker tools"],
    }


def test_search_api_returns_unchanged_listing_objects() -> None:
    listings = load_listings()
    matches = (
        SimpleNamespace(listing=listings[4], score=0.98),
        SimpleNamespace(listing=listings[6], score=0.91),
    )
    stub = StubSearch(result=matches)
    override_search(stub)

    response = client.post("/api/search", json={"query": "  Electronics   repair  "})

    assert response.status_code == 200
    assert response.json() == {
        "query": "Electronics repair",
        "results": [
            listings[4].model_dump(mode="json"),
            listings[6].model_dump(mode="json"),
        ],
    }
    assert stub.queries == ["Electronics repair"]


def test_search_api_excludes_unavailable_matches_from_beginner_budget_query() -> None:
    listings_by_id = {listing.id: listing for listing in load_listings()}
    matches = (
        SimpleNamespace(
            listing=listings_by_id["arduino-sensor-starter-kit"],
            score=0.98,
        ),
        SimpleNamespace(
            listing=listings_by_id["raspberry-pi-4-workbench"],
            score=0.94,
        ),
        SimpleNamespace(
            listing=listings_by_id["original-prusa-mini-plus"],
            score=0.88,
        ),
        SimpleNamespace(
            listing=listings_by_id["bambu-lab-a1-mini"],
            score=0.84,
        ),
    )
    stub = StubSearch(result=matches)
    override_search(stub)

    response = client.post(
        "/api/search",
        json={"query": "beginner setup under $150"},
    )

    assert response.status_code == 200
    results = response.json()["results"]
    assert [result["id"] for result in results] == [
        "raspberry-pi-4-workbench",
        "original-prusa-mini-plus",
    ]
    assert all(result["status"] == "Available" for result in results)
    assert "arduino-sensor-starter-kit" not in {
        result["id"] for result in results
    }
    assert "bambu-lab-a1-mini" not in {result["id"] for result in results}
    assert stub.queries == ["beginner setup under $150"]


@pytest.mark.parametrize(
    "body",
    [
        {"query": " "},
        {"query": "a"},
        {"query": "x" * 201},
        {"query": "valid query", "unexpected": True},
        {},
    ],
)
def test_search_api_validates_input(body: dict) -> None:
    override_search(StubSearch())

    response = client.post("/api/search", json=body)

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (SearchKeyError("missing"), "search_not_configured"),
        (SearchTimeoutError("slow"), "search_timeout"),
        (SearchModelError("model"), "search_model_unavailable"),
        (SearchGatewayError("offline"), "search_gateway_unavailable"),
    ],
)
def test_search_api_surfaces_honest_failure_codes(error: Exception, code: str) -> None:
    override_search(StubSearch(error=error))

    response = client.post("/api/search", json={"query": "maker tools"})

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == code


def test_browse_page_includes_async_search_states() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert 'id="catalogue-search-form"' in response.text
    assert 'id="nav-search-form"' in response.text
    assert 'id="nav-search-query"' in response.text
    assert 'id="search-status"' in response.text
    assert 'id="catalogue-empty-state"' in response.text
    assert 'id="browse-all-items"' in response.text
    assert "data-suggested-query" not in response.text
    assert (
        'src="http://testserver/static/search.js?v=condition-badges-1"'
        in response.text
    )
    assert "data-card-status" in response.text
    assert "data-listing-status" in response.text
    assert "CLASSGW_KEY" not in response.text
