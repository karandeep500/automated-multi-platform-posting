import httpx

from app.platforms.base import (
    Platform,
    PlatformError,
    PublishedPost,
    published_url,
    require_settings,
    timestamp,
)
from app.schemas import extract_cta


class DevTo(Platform):
    name = "DEV Community"

    async def publish(self, message: str, client: httpx.AsyncClient) -> PublishedPost:
        require_settings(DEVTO_API_KEY=self.settings.devto_api_key)
        cta = extract_cta(message)
        title = " ".join((message[: cta.start] + message[cta.end :]).split()).strip(" .!()[]")
        result = await self.request(
            client,
            "POST",
            "https://dev.to/api/articles",
            headers={
                "api-key": self.settings.devto_api_key.get_secret_value(),
                "Accept": "application/vnd.forem.api-v1+json",
            },
            json={
                "article": {
                    "title": title[:100] or "Community update",
                    "body_markdown": message,
                    "published": True,
                }
            },
        )
        if not result.get("published_at"):
            raise PlatformError("Article was not confirmed published; check DEV before retrying")
        return PublishedPost(published_url(result["url"]), True, timestamp(result["published_at"]))
