import httpx

from app.platforms.base import (
    Platform,
    PublishedPost,
    https_origin,
    published_url,
    require_settings,
    timestamp,
)


class Mastodon(Platform):
    name = "Mastodon"

    async def publish(self, message: str, client: httpx.AsyncClient) -> PublishedPost:
        require_settings(MASTODON_ACCESS_TOKEN=self.settings.mastodon_access_token)
        origin = https_origin(self.settings.mastodon_base_url)
        result = await self.request(
            client,
            "POST",
            f"{origin}/api/v1/statuses",
            headers={
                "Authorization": f"Bearer {self.settings.mastodon_access_token.get_secret_value()}"
            },
            data={"status": message, "visibility": "public"},
        )
        return PublishedPost(
            published_url(result["url"]),
            result["visibility"] in ("public", "unlisted"),
            timestamp(result["created_at"]),
        )
