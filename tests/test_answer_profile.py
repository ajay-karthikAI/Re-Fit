import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from pydantic import ValidationError

from app.models import AnswerProfile
from app.schemas.answer_profile import AnswerProfileWrite
from app.services.answer_profile import completeness

FULL_PROFILE: dict[str, Any] = {
    "work_auth": "citizen",
    "sponsorship_needed": False,
    "salary_min": 140000,
    "salary_max": 170000,
    "salary_currency": "USD",
    "salary_type": "annual",
    "relocation": "case_by_case",
    "notice_period_days": 14,
    "pronouns": "she/her",
    "referral_source_default": "Company careers page",
    "eeo_prefs": {"veteran_status": "not_a_veteran"},
}


def _profile(**overrides: Any) -> dict[str, Any]:
    return {**FULL_PROFILE, **overrides}


# --- schema-level cross-field validation -----------------------------------


def test_salary_max_below_min_rejected() -> None:
    with pytest.raises(ValidationError, match="salary_max"):
        AnswerProfileWrite(**_profile(salary_min=150000, salary_max=100000))


def test_salary_max_equal_to_min_accepted() -> None:
    profile = AnswerProfileWrite(**_profile(salary_min=150000, salary_max=150000))
    assert profile.salary_min == profile.salary_max == 150000


def test_salary_range_with_one_side_missing_accepted() -> None:
    profile = AnswerProfileWrite(**_profile(salary_min=150000, salary_max=None))
    assert profile.salary_max is None


def test_needs_sponsorship_without_flag_rejected() -> None:
    with pytest.raises(ValidationError, match="sponsorship_needed"):
        AnswerProfileWrite(**_profile(work_auth="needs_sponsorship", sponsorship_needed=False))


def test_needs_sponsorship_with_flag_accepted() -> None:
    profile = AnswerProfileWrite(**_profile(work_auth="needs_sponsorship", sponsorship_needed=True))
    assert profile.work_auth == "needs_sponsorship"
    assert profile.sponsorship_needed is True


def test_citizen_with_sponsorship_false_accepted() -> None:
    profile = AnswerProfileWrite(**_profile(work_auth="citizen", sponsorship_needed=False))
    assert profile.sponsorship_needed is False


# --- completeness: pure function --------------------------------------------


def test_completeness_no_profile_reports_all_required_missing() -> None:
    result = completeness(None)
    assert result.complete is False
    assert set(result.missing_fields) == {"work_auth", "sponsorship_needed", "relocation"}


def test_completeness_partial_profile_reports_only_unset_required_fields() -> None:
    partial = AnswerProfile(work_auth="citizen", sponsorship_needed=False)
    # relocation deliberately left unset (transient instance, never flushed).
    result = completeness(partial)
    assert result.complete is False
    assert result.missing_fields == ["relocation"]


def test_completeness_full_profile_reports_complete() -> None:
    full = AnswerProfile(
        work_auth="citizen",
        sponsorship_needed=False,
        relocation="yes",
        salary_type="annual",
        salary_currency="USD",
    )
    result = completeness(full)
    assert result.complete is True
    assert result.missing_fields == []


def test_completeness_ignores_optional_fields() -> None:
    """salary/notice/pronouns/eeo never block completeness, even fully unset."""
    full = AnswerProfile(
        work_auth="citizen",
        sponsorship_needed=False,
        relocation="no",
        salary_type="annual",
        salary_currency="USD",
        salary_min=None,
        salary_max=None,
        notice_period_days=None,
        pronouns=None,
        eeo_prefs=None,
    )
    result = completeness(full)
    assert result.complete is True
    assert result.missing_fields == []


# --- HTTP: PUT (upsert) / GET / completeness --------------------------------


async def _make_user(client: AsyncClient, email: str) -> str:
    response = await client.post("/users", json={"email": email})
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def test_put_creates_then_get_returns_it(client: AsyncClient) -> None:
    user_id = await _make_user(client, "answer-profile-create@example.com")

    response = await client.get(f"/users/{user_id}/answer-profile")
    assert response.status_code == 404

    response = await client.put(f"/users/{user_id}/answer-profile", json=FULL_PROFILE)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["user_id"] == user_id
    assert body["work_auth"] == "citizen"
    assert body["salary_min"] == 140000
    assert body["eeo_prefs"] == {"veteran_status": "not_a_veteran"}

    response = await client.get(f"/users/{user_id}/answer-profile")
    assert response.status_code == 200
    assert response.json()["salary_max"] == 170000


async def test_put_twice_replaces_the_single_row(client: AsyncClient) -> None:
    user_id = await _make_user(client, "answer-profile-upsert@example.com")

    response = await client.put(f"/users/{user_id}/answer-profile", json=FULL_PROFILE)
    assert response.status_code == 200, response.text
    first_id = response.json()["id"]

    updated = _profile(
        work_auth="needs_sponsorship",
        sponsorship_needed=True,
        salary_min=None,
        salary_max=None,
        pronouns=None,
    )
    response = await client.put(f"/users/{user_id}/answer-profile", json=updated)
    assert response.status_code == 200, response.text
    assert response.json()["id"] == first_id  # same row, replaced not duplicated
    assert response.json()["work_auth"] == "needs_sponsorship"
    assert response.json()["salary_min"] is None
    assert response.json()["pronouns"] is None

    response = await client.get(f"/users/{user_id}/answer-profile")
    assert response.json()["work_auth"] == "needs_sponsorship"


async def test_put_rejects_salary_contradiction_over_http(client: AsyncClient) -> None:
    user_id = await _make_user(client, "answer-profile-bad-salary@example.com")
    response = await client.put(
        f"/users/{user_id}/answer-profile",
        json=_profile(salary_min=150000, salary_max=100000),
    )
    assert response.status_code == 422


async def test_put_rejects_sponsorship_contradiction_over_http(client: AsyncClient) -> None:
    user_id = await _make_user(client, "answer-profile-bad-sponsorship@example.com")
    response = await client.put(
        f"/users/{user_id}/answer-profile",
        json=_profile(work_auth="needs_sponsorship", sponsorship_needed=False),
    )
    assert response.status_code == 422


async def test_put_unknown_user_404(client: AsyncClient) -> None:
    response = await client.put(f"/users/{uuid.uuid4()}/answer-profile", json=FULL_PROFILE)
    assert response.status_code == 404


async def test_completeness_endpoint_before_and_after_put(client: AsyncClient) -> None:
    user_id = await _make_user(client, "answer-profile-completeness@example.com")

    response = await client.get(f"/users/{user_id}/answer-profile/completeness")
    assert response.status_code == 200
    body = response.json()
    assert body["complete"] is False
    assert set(body["missing_fields"]) == {"work_auth", "sponsorship_needed", "relocation"}

    response = await client.put(f"/users/{user_id}/answer-profile", json=FULL_PROFILE)
    assert response.status_code == 200, response.text

    response = await client.get(f"/users/{user_id}/answer-profile/completeness")
    assert response.status_code == 200
    assert response.json() == {"complete": True, "missing_fields": []}
