from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.catalog import CatalogLoadError, get_categories, get_listing, load_listings


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
