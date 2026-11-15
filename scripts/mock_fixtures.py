import httpx

from app.config import Settings

MESSAGE = "Grow your online visibility. https://example.com"
DATE_TIME = "2026-11-15T10:30:00Z"


def mock_settings(**overrides) -> Settings:
    values = {
        "_env_file": None,
        "mastodon_base_url": "https://mastodon.example",
        "mastodon_access_token": "fake-mastodon-token",
        "bluesky_service_url": "https://bsky.social",
        "bluesky_identifier": "tester.bsky.social",
        "bluesky_app_password": "fake-app-password",
        "devto_api_key": "fake-dev-key",
        "telegram_bot_token": "123456:fake-bot-token",
        "telegram_chat_id": "@testchannel",
        "discord_webhook_url": "https://discord.com/api/webhooks/123456/fake-webhook-token",
        "discord_guild_id": "100000",
    }
    return Settings(**(values | overrides))


def success_response(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/api/v1/statuses":
        return httpx.Response(
            200,
            json={
                "url": "https://mastodon.example/@tester/123",
                "visibility": "public",
                "created_at": DATE_TIME,
            },
        )
    if path == "/xrpc/com.atproto.server.createSession":
        return httpx.Response(200, json={"did": "did:plc:tester", "accessJwt": "fake-session-jwt"})
    if path == "/xrpc/com.atproto.repo.createRecord":
        return httpx.Response(200, json={"uri": "at://did:plc:tester/app.bsky.feed.post/abc123"})
    if path == "/api/articles":
        return httpx.Response(
            201, json={"url": "https://dev.to/tester/update-123", "published_at": DATE_TIME}
        )
    if path.endswith("/sendMessage"):
        return httpx.Response(
            200,
            json={
                "ok": True,
                "result": {
                    "message_id": 42,
                    "date": 1794738600,
                    "chat": {"id": -100123456, "type": "channel", "username": "testchannel"},
                },
            },
        )
    if path.startswith("/api/webhooks/"):
        return httpx.Response(
            200, json={"id": "300000", "channel_id": "200000", "timestamp": DATE_TIME}
        )
    raise AssertionError(f"Unexpected mock request: {request.method} {request.url.host} {path}")
