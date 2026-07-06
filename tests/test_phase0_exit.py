"""Phase 0 exit criterion: the full user → profile → job target → version →
application chain works end to end through the API, against real Postgres."""

from typing import Any

from httpx import AsyncClient

RESUME: dict[str, Any] = {
    "contact": {"full_name": "Test Person", "email": "tp@example.com"},
    "summary": "Engineer.",
    "experience": [
        {
            "company": "Acme",
            "title": "Engineer",
            "start_date": "2020-01",
            "end_date": None,
            "bullets": ["Built the thing."],
            "technologies": ["Python"],
        }
    ],
    "education": [],
    "skills": [{"category": "Languages", "items": ["Python"]}],
    "projects": [],
}


async def _make_user(client: AsyncClient, email: str) -> str:
    response = await client.post("/users", json={"email": email})
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _make_chain(client: AsyncClient, email: str) -> dict[str, str]:
    """Create user → profile → job target, return their ids."""
    user_id = await _make_user(client, email)

    response = await client.put(f"/users/{user_id}/profile", json=RESUME)
    assert response.status_code == 200, response.text
    profile_id = response.json()["id"]

    response = await client.post(
        f"/users/{user_id}/job-targets",
        json={"raw_description": "Great job.", "company": "Initech", "title": "Staff Engineer"},
    )
    assert response.status_code == 201, response.text
    return {"user_id": user_id, "profile_id": profile_id, "job_target_id": response.json()["id"]}


async def test_phase0_full_chain(client: AsyncClient) -> None:
    ids = await _make_chain(client, "phase0@example.com")

    response = await client.get(f"/users/{ids['user_id']}/profile")
    assert response.status_code == 200
    assert response.json()["data"]["contact"]["full_name"] == "Test Person"

    response = await client.post(
        f"/profiles/{ids['profile_id']}/versions",
        json={"job_target_id": ids["job_target_id"], "label": "Initech v1"},
    )
    assert response.status_code == 201, response.text
    version = response.json()
    assert version["data"] == response.json()["data"]  # well-formed StructuredResume
    assert version["data"]["contact"]["full_name"] == "Test Person"

    response = await client.post(
        f"/users/{ids['user_id']}/applications",
        json={
            "job_target_id": ids["job_target_id"],
            "resume_version_id": version["id"],
            "status": "applied",
        },
    )
    assert response.status_code == 201, response.text
    application_id = response.json()["id"]

    response = await client.patch(
        f"/applications/{application_id}", json={"notes": "Phone screen scheduled."}
    )
    assert response.status_code == 200
    assert response.json()["notes"] == "Phone screen scheduled."

    response = await client.get(f"/users/{ids['user_id']}/applications")
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 1
    row = rows[0]
    # The exit criterion: the exact submitted version id round-trips.
    assert row["resume_version_id"] == version["id"]
    assert row["company"] == "Initech"
    assert row["title"] == "Staff Engineer"
    assert row["resume_version_label"] == "Initech v1"
    assert row["status"] == "applied"


async def test_duplicate_version_for_job_target_conflicts(client: AsyncClient) -> None:
    ids = await _make_chain(client, "dup@example.com")

    body = {"job_target_id": ids["job_target_id"], "label": "first"}
    response = await client.post(f"/profiles/{ids['profile_id']}/versions", json=body)
    assert response.status_code == 201, response.text

    response = await client.post(f"/profiles/{ids['profile_id']}/versions", json=body)
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


async def test_cross_user_version_rejected(client: AsyncClient) -> None:
    owner = await _make_chain(client, "owner@example.com")
    response = await client.post(
        f"/profiles/{owner['profile_id']}/versions",
        json={"job_target_id": owner["job_target_id"]},
    )
    assert response.status_code == 201
    foreign_version_id = response.json()["id"]

    intruder = await _make_chain(client, "intruder@example.com")
    response = await client.post(
        f"/users/{intruder['user_id']}/applications",
        json={
            "job_target_id": intruder["job_target_id"],
            "resume_version_id": foreign_version_id,
        },
    )
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]
