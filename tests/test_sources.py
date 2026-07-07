"""Unit tests for the external job-source clients.

All HTTP is mocked with respx — these never touch the network, so they are safe
in CI. Payloads mirror the real Greenhouse/Lever shapes (real board tokens from
WATCHED_BOARDS.md are used as URL fixtures, but the calls are mocked). The
"does the real API still match the docs" check is a separate, manual,
non-CI run against live boards.
"""

import httpx
import pytest
import respx

from app.services.sources import html_to_text
from app.services.sources.base import (
    BoardNotFoundError,
    SourceParseError,
    SourceUnavailableError,
    _BACKOFF_BASE,  # noqa: F401  (imported to document what the retry test tunes)
)
from app.services.sources.greenhouse import GreenhouseClient
from app.services.sources.lever import LeverClient

GH_URL = "https://boards-api.greenhouse.io/v1/boards/pathai/jobs?content=true"
LV_URL = "https://api.lever.co/v0/postings/mistral?mode=json"

# Greenhouse returns HTML that is entity-encoded in the JSON string.
_GH_CONTENT = "&lt;h2&gt;Who We Are&lt;/h2&gt;\n&lt;ul&gt;&lt;li&gt;Ship models&lt;/li&gt;&lt;li&gt;Improve diagnosis&lt;/li&gt;&lt;/ul&gt;"

_GH_PAYLOAD = {
    "jobs": [
        {
            "id": 8308240002,
            "title": "Staff Machine Learning Engineer",
            "absolute_url": "https://boards.greenhouse.io/pathai/jobs/8308240002",
            "location": {"name": "Boston (Onsite) Preferred, or Remote"},
            "departments": [{"id": 1, "name": "Machine Learning"}],
            "updated_at": "2026-04-22T17:22:12-04:00",
            "content": _GH_CONTENT,
        }
    ]
}

_LV_PAYLOAD = [
    {
        "id": "7894fd8a-ffc9-4c89-87f0-f8a7b695cf01",
        "text": "Account Executive – AI for Citizens",
        "categories": {"location": "Paris", "team": "Business", "commitment": "Full-time"},
        "hostedUrl": "https://jobs.lever.co/mistral/7894fd8a-ffc9-4c89-87f0-f8a7b695cf01",
        "createdAt": 1753687796431,
        "descriptionPlain": "About Mistral \n \nAt Mistral AI, we build AI.",
        "description": "<div>About Mistral</div>",
    }
]


# --- Greenhouse happy path --------------------------------------------------


@respx.mock
async def test_greenhouse_lists_and_maps_postings() -> None:
    respx.get(GH_URL).mock(return_value=httpx.Response(200, json=_GH_PAYLOAD))

    postings = await GreenhouseClient().list_postings("pathai")

    assert len(postings) == 1
    p = postings[0]
    assert p.source == "greenhouse"
    assert p.external_id == "8308240002"  # int stringified
    assert p.title == "Staff Machine Learning Engineer"
    assert p.department == "Machine Learning"
    assert p.location.startswith("Boston")
    assert p.url == "https://boards.greenhouse.io/pathai/jobs/8308240002"
    assert p.posted_at is not None and p.posted_at.year == 2026
    # content was entity-encoded HTML; description_text is clean, structured text.
    text = p.description_text
    assert "<" not in text and "&lt;" not in text
    assert "Who We Are" in text
    assert "Ship models" in text.splitlines()
    assert "Improve diagnosis" in text.splitlines()


# --- Lever happy path -------------------------------------------------------


@respx.mock
async def test_lever_lists_and_maps_postings() -> None:
    respx.get(LV_URL).mock(return_value=httpx.Response(200, json=_LV_PAYLOAD))

    postings = await LeverClient().list_postings("mistral")

    assert len(postings) == 1
    p = postings[0]
    assert p.source == "lever"
    assert p.external_id == "7894fd8a-ffc9-4c89-87f0-f8a7b695cf01"
    assert p.title == "Account Executive – AI for Citizens"
    assert p.location == "Paris"
    assert p.department == "Business"
    assert p.url.endswith("/mistral/7894fd8a-ffc9-4c89-87f0-f8a7b695cf01")
    # createdAt is epoch milliseconds -> July 2025.
    assert p.posted_at is not None
    assert (p.posted_at.year, p.posted_at.month) == (2025, 7)
    # descriptionPlain preferred; non-breaking spaces normalized.
    assert "\xa0" not in p.description_text
    assert "About Mistral" in p.description_text


# --- 404 -> typed error, never retried --------------------------------------


@respx.mock
async def test_greenhouse_404_raises_board_not_found() -> None:
    route = respx.get("https://boards-api.greenhouse.io/v1/boards/nope/jobs?content=true").mock(
        return_value=httpx.Response(404)
    )

    with pytest.raises(BoardNotFoundError) as excinfo:
        await GreenhouseClient().list_postings("nope")

    assert excinfo.value.board_token == "nope"
    assert excinfo.value.source == "greenhouse"
    assert route.call_count == 1  # a real 404 is never retried


@respx.mock
async def test_lever_404_raises_board_not_found() -> None:
    route = respx.get("https://api.lever.co/v0/postings/nope?mode=json").mock(
        return_value=httpx.Response(404)
    )

    with pytest.raises(BoardNotFoundError):
        await LeverClient().list_postings("nope")

    assert route.call_count == 1


# --- Malformed / unexpected responses -> typed parse error, not a crash -----


@respx.mock
async def test_greenhouse_malformed_json_raises_parse_error() -> None:
    respx.get(GH_URL).mock(return_value=httpx.Response(200, text="{not valid json"))

    with pytest.raises(SourceParseError):
        await GreenhouseClient().list_postings("pathai")


@respx.mock
async def test_lever_malformed_json_raises_parse_error() -> None:
    respx.get(LV_URL).mock(return_value=httpx.Response(200, text="}{"))

    with pytest.raises(SourceParseError):
        await LeverClient().list_postings("mistral")


@respx.mock
async def test_greenhouse_unexpected_shape_raises_parse_error() -> None:
    # Valid JSON, but a job is missing required fields.
    respx.get(GH_URL).mock(return_value=httpx.Response(200, json={"jobs": [{"id": 1}]}))

    with pytest.raises(SourceParseError):
        await GreenhouseClient().list_postings("pathai")


@respx.mock
async def test_lever_non_array_raises_parse_error() -> None:
    respx.get(LV_URL).mock(return_value=httpx.Response(200, json={"error": "nope"}))

    with pytest.raises(SourceParseError):
        await LeverClient().list_postings("mistral")


# --- Retry policy: 5xx/timeout retried, then typed unavailable --------------


@respx.mock
async def test_5xx_is_retried_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.sources.base._BACKOFF_BASE", 0.0)
    route = respx.get(GH_URL).mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(200, json=_GH_PAYLOAD),
        ]
    )

    postings = await GreenhouseClient().list_postings("pathai")

    assert len(postings) == 1
    assert route.call_count == 2  # retried the 503, then succeeded


@respx.mock
async def test_persistent_5xx_raises_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.sources.base._BACKOFF_BASE", 0.0)
    route = respx.get(GH_URL).mock(return_value=httpx.Response(500))

    with pytest.raises(SourceUnavailableError):
        await GreenhouseClient().list_postings("pathai")

    assert route.call_count == 3  # MAX_ATTEMPTS


@respx.mock
async def test_timeout_is_retried_then_raises_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.sources.base._BACKOFF_BASE", 0.0)
    route = respx.get(LV_URL).mock(side_effect=httpx.ConnectTimeout("slow"))

    with pytest.raises(SourceUnavailableError):
        await LeverClient().list_postings("mistral")

    assert route.call_count == 3


# --- html_to_text helper ----------------------------------------------------


def test_html_to_text_preserves_list_structure() -> None:
    html = "<p>Requirements:</p><ul><li>Python</li><li>SQL</li></ul>"
    lines = html_to_text(html).splitlines()

    assert "Python" in lines
    assert "SQL" in lines
    assert "<" not in "\n".join(lines)


def test_html_to_text_handles_plain_text_and_nbsp() -> None:
    assert html_to_text("Just plain   text") == "Just plain text"
    assert html_to_text("") == ""
