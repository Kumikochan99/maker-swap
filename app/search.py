import os
import re
from dataclasses import dataclass
from math import isfinite, sqrt
from threading import Lock
from typing import Protocol, Sequence

from openai import (
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    OpenAI,
    PermissionDeniedError,
)
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.catalog import Listing, load_listings


GATEWAY_BASE_URL = "https://174.138.16.223/openrouter/v1"
# OpenRouter requires the provider-qualified request id. The response reports
# the underlying model as "text-embedding-3-small".
EMBEDDING_MODEL = "openai/text-embedding-3-small"
EMBEDDING_TIMEOUT_SECONDS = 20.0
SEARCH_RESULT_LIMIT = 4
MINIMUM_SIMILARITY = 0.35
NON_ALPHANUMERIC = re.compile(r"[^a-z0-9]+")


class SearchError(RuntimeError):
    """Base class for expected semantic-search failures."""


class SearchKeyError(SearchError):
    """Raised when the server-side gateway key is missing or rejected."""


class SearchModelError(SearchError):
    """Raised when the embedding model is unavailable or returns invalid data."""


class SearchTimeoutError(SearchError):
    """Raised when the embedding provider does not respond in time."""


class SearchGatewayError(SearchError):
    """Raised when the embedding gateway cannot complete a request."""


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(max_length=200)

    @field_validator("query")
    @classmethod
    def normalize_and_validate_query(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if len(normalized) < 2:
            raise ValueError("Enter at least 2 non-space characters.")
        return normalized


class SearchResponse(BaseModel):
    query: str
    results: tuple[Listing, ...]


class Embedder(Protocol):
    def embed(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]: ...


class GatewayEmbedder:
    """Small server-side adapter around the CognitioLabs embeddings gateway."""

    def __init__(self, client: OpenAI | None = None) -> None:
        self._client = client

    def _get_client(self) -> OpenAI:
        if self._client is not None:
            return self._client

        try:
            api_key = os.environ["CLASSGW_KEY"]
        except KeyError as exc:
            raise SearchKeyError("CLASSGW_KEY is not configured on the server.") from exc

        if not api_key.strip():
            raise SearchKeyError("CLASSGW_KEY is not configured on the server.")

        self._client = OpenAI(
            base_url=GATEWAY_BASE_URL,
            api_key=api_key,
            timeout=EMBEDDING_TIMEOUT_SECONDS,
            max_retries=0,
        )
        return self._client

    def embed(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        if not texts:
            return ()

        try:
            response = self._get_client().embeddings.create(
                model=EMBEDDING_MODEL,
                input=list(texts),
            )
        except APITimeoutError as exc:
            raise SearchTimeoutError("The embedding request timed out.") from exc
        except AuthenticationError as exc:
            raise SearchKeyError("The gateway rejected the server credential.") from exc
        except (BadRequestError, NotFoundError, PermissionDeniedError) as exc:
            raise SearchModelError("The configured embedding model is unavailable.") from exc
        except APIConnectionError as exc:
            raise SearchGatewayError("The embedding gateway could not be reached.") from exc
        except (APIStatusError, APIError) as exc:
            raise SearchGatewayError("The embedding gateway rejected the request.") from exc

        try:
            ordered_data = sorted(response.data, key=lambda item: item.index)
            if [item.index for item in ordered_data] != list(range(len(texts))):
                raise ValueError("Embedding indexes do not match the request.")

            vectors = tuple(
                tuple(float(component) for component in item.embedding)
                for item in ordered_data
            )
        except (AttributeError, TypeError, ValueError) as exc:
            raise SearchModelError("The embedding model returned invalid data.") from exc

        if len(vectors) != len(texts):
            raise SearchModelError("The embedding model returned an unexpected vector count.")
        if not vectors or not vectors[0]:
            raise SearchModelError("The embedding model returned an empty vector.")

        dimensions = len(vectors[0])
        if any(
            len(vector) != dimensions
            or not all(isfinite(component) for component in vector)
            for vector in vectors
        ):
            raise SearchModelError("The embedding model returned malformed vectors.")

        return vectors


@dataclass(frozen=True)
class SearchMatch:
    listing: Listing
    score: float


class SemanticCatalogSearch:
    def __init__(self, embedder: Embedder | None = None) -> None:
        self._embedder = embedder or GatewayEmbedder()
        self._cache_lock = Lock()
        self._catalog_cache: tuple[
            tuple[tuple[str, str, str], ...],
            tuple[tuple[float, ...], ...],
        ] | None = None

    def search(
        self,
        query: str,
        listings: Sequence[Listing] | None = None,
        limit: int = SEARCH_RESULT_LIMIT,
    ) -> tuple[SearchMatch, ...]:
        normalized_query = normalize_text(query)
        if len(normalized_query) < 2:
            raise ValueError("A search query needs at least 2 non-space characters.")
        if limit < 1:
            raise ValueError("Search result limit must be positive.")

        catalogue = tuple(listings if listings is not None else load_listings())
        if not catalogue:
            return ()

        catalogue_vectors = self._get_catalog_vectors(catalogue)
        query_vectors = self._embedder.embed((normalized_query,))
        if len(query_vectors) != 1:
            raise SearchModelError("The embedding model returned an unexpected query vector count.")

        query_vector = query_vectors[0]
        if len(query_vector) != len(catalogue_vectors[0]):
            raise SearchModelError("Catalogue and query embeddings have different dimensions.")

        focused_vector_offset = len(catalogue)
        scored = tuple(
            SearchMatch(
                listing=listing,
                score=max(
                    cosine_similarity(query_vector, catalogue_vectors[index]),
                    cosine_similarity(
                        query_vector,
                        catalogue_vectors[focused_vector_offset + index],
                    ),
                ),
            )
            for index, listing in enumerate(catalogue)
        )
        ranked = sorted(scored, key=lambda match: match.score, reverse=True)
        literal_ids = literal_match_ids(normalized_query, catalogue)
        guaranteed = [match for match in ranked if match.listing.id in literal_ids]
        semantic = [
            match
            for match in ranked
            if match.score >= MINIMUM_SIMILARITY
            and match.listing.id not in literal_ids
        ]
        return tuple((guaranteed + semantic)[:limit])

    def _get_catalog_vectors(
        self,
        listings: tuple[Listing, ...],
    ) -> tuple[tuple[float, ...], ...]:
        signature = tuple(
            (
                listing.id,
                listing_search_text(listing),
                listing_discovery_text(listing),
            )
            for listing in listings
        )
        cache = self._catalog_cache
        if cache is not None and cache[0] == signature:
            return cache[1]

        with self._cache_lock:
            cache = self._catalog_cache
            if cache is not None and cache[0] == signature:
                return cache[1]

            detailed_texts = tuple(detail for _, detail, _ in signature)
            focused_texts = tuple(focused for _, _, focused in signature)
            vectors = self._embedder.embed(detailed_texts + focused_texts)
            if len(vectors) != len(listings) * 2:
                raise SearchModelError(
                    "The embedding model returned an unexpected catalogue vector count."
                )
            if not vectors or not vectors[0]:
                raise SearchModelError("The embedding model returned an empty catalogue vector.")

            dimensions = len(vectors[0])
            if any(len(vector) != dimensions for vector in vectors):
                raise SearchModelError(
                    "The embedding model returned inconsistent catalogue dimensions."
                )

            self._catalog_cache = (signature, vectors)
            return vectors


def normalize_text(value: str) -> str:
    return " ".join(value.split()).casefold()


def normalize_literal_text(value: str) -> str:
    words = NON_ALPHANUMERIC.sub(" ", normalize_text(value).replace("&", " and "))
    return " ".join(words.split())


def contains_phrase(container: str, phrase: str) -> bool:
    return bool(phrase) and f" {phrase} " in f" {container} "


def literal_match_ids(
    query: str,
    listings: Sequence[Listing],
) -> set[str]:
    normalized_query = normalize_literal_text(query)
    matches: set[str] = set()

    for listing in listings:
        category = normalize_literal_text(listing.category)
        title = normalize_literal_text(listing.title)
        category_match = contains_phrase(normalized_query, category)
        title_match = contains_phrase(title, normalized_query) or contains_phrase(
            normalized_query,
            title,
        )
        if category_match or title_match:
            matches.add(listing.id)

    return matches


def listing_search_text(listing: Listing) -> str:
    fields = (
        f"title: {listing.title}",
        f"category: {listing.category}",
        f"condition: {listing.condition}",
        f"description: {listing.description}",
        f"pickup area: {listing.pickup_area}",
        f"tags: {', '.join(listing.tags)}",
    )
    return normalize_text("\n".join(fields))


def listing_discovery_text(listing: Listing) -> str:
    return normalize_text(
        f"{listing.title}. category: {listing.category}. "
        f"useful for: {', '.join(listing.tags)}."
    )


def cosine_similarity(
    left: Sequence[float],
    right: Sequence[float],
) -> float:
    if len(left) != len(right) or not left:
        raise SearchModelError("Embedding vectors have incompatible dimensions.")

    left_norm = sqrt(sum(component * component for component in left))
    right_norm = sqrt(sum(component * component for component in right))
    if left_norm == 0 or right_norm == 0:
        raise SearchModelError("The embedding model returned a zero-length vector.")

    return sum(a * b for a, b in zip(left, right, strict=True)) / (
        left_norm * right_norm
    )


search_service = SemanticCatalogSearch()


def get_search_service() -> SemanticCatalogSearch:
    return search_service
