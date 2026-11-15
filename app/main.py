import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request

from app.config import Settings
from app.platforms import build_platforms
from app.schemas import PostingRequest, PostingResponse
from app.services.posting_service import PostingService


def create_app(
    settings: Settings | None = None, transport: httpx.AsyncBaseTransport | None = None
) -> FastAPI:
    """Inject settings/transport for offline tests without changing the real publish path."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        config = settings if settings is not None else Settings()
        # HTTPX logs URLs at INFO; Telegram tokens and Discord webhooks live in those URLs.
        for name in ("httpx", "httpcore"):
            logging.getLogger(name).setLevel(logging.WARNING)
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(config.http_timeout_seconds, connect=5, pool=5),
            follow_redirects=False,
            trust_env=False,
            transport=transport,
            headers={"User-Agent": "automated-posting/1.0"},
        ) as client:
            app.state.posting_service = PostingService(
                build_platforms(config), client, config.platform_timeout_seconds
            )
            yield

    application = FastAPI(
        title="Automated Multi-Platform Posting System",
        version="1.0.0",
        description=(
            "Publish a message of at most 200 characters with exactly one HTTP(S) CTA link to "
            "five internally selected platforms. Results are independent; date/time are UTC. "
            "An HTTP 200 response contains each outcome; HTTP 422 indicates invalid input."
        ),
        lifespan=lifespan,
    )

    @application.post("/posting", response_model=PostingResponse, tags=["Posting"])
    async def posting(payload: PostingRequest, request: Request) -> PostingResponse:
        return await request.app.state.posting_service.post(payload.message)

    return application


app = create_app()
