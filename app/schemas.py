import ipaddress
import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, TypeAdapter, field_validator

URL_ADAPTER = TypeAdapter(HttpUrl)
LINK_START = re.compile(r"\b[a-z][a-z0-9+.-]*://|(?:^|(?<=[\s(\[<]))www\.", re.IGNORECASE)
URL_TOKEN = re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s<>\"']+", re.IGNORECASE)


@dataclass(frozen=True)
class CTALink:
    url: str
    start: int
    end: int


def extract_cta(message: str) -> CTALink:
    """Require one explicit HTTP(S) URL; do not fetch user-supplied URLs."""
    if len(LINK_START.findall(message)) != 1:
        raise ValueError("Message must contain exactly one explicit http:// or https:// CTA link")
    match = URL_TOKEN.search(message)
    if not match:
        raise ValueError("CTA link must begin with http:// or https://")
    candidate = match.group().rstrip(".,!?;")
    for opening, closing in (("(", ")"), ("[", "]"), ("{", "}")):
        while candidate.endswith(closing) and candidate.count(closing) > candidate.count(opening):
            candidate = candidate[:-1]
    # Reject malformed escapes and control characters instead of silently normalizing them.
    if re.search(r"%(?![0-9a-fA-F]{2})|%0[0-9a-fA-F]|%7f|[\\\x00-\x20\x7f]", candidate, re.I):
        raise ValueError("CTA link contains invalid characters or percent escapes")
    try:
        parsed = URL_ADAPTER.validate_python(candidate)
    except ValueError as exc:
        raise ValueError("CTA link must be a valid HTTP(S) URL") from exc
    if parsed.username or parsed.password:
        raise ValueError("CTA link must not contain embedded credentials")
    host = parsed.host or ""
    try:
        address = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        labels = host.rstrip(".").split(".")
        if (
            len(labels) < 2
            or host.endswith((".localhost", ".local"))
            or not all(
                re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label, re.I)
                for label in labels
            )
        ):
            raise ValueError("CTA link must use a public domain or public IP address") from None
    else:
        if not address.is_global:
            raise ValueError("CTA link must use a public domain or public IP address")
    return CTALink(candidate, match.start(), match.start() + len(candidate))


class PostingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    message: str = Field(
        min_length=1, max_length=200, description="One HTTP(S) CTA, at most 200 characters"
    )

    @field_validator("message")
    @classmethod
    def validate_message(cls, message: str) -> str:
        if not message.strip():
            raise ValueError("Message must not be blank")
        extract_cta(message)
        return message


class PlatformResult(BaseModel):
    platform: str
    status: Literal["success", "failed"]
    posted_url: str | None = None
    public_access: bool = False
    date: str | None = Field(default=None, description="Posting date in UTC, YYYY-MM-DD")
    time: str | None = Field(default=None, description="Posting time in UTC, HH:MM:SS")
    error: str | None = None


class PostingResponse(BaseModel):
    success: bool = Field(description="True when at least one platform confirms publication")
    results: list[PlatformResult]
