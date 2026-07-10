"""Password auth: register/login issue bearer sessions, credentials are
verified against bcrypt hashes (never stored in plaintext), and /auth/me and
logout honor session state."""

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User

EMAIL = "casey@example.com"
PASSWORD = "correct horse battery staple"


async def _register(client: AsyncClient, email: str = EMAIL, password: str = PASSWORD) -> dict:
    response = await client.post("/auth/register", json={"email": email, "password": password})
    assert response.status_code == 201, response.text
    return response.json()


async def test_register_issues_session_and_hashes_password(
    client: AsyncClient, session: AsyncSession
) -> None:
    body = await _register(client)
    assert body["token"]
    assert body["user"]["email"] == EMAIL

    user = (await session.execute(select(User).where(User.email == EMAIL))).scalar_one()
    assert user.password_hash is not None
    assert PASSWORD not in user.password_hash
    assert user.password_hash.startswith("$2")  # bcrypt, not plaintext


async def test_login_with_correct_password(client: AsyncClient) -> None:
    await _register(client)
    response = await client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert response.status_code == 200
    body = response.json()
    assert body["token"]
    assert body["user"]["email"] == EMAIL


async def test_login_rejects_wrong_password_and_unknown_email(client: AsyncClient) -> None:
    await _register(client)
    wrong = await client.post("/auth/login", json={"email": EMAIL, "password": "not-the-password"})
    assert wrong.status_code == 401
    unknown = await client.post(
        "/auth/login", json={"email": "ghost@example.com", "password": PASSWORD}
    )
    assert unknown.status_code == 401
    # Both failure modes read identically so responses don't leak which emails exist.
    assert wrong.json()["detail"] == unknown.json()["detail"]


async def test_register_conflicts_on_existing_password_account(client: AsyncClient) -> None:
    await _register(client)
    response = await client.post(
        "/auth/register", json={"email": EMAIL, "password": "another password 1"}
    )
    assert response.status_code == 409


async def test_register_claims_legacy_passwordless_account(
    client: AsyncClient, session: AsyncSession
) -> None:
    # A pre-auth account (dev picker / seed scripts) has no credential…
    created = await client.post("/users", json={"email": EMAIL})
    assert created.status_code == 201
    legacy_id = created.json()["id"]

    # …cannot log in…
    denied = await client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert denied.status_code == 401

    # …and is claimed (same id, now with a password) by registering.
    body = await _register(client)
    assert body["user"]["id"] == legacy_id
    login = await client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert login.status_code == 200


async def test_register_rejects_short_password(client: AsyncClient) -> None:
    response = await client.post("/auth/register", json={"email": EMAIL, "password": "short"})
    assert response.status_code == 422


async def test_me_requires_live_session_and_logout_revokes(client: AsyncClient) -> None:
    token = (await _register(client))["token"]
    headers = {"Authorization": f"Bearer {token}"}

    me = await client.get("/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["email"] == EMAIL

    assert (await client.get("/auth/me")).status_code == 401
    assert (
        await client.get("/auth/me", headers={"Authorization": "Bearer bogus-token"})
    ).status_code == 401

    logout = await client.post("/auth/logout", headers=headers)
    assert logout.status_code == 204
    assert (await client.get("/auth/me", headers=headers)).status_code == 401
