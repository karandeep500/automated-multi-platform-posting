from datetime import UTC, datetime
from urllib.parse import quote

import httpx

from app.platforms.base import (
    Platform,
    PlatformError,
    PublishedPost,
    https_origin,
    require_settings,
)
from app.schemas import extract_cta


class Bluesky(Platform):
    name = "Bluesky"

    async def publish(self, message: str, client: httpx.AsyncClient) -> PublishedPost:
        require_settings(
            BLUESKY_IDENTIFIER=self.settings.bluesky_identifier,
            BLUESKY_APP_PASSWORD=self.settings.bluesky_app_password,
        )
        origin = https_origin(self.settings.bluesky_service_url)
        session = await self.request(
            client,
            "POST",
            f"{origin}/xrpc/com.atproto.server.createSession",
            json={
                "identifier": self.settings.bluesky_identifier,
                "password": self.settings.bluesky_app_password.get_secret_value(),
            },
        )
        did, token = session["did"], session["accessJwt"]
        if not isinstance(did, str) or not did.startswith("did:") or not isinstance(token, str):
            raise PlatformError("Platform returned an invalid session")
        cta = extract_cta(message)
        created_at = datetime.now(UTC)
        result = await self.request(
            client,
            "POST",
            f"{origin}/xrpc/com.atproto.repo.createRecord",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "repo": did,
                "collection": "app.bsky.feed.post",
                "record": {
                    "$type": "app.bsky.feed.post",
                    "text": message,
                    "createdAt": created_at.isoformat().replace("+00:00", "Z"),
                    "facets": [
                        {
                            "index": {
                                "byteStart": len(message[: cta.start].encode("utf-8")),
                                "byteEnd": len(message[: cta.end].encode("utf-8")),
                            },
                            "features": [{"$type": "app.bsky.richtext.facet#link", "uri": cta.url}],
                        }
                    ],
                },
            },
        )
        prefix = f"at://{did}/app.bsky.feed.post/"
        uri = result["uri"]
        if not isinstance(uri, str) or not uri.startswith(prefix):
            raise PlatformError("Platform returned an invalid record URI; check before retrying")
        record_key = uri[len(prefix) :]
        if not record_key or "/" in record_key:
            raise PlatformError("Platform returned an invalid record key; check before retrying")
        url = f"https://bsky.app/profile/{quote(did, safe=':')}/post/{quote(record_key, safe='')}"
        return PublishedPost(url, True, created_at)
