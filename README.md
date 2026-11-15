# Automated Multi-Platform Posting System

A Python 3.11+ / FastAPI application that accepts one short message and publishes it to **Mastodon, Bluesky, DEV Community, Telegram, and Discord**. Platform selection is fixed inside the application. All five attempts run concurrently, and each returns its own result.

Implemented against the [Python practical test requirements](https://github.com/chivoxai/practical-test/blob/main/python-post-message.md).

**Verification status:** automated tests and the included demo use mocked upstream HTTP responses. No live account credentials were supplied, and no real posts were made. The normal application uses real platform endpoints; it never substitutes simulated successes for missing credentials.

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
# Fill in credentials for the accounts you want to use.
uvicorn app.main:app --host 0.0.0.0 --port 4000
```

Swagger UI: **http://localhost:4000/docs**. OpenAPI: http://localhost:4000/openapi.json.

The application can start with no credentials. It returns five explicit configuration failures until credentials are supplied. Settings are loaded at startup; restart after editing `.env`.

## API

```bash
curl -X POST http://localhost:4000/posting \
  -H 'Content-Type: application/json' \
  -d '{"message":"Grow your online visibility. https://example.com"}'
```

The only request field is `message`, a string of **1–200 Unicode characters**, including spaces and the URL. Extra fields, including client-selected platforms, are rejected. The text is preserved for publication.

The message must contain exactly one explicit `http://` or `https://` CTA URL. Validation checks URL syntax, hostname, port, and percent escapes. Embedded credentials, local/private IP literals, local hostnames, unsupported schemes, missing links, and duplicate links are rejected with **HTTP 422**, before any publishing requests. Standalone `www.` links require a scheme. Sentence punctuation and Markdown link wrappers are supported; percent-encode punctuation when it is part of a URL. Validation is syntactic: the CTA is never fetched, and domain ownership, DNS resolution, and destination availability are not checked.

Example invalid input:

```json
{"message":"Read https://example.com and https://another.example"}
```

Example **mocked** partial response (abbreviated to two results; the actual response always contains five):

```json
{
  "success": true,
  "results": [
    {
      "platform": "Mastodon",
      "status": "success",
      "posted_url": "https://mastodon.example/@tester/123",
      "public_access": true,
      "date": "2026-11-15",
      "time": "10:30:00",
      "error": null
    },
    {
      "platform": "Discord",
      "status": "failed",
      "posted_url": null,
      "public_access": false,
      "date": null,
      "time": null,
      "error": "Platform rate limit exceeded (HTTP 429); retry later"
    }
  ]
}
```

Full generated examples: [docs/mock-demo.json](docs/mock-demo.json).

Valid requests return **HTTP 200** with per-platform outcomes, including when all five fail. Top-level `success` means **at least one platform confirmed publication**. Check every result to determine complete or partial success. Failed results have null URL/date/time and a safe error message. A timeout or malformed response can occur after a provider has created a post, so failure can mean an unknown outcome.

Dates and times are **UTC**. Mastodon, DEV, Telegram, and Discord use the provider's publication timestamp; Bluesky uses the `createdAt` timestamp submitted in the successfully created record. URLs come from provider responses or are constructed using confirmed record/message IDs. Private Telegram direct messages can succeed with `posted_url: null` because there is no public permalink.

`public_access` reflects platform visibility metadata and access rules at posting time, without fetching the resulting page anonymously. Discord messages require server/channel access and always return false. A public Telegram channel or supergroup with a returned username returns true. Mastodon and DEV use the returned visibility/publication metadata; Bluesky records are public. Moderation, instance policies, deletion, or later access changes may affect reachability.

## Configure the five integrations

| Platform | Environment variables | Setup and implementation |
| --- | --- | --- |
| Mastodon | `MASTODON_BASE_URL`, `MASTODON_ACCESS_TOKEN` | On your instance, create an application under Preferences → Development. Give the user token `write:statuses`. The service sends a public status to `/api/v1/statuses`. |
| Bluesky | `BLUESKY_SERVICE_URL`, `BLUESKY_IDENTIFIER`, `BLUESKY_APP_PASSWORD` | Create an app password in account settings; use your handle or DID as identifier. Default service is `https://bsky.social`; set your own PDS origin if needed. The service creates a session, then an `app.bsky.feed.post` record with a clickable link facet using UTF-8 byte offsets. |
| DEV Community | `DEVTO_API_KEY` | Generate an API key at `https://dev.to/settings/extensions`. The service creates a published article via `/api/articles`; the message becomes the Markdown body and the non-URL text supplies a title of at most 100 characters. Use an account and content suitable for DEV publishing. |
| Telegram | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | Create a bot with @BotFather and add it as an administrator with posting permission in your channel. Use `@channelusername` or a numeric chat ID. `sendMessage` returns the actual chat, message ID, and timestamp. |
| Discord | `DISCORD_WEBHOOK_URL`, `DISCORD_GUILD_ID` | In a normal server text channel, create an incoming webhook under Integrations. Copy the webhook URL and the numeric server ID (Developer Mode → Copy Server ID). `wait=true` requests confirmation; mentions are disabled. Forum/media channels requiring threads are outside this implementation. |

Official API research, endpoints, authentication, and visibility decisions: [docs/platform-research.md](docs/platform-research.md).

## Test and reproduce the demo

```bash
python -m pip install -e '.[dev]'
pytest -q
ruff check .
ruff format --check .
python -m scripts.mock_demo
```

For the exact complete dependency set used locally, install `requirements-dev.lock` instead of the development extra. `requirements.txt` pins the five runtime dependencies; `pyproject.toml` declares the supported version ranges.

Tests inject an `httpx.MockTransport` below the real adapters. They exercise validation, actual outgoing methods/headers/payloads, five-platform success, partial and total failure, authentication errors, rate limiting, network errors, malformed responses, secret redaction, visibility, Unicode link offsets, concurrency, and total platform timeouts. No third-party accounts or network requests are required. The demo runs the actual ASGI app with success and partial-failure scenarios using explicitly fake credentials.

Captured local results are in [docs/verification.txt](docs/verification.txt). GitHub Actions runs tests, lint, and formatting checks on Python 3.11 and 3.14.

## Design and limits

```text
app/
  main.py                    FastAPI app, lifecycle, shared async HTTP client
  config.py                  Environment settings with redacted secret fields
  schemas.py                 Request validation, CTA extraction, response models
  platforms/                 Five independent REST API adapters
  services/posting_service.py Concurrent dispatch and isolated failure handling
scripts/                     Offline demo and fake upstream fixtures
tests/                       API and adapter contract tests
docs/                        Research, generated examples, verification evidence
```

Each platform has a total timeout (`PLATFORM_TIMEOUT_SECONDS`, default 25 seconds); each HTTP operation also has a timeout (`HTTP_TIMEOUT_SECONDS`, default 10 seconds). A slow or failed platform cannot cancel successful peers. Results remain in a stable platform order.

POST requests are **not automatically retried**, since providers can accept a post before a connection fails. Repeating the endpoint can create duplicates, including on platforms that already succeeded. There is no persistent queue, history, scheduling, or cross-request idempotency in this assignment-sized service. Bluesky creates a new app-password session per call; a high-volume deployment would persist and refresh sessions to reduce login rate limits.

The local endpoint has no caller authentication. Add authentication and rate limiting before exposing a credentialed instance to the Internet. Secrets are read from environment variables or an ignored `.env` file, never included in API errors. HTTPX/HTTPCore URL logging is suppressed because Telegram tokens and Discord webhook secrets appear in request URLs. The repository contains only empty credential templates and clearly fake test values.

## Submission

The source, README, API research, examples, tests, and verification evidence form the submission. [docs/submission-email.md](docs/submission-email.md) provides the required email format; replace its personal-detail placeholders before sending.
