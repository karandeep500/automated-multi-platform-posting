import asyncio
import logging

import httpx

from app.platforms.base import Platform, PlatformError
from app.schemas import PlatformResult, PostingResponse

logger = logging.getLogger(__name__)


class PostingService:
    def __init__(
        self, platforms: list[Platform], client: httpx.AsyncClient, timeout: float
    ) -> None:
        self.platforms = platforms
        self.client = client
        self.timeout = timeout

    async def _publish(self, platform: Platform, message: str) -> PlatformResult:
        try:
            async with asyncio.timeout(self.timeout):
                post = await platform.publish(message, self.client)
            return PlatformResult(
                platform=platform.name,
                status="success",
                posted_url=post.url,
                public_access=post.public_access,
                date=post.posted_at.strftime("%Y-%m-%d"),
                time=post.posted_at.strftime("%H:%M:%S"),
            )
        except PlatformError as exc:
            error = str(exc)
        except (TimeoutError, httpx.TimeoutException):
            error = "Request timed out; publication outcome may be unknown. Check before retrying"
        except httpx.RequestError:
            error = (
                "Network request failed; publication outcome may be unknown. Check before retrying"
            )
        except (KeyError, ValueError, TypeError, OverflowError):
            error = (
                "Platform returned an invalid response; publication outcome may be unknown. "
                "Check before retrying"
            )
        except Exception:
            # An adapter bug must not prevent other platforms from completing or expose credentials.
            error = "Unexpected platform failure; check publication before retrying"
        logger.info("Posting result platform=%s status=failed", platform.name)
        return PlatformResult(platform=platform.name, status="failed", error=error)

    async def post(self, message: str) -> PostingResponse:
        results = await asyncio.gather(*(self._publish(p, message) for p in self.platforms))
        return PostingResponse(success=any(r.status == "success" for r in results), results=results)
