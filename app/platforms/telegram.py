from datetime import UTC, datetime

import httpx

from app.platforms.base import (
    Platform,
    PlatformError,
    PublishedPost,
    require_object,
    require_settings,
)


class Telegram(Platform):
    name = "Telegram"

    async def publish(self, message: str, client: httpx.AsyncClient) -> PublishedPost:
        require_settings(
            TELEGRAM_BOT_TOKEN=self.settings.telegram_bot_token,
            TELEGRAM_CHAT_ID=self.settings.telegram_chat_id,
        )
        token = self.settings.telegram_bot_token.get_secret_value()
        result = await self.request(
            client,
            "POST",
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": self.settings.telegram_chat_id, "text": message},
        )
        if result.get("ok") is not True:
            raise PlatformError(
                "Telegram did not confirm publication; check bot permissions and chat ID"
            )
        post = require_object(result["result"])
        chat = require_object(post["chat"])
        message_id = int(post["message_id"])
        public = chat["type"] in ("channel", "supergroup") and bool(chat.get("username"))
        url = None
        if public:
            url = f"https://t.me/{chat['username']}/{message_id}"
        elif chat["type"] in ("channel", "supergroup") and str(chat["id"]).startswith("-100"):
            url = f"https://t.me/c/{str(chat['id'])[4:]}/{message_id}"
        return PublishedPost(url, public, datetime.fromtimestamp(post["date"], tz=UTC))
