"""Offline evidence: real application and adapters, fake upstream HTTP responses."""

import asyncio
import json

import httpx

from app.main import create_app
from scripts.mock_fixtures import MESSAGE, mock_settings, success_response


async def run_demo() -> dict:
    scenarios = {}
    for partial_failure in (False, True):

        def handler(request, fail_discord=partial_failure):
            if fail_discord and request.url.host == "discord.com":
                return httpx.Response(429, json={"message": "Mock rate limit"})
            return success_response(request)

        app = create_app(mock_settings(), httpx.MockTransport(handler))
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app), base_url="http://testserver"
            ) as client:
                response = await client.post("/posting", json={"message": MESSAGE})
                assert response.status_code == 200
                scenarios["partial_failure" if partial_failure else "all_success"] = response.json()
    return {
        "mode": "MOCKED: no real posts or external network requests",
        "request": {"message": MESSAGE},
        "scenarios": scenarios,
    }


if __name__ == "__main__":
    print(json.dumps(asyncio.run(run_demo()), indent=2))
