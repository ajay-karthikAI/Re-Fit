from typing import Any

from httpx import AsyncClient

RESUME: dict[str, Any] = {
    "contact": {"full_name": "History Person", "email": "history@example.com"},
    "summary": "Engineer.",
    "experience": [
        {
            "company": "Acme",
            "title": "Engineer",
            "start_date": "2020-01",
            "end_date": None,
            "bullets": ["Built Python services."],
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


async def test_delete_referenced_version_conflicts(client: AsyncClient) -> None:
    user_id = await _make_user(client, "history-delete@example.com")
    response = await client.put(f"/users/{user_id}/profile", json=RESUME)
    assert response.status_code == 200, response.text
    profile_id = response.json()["id"]

    response = await client.post(
        f"/users/{user_id}/job-targets",
        json={"raw_description": "Python services.", "company": "Initech", "title": "Engineer"},
    )
    assert response.status_code == 201, response.text
    job_target_id = response.json()["id"]

    response = await client.post(
        f"/profiles/{profile_id}/versions",
        json={"job_target_id": job_target_id, "label": "submitted"},
    )
    assert response.status_code == 201, response.text
    version_id = response.json()["id"]

    response = await client.post(
        f"/users/{user_id}/applications",
        json={"job_target_id": job_target_id, "resume_version_id": version_id},
    )
    assert response.status_code == 201, response.text

    response = await client.delete(f"/versions/{version_id}")

    assert response.status_code == 409
    assert "referenced by an application" in response.json()["detail"]
