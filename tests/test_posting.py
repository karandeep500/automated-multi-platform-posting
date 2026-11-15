import asyncio
import json
from datetime import UTC, datetime
from urllib.parse import parse_qs

import httpx
import pytest

from app.main import create_app
from app.platforms.base import Platform, PublishedPost
from app.services.posting_service import PostingService
from scripts.mock_fixtures import MESSAGE, mock_settings, success_response


def call_api(settings, handler, payload=None):
    async def run():
        app = create_app(settings, httpx.MockTransport(handler))
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app), base_url="http://testserver"
            ) as client:
                return await client.post(
                    "/posting", json=payload if payload is not None else {"message": MESSAGE}
                )

    return asyncio.run(run())


def test_five_real_adapter_contracts(settings):
    seen = []

    def handler(request):
        seen.append(request)
        assert request.method == "POST"
        return success_response(request)

    response = call_api(settings, handler)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert [r["platform"] for r in data["results"]] == [
        "Mastodon",
        "Bluesky",
        "DEV Community",
        "Telegram",
        "Discord",
    ]
    assert all(r["status"] == "success" and r["error"] is None for r in data["results"])
    assert len(seen) == 6  # Bluesky authenticates before writing its record.
    requests = {request.url.path: request for request in seen}
    mastodon = requests["/api/v1/statuses"]
    assert mastodon.headers["Authorization"] == "Bearer fake-mastodon-token"
    assert parse_qs(mastodon.content.decode()) == {"status": [MESSAGE], "visibility": ["public"]}
    session = requests["/xrpc/com.atproto.server.createSession"]
    assert json.loads(session.content) == {
        "identifier": "tester.bsky.social",
        "password": "fake-app-password",
    }
    bluesky = requests["/xrpc/com.atproto.repo.createRecord"]
    record = json.loads(bluesky.content)
    assert bluesky.headers["Authorization"] == "Bearer fake-session-jwt"
    assert record["repo"] == "did:plc:tester"
    assert record["collection"] == record["record"]["$type"] == "app.bsky.feed.post"
    assert record["record"]["text"] == MESSAGE
    assert data["results"][1]["posted_url"] == "https://bsky.app/profile/did:plc:tester/post/abc123"
    dev = requests["/api/articles"]
    assert dev.headers["api-key"] == "fake-dev-key"
    assert dev.headers["Accept"] == "application/vnd.forem.api-v1+json"
    assert json.loads(dev.content)["article"] == {
        "title": "Grow your online visibility",
        "body_markdown": MESSAGE,
        "published": True,
    }
    telegram = requests["/bot123456:fake-bot-token/sendMessage"]
    assert json.loads(telegram.content) == {"chat_id": "@testchannel", "text": MESSAGE}
    discord = requests["/api/webhooks/123456/fake-webhook-token"]
    assert discord.url.params["wait"] == "true"
    assert json.loads(discord.content) == {"content": MESSAGE, "allowed_mentions": {"parse": []}}
    assert [r["public_access"] for r in data["results"]] == [True, True, True, True, False]
    assert data["results"][4]["posted_url"] == "https://discord.com/channels/100000/200000/300000"
    for index in (0, 2, 3, 4):
        assert data["results"][index]["date"] == "2026-11-15"
        assert data["results"][index]["time"] == "10:30:00"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"message": None},
        {"message": 123},
        {"message": []},
        {"message": ""},
        {"message": " "},
        {"message": "No link"},
        {"message": "https://example.com https://second.example"},
        {"message": "https://example.com www.second.example"},
        {"message": "https://example.com https://example.com"},
        {"message": "https://example.comhttps://other.example"},
        {"message": "www.example.com"},
        {"message": "ftp://example.com"},
        {"message": "https://"},
        {"message": "https://localhost"},
        {"message": "http://127.0.0.1"},
        {"message": "http://[::1]"},
        {"message": "https://user:password@example.com"},
        {"message": "https://example.com:99999"},
        {"message": "https://example.com/%zz"},
        {"message": "https://example.com/%0a"},
        {"message": "https://example.com\\bad"},
        {"message": "x" * 182 + "https://example.com/"},
        {"message": MESSAGE, "platforms": ["Discord"]},
    ],
)
def test_validation_rejects_before_any_publish(settings, payload):
    def no_request(request):
        pytest.fail("Invalid input must not call any upstream")

    response = call_api(settings, no_request, payload)
    assert response.status_code == 422
    assert response.json()["detail"]


@pytest.mark.parametrize(
    "message",
    [
        MESSAGE,
        "https://example.com",
        "Learn (https://example.com).",
        "[Learn more](https://example.com/page)",
        "Read https://example.com/path_(one)",
        "Read https://example.com?q=one%20two&x=1#section",
        "Read HTTPS://EXAMPLE.COM",
        "Learn https://例え.jp/",
        "Read http://8.8.8.8/",
        "✨ " + MESSAGE,
        "x" * 179 + " https://example.com/",
        "Visit https://www.example.com",
        "Visit https://example.com/www.example.com",
    ],
)
def test_valid_inputs(settings, message):
    response = call_api(settings, success_response, {"message": message})
    assert response.status_code == 200
    assert all(r["status"] == "success" for r in response.json()["results"])


def test_unicode_facet_offsets_use_utf8_bytes(settings):
    message = "🚀 पढ़ें https://example.com."

    def handler(request):
        if request.url.path.endswith("createRecord"):
            record = json.loads(request.content)["record"]
            facet = record["facets"][0]
            raw = message.encode("utf-8")
            index = facet["index"]
            assert raw[index["byteStart"] : index["byteEnd"]].decode() == "https://example.com"
            assert facet["features"] == [
                {"$type": "app.bsky.richtext.facet#link", "uri": "https://example.com"}
            ]
        return success_response(request)

    assert call_api(settings, handler, {"message": message}).json()["success"] is True


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422, 429, 500, 503])
def test_one_platform_failure_does_not_stop_others(settings, status):
    def handler(request):
        if request.url.host == "dev.to":
            return httpx.Response(status, text="private upstream body fake-dev-key")
        return success_response(request)

    response = call_api(settings, handler)
    results = response.json()["results"]
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert [r["status"] for r in results] == ["success", "success", "failed", "success", "success"]
    failed = results[2]
    assert failed["date"] is failed["time"] is failed["posted_url"] is None
    assert failed["public_access"] is False
    assert str(status) in failed["error"]
    assert "fake-dev-key" not in response.text


def test_all_platforms_fail(settings):
    response = call_api(settings, lambda request: httpx.Response(401, json={"error": "secret"}))
    assert response.status_code == 200
    assert response.json()["success"] is False
    assert all(r["status"] == "failed" for r in response.json()["results"])


def test_missing_credentials_are_explicit_and_offline():
    settings = mock_settings(
        mastodon_access_token="",
        bluesky_identifier="",
        bluesky_app_password="",
        devto_api_key="",
        telegram_bot_token="",
        telegram_chat_id="",
        discord_webhook_url="",
        discord_guild_id="",
    )

    def no_request(request):
        pytest.fail("Missing credentials must not call upstream")

    response = call_api(settings, no_request)
    assert response.json()["success"] is False
    assert all("Missing configuration:" in r["error"] for r in response.json()["results"])


@pytest.mark.parametrize("kind", ["timeout", "network", "json", "missing", "array", "bug"])
def test_failures_are_isolated_without_leaking_secrets(settings, kind, caplog):
    def handler(request):
        if request.url.host == "api.telegram.org":
            if kind == "timeout":
                raise httpx.ReadTimeout("secret-token in URL", request=request)
            if kind == "network":
                raise httpx.ConnectError("secret-token in URL", request=request)
            if kind == "json":
                return httpx.Response(200, text="secret-token not JSON")
            if kind == "missing":
                return httpx.Response(200, json={"ok": True})
            if kind == "array":
                return httpx.Response(200, json=[])
            raise RuntimeError("secret-token")
        return success_response(request)

    with caplog.at_level("INFO"):
        response = call_api(settings, handler)
    assert response.json()["results"][3]["status"] == "failed"
    assert response.json()["results"][4]["status"] == "success"
    assert "secret-token" not in response.text + caplog.text
    assert "fake-bot-token" not in caplog.text
    assert "fake-webhook-token" not in caplog.text


@pytest.mark.parametrize(
    "chat, expected_url, public",
    [
        (
            {"id": -100123456, "type": "supergroup", "username": "testgroup"},
            "https://t.me/testgroup/42",
            True,
        ),
        ({"id": -100123456, "type": "channel"}, "https://t.me/c/123456/42", False),
        ({"id": 123456, "type": "private", "username": "person"}, None, False),
    ],
)
def test_telegram_visibility_uses_returned_chat(settings, chat, expected_url, public):
    def handler(request):
        if request.url.host == "api.telegram.org":
            return httpx.Response(
                200,
                json={"ok": True, "result": {"message_id": 42, "date": 1794738600, "chat": chat}},
            )
        return success_response(request)

    result = call_api(settings, handler).json()["results"][3]
    assert result["posted_url"] == expected_url
    assert result["public_access"] is public


def test_dev_draft_is_not_reported_as_publication(settings):
    def handler(request):
        if request.url.host == "dev.to":
            return httpx.Response(
                201, json={"url": "https://dev.to/tester/draft", "published_at": None}
            )
        return success_response(request)

    assert call_api(settings, handler).json()["results"][2]["status"] == "failed"


@pytest.mark.parametrize(
    "field, value, index",
    [
        ("mastodon_base_url", "http://mastodon.example", 0),
        ("bluesky_service_url", "https://bsky.social/other", 1),
        ("discord_webhook_url", "https://attacker.example/api/webhooks/1/secret", 4),
        ("discord_guild_id", "not-a-number", 4),
    ],
)
def test_bad_platform_config_does_not_disable_others(field, value, index):
    response = call_api(mock_settings(**{field: value}), success_response)
    results = response.json()["results"]
    assert results[index]["status"] == "failed"
    assert sum(r["status"] == "success" for r in results) == 4


async def test_platforms_start_concurrently_and_slow_platform_is_bounded(settings):
    started = set()
    all_started = asyncio.Event()

    class ControlledPlatform(Platform):
        def __init__(self, name):
            super().__init__(settings)
            self.name = name

        async def publish(self, message, client):
            started.add(self.name)
            if len(started) == 3:
                all_started.set()
            await all_started.wait()  # Sequential dispatch would time out.
            if self.name == "slow":
                await asyncio.Event().wait()
            return PublishedPost("https://example.com/posted", True, datetime.now(UTC))

    async with httpx.AsyncClient(transport=httpx.MockTransport(success_response)) as client:
        service = PostingService(
            [ControlledPlatform(name) for name in ("first", "slow", "last")], client, timeout=0.1
        )
        response = await service.post(MESSAGE)
    assert [r.status for r in response.results] == ["success", "failed", "success"]
    assert "timed out" in response.results[1].error


async def test_openapi_and_docs(settings):
    app = create_app(settings, httpx.MockTransport(success_response))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://testserver"
        ) as client:
            assert (await client.get("/docs")).status_code == 200
            schema = (await client.get("/openapi.json")).json()
    assert set(schema["paths"]) == {"/posting"}
    field = schema["components"]["schemas"]["PostingRequest"]["properties"]["message"]
    assert field["maxLength"] == 200
