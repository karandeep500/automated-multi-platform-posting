from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import SecretStr

from app.config import Settings
from app.schemas import URL_ADAPTER


class PlatformError(Exception):
    """Only safe, application-controlled messages may be returned to the caller."""


@dataclass(frozen=True)
class PublishedPost:
    url: str | None
    public_access: bool
    posted_at: datetime


def require_settings(**values: str | SecretStr) -> None:
    missing = [
        name
        for name, value in values.items()
        if not (value.get_secret_value() if isinstance(value, SecretStr) else value).strip()
    ]
    if missing:
        raise PlatformError("Missing configuration: " + ", ".join(missing))


def https_origin(value: str) -> str:
    try:
        url = URL_ADAPTER.validate_python(value)
        if (
            url.scheme != "https"
            or url.username
            or url.password
            or url.path not in (None, "/")
            or url.query
            or url.fragment
        ):
            raise ValueError
    except ValueError:
        raise PlatformError("Invalid service URL: expected an HTTPS origin") from None
    return str(url).rstrip("/")


def published_url(value: Any) -> str:
    try:
        url = URL_ADAPTER.validate_python(value)
        if url.username or url.password:
            raise ValueError
    except ValueError:
        raise PlatformError(
            "Platform returned an invalid published URL; check before retrying"
        ) from None
    return str(url)


def timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("Missing timestamp")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Timestamp must include timezone")
    return result.astimezone(UTC)


def require_object(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PlatformError("Platform returned an invalid response; check before retrying")
    return value


class Platform(ABC):
    name: str

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @abstractmethod
    async def publish(self, message: str, client: httpx.AsyncClient) -> PublishedPost:
        """Send a real publish request and return the confirmed publication."""

    async def request(
        self, client: httpx.AsyncClient, method: str, url: str, **kwargs: Any
    ) -> dict:
        response = await client.request(method, url, **kwargs)
        status = response.status_code
        if status in (401, 403):
            raise PlatformError(f"Authentication or permission denied (HTTP {status})")
        if status == 429:
            raise PlatformError("Platform rate limit exceeded (HTTP 429); retry later")
        if status >= 500:
            raise PlatformError(f"Platform unavailable (HTTP {status}); check before retrying")
        if not 200 <= status < 300:
            raise PlatformError(f"Platform rejected the request (HTTP {status})")
        # Never echo provider bodies, request URLs, or exception strings: they can contain secrets.
        return require_object(response.json())
