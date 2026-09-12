from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.catalog import CatalogLoadError, get_categories, get_listing, load_listings
from app.qa import (
    CatalogueQA,
    QAGatewayError,
    QAKeyError,
    QAModelError,
    QARequest,
    QAResponse,
    QASource,
    QATimeoutError,
    get_qa_service,
)
from app.search import (
    SearchGatewayError,
    SearchKeyError,
    SearchModelError,
    SearchRequest,
    SearchResponse,
    SearchTimeoutError,
    SemanticCatalogSearch,
    get_search_service,
)


BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(
    title="Maker Swap",
    description="A second-hand marketplace demo for makers and hobbyists.",
    version="0.1.0",
)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

templates = Jinja2Templates(directory=BASE_DIR / "templates")


@app.get("/", response_class=HTMLResponse)
def home(
    request: Request,
    category: str | None = Query(default=None, max_length=50),
) -> HTMLResponse:
    listings = load_listings()
    selected_category = category.strip() if category else None
    visible_listings = (
        tuple(
            listing
            for listing in listings
            if listing.category == selected_category
        )
        if selected_category
        else listings
    )

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "listings": visible_listings,
            "listing_count": len(visible_listings),
            "categories": get_categories(),
            "selected_category": selected_category,
        },
    )


@app.get("/listings/{listing_id}", response_class=HTMLResponse)
def listing_detail(request: Request, listing_id: str) -> HTMLResponse:
    listing = get_listing(listing_id)
    if listing is None:
        return templates.TemplateResponse(
            request=request,
            name="404.html",
            context={"listing_id": listing_id},
            status_code=404,
        )

    return templates.TemplateResponse(
        request=request,
        name="listing_detail.html",
        context={"listing": listing},
    )


@app.get("/notes", response_class=HTMLResponse)
def notes(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="notes.html",
    )


@app.post("/api/search", response_model=SearchResponse)
def search_catalogue(
    payload: SearchRequest,
    search: Annotated[SemanticCatalogSearch, Depends(get_search_service)],
) -> SearchResponse:
    try:
        matches = search.search(payload.query)
    except SearchKeyError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "search_not_configured",
                "message": "AI search is not configured on the server.",
            },
        ) from exc
    except SearchTimeoutError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "search_timeout",
                "message": "The AI search provider timed out. Please try again.",
            },
        ) from exc
    except SearchModelError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "search_model_unavailable",
                "message": "The configured embedding model is unavailable through the AI provider.",
            },
        ) from exc
    except SearchGatewayError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "search_gateway_unavailable",
                "message": "The AI search provider is unavailable. Please try again.",
            },
        ) from exc

    return SearchResponse(
        query=payload.query,
        results=tuple(match.listing for match in matches),
    )


@app.post("/api/qa", response_model=QAResponse)
def ask_catalogue(
    payload: QARequest,
    qa: Annotated[CatalogueQA, Depends(get_qa_service)],
) -> QAResponse:
    try:
        result = qa.answer(payload.question, payload.history)
    except (SearchKeyError, QAKeyError) as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "qa_not_configured",
                "message": "Catalogue Q&A is not configured on this server.",
            },
        ) from exc
    except (SearchTimeoutError, QATimeoutError) as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "qa_timeout",
                "message": "The catalogue Q&A provider timed out. Please try again.",
            },
        ) from exc
    except (SearchModelError, QAModelError) as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "qa_model_unavailable",
                "message": "A required Q&A model is unavailable through the AI provider.",
            },
        ) from exc
    except (SearchGatewayError, QAGatewayError) as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "qa_gateway_unavailable",
                "message": "The catalogue Q&A provider is unavailable. Please try again.",
            },
        ) from exc

    return QAResponse(
        question=payload.question,
        answer=result.answer,
        sources=tuple(
            QASource(id=listing.id, title=listing.title)
            for listing in result.sources
        ),
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.exception_handler(CatalogLoadError)
def catalog_error(request: Request, exc: CatalogLoadError) -> Response:
    return templates.TemplateResponse(
        request=request,
        name="catalog_error.html",
        context={"message": str(exc)},
        status_code=500,
    )
