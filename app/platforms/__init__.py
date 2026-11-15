from app.config import Settings
from app.platforms.base import Platform
from app.platforms.bluesky import Bluesky
from app.platforms.devto import DevTo
from app.platforms.discord import Discord
from app.platforms.mastodon import Mastodon
from app.platforms.telegram import Telegram


def build_platforms(settings: Settings) -> list[Platform]:
    """Fixed server-side selection; callers cannot choose publishing destinations."""
    return [
        Mastodon(settings),
        Bluesky(settings),
        DevTo(settings),
        Telegram(settings),
        Discord(settings),
    ]
