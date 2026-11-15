import re

import httpx

from app.platforms.base import Platform, PlatformError, PublishedPost, require_settings, timestamp


class Discord(Platform):
    name = "Discord"

    async def publish(self, message: str, client: httpx.AsyncClient) -> PublishedPost:
        require_settings(
            DISCORD_WEBHOOK_URL=self.settings.discord_webhook_url,
            DISCORD_GUILD_ID=self.settings.discord_guild_id,
        )
        webhook = self.settings.discord_webhook_url.get_secret_value()
        if not re.fullmatch(r"https://discord\.com/api/(?:v10/)?webhooks/\d+/[\w.-]+", webhook):
            raise PlatformError(
                "Invalid DISCORD_WEBHOOK_URL: expected a Discord incoming webhook URL"
            )
        if not self.settings.discord_guild_id.isdecimal():
            raise PlatformError("Invalid DISCORD_GUILD_ID: expected a numeric server ID")
        result = await self.request(
            client,
            "POST",
            webhook,
            params={"wait": "true"},
            json={"content": message, "allowed_mentions": {"parse": []}},
        )
        channel_id, message_id = str(result["channel_id"]), str(result["id"])
        if not channel_id.isdecimal() or not message_id.isdecimal():
            raise PlatformError(
                "Platform returned invalid message identifiers; check before retrying"
            )
        url = f"https://discord.com/channels/{self.settings.discord_guild_id}/{channel_id}/{message_id}"
        return PublishedPost(url, False, timestamp(result["timestamp"]))
