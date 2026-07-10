"""Password auth and bearer sessions (the Phase 3 credential layer).

Passwords are bcrypt-hashed (hashing runs in a worker thread — bcrypt is
deliberately CPU-slow). Sessions are opaque ``secrets`` tokens handed to the
client once; only their SHA-256 is persisted, so the sessions table never
contains anything replayable.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

import anyio.to_thread
import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuthSession, User
from app.services.errors import AuthenticationError, ConflictError

SESSION_TTL = timedelta(days=30)

_INVALID_CREDENTIALS = "invalid email or password"


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def _issue_session(session: AsyncSession, user: User) -> str:
    token = secrets.token_urlsafe(32)
    session.add(
        AuthSession(
            user_id=user.id,
            token_hash=_token_hash(token),
            expires_at=datetime.now(UTC) + SESSION_TTL,
        )
    )
    await session.commit()
    return token


async def register(session: AsyncSession, email: str, password: str) -> tuple[User, str]:
    """Create an account with a password and open a session.

    An existing account that already has a password is a conflict. An existing
    account *without* one (created by the pre-auth dev picker or seed scripts)
    is claimed: registering with its email sets its first password. That claim
    path is a dev-phase convenience — revisit before real multi-user exposure.
    """
    email = email.strip().lower()
    password_hash = await anyio.to_thread.run_sync(_hash_password, password)

    existing = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if existing is not None:
        if existing.password_hash is not None:
            raise ConflictError(f"an account for {email!r} already exists — log in instead")
        existing.password_hash = password_hash
        user = existing
    else:
        user = User(email=email, password_hash=password_hash)
        session.add(user)
    await session.commit()
    await session.refresh(user)
    token = await _issue_session(session, user)
    return user, token


async def login(session: AsyncSession, email: str, password: str) -> tuple[User, str]:
    """Verify credentials and open a session. Every failure mode — unknown
    email, passwordless legacy account, wrong password — raises the same
    error so responses don't reveal which emails have accounts."""
    email = email.strip().lower()
    user = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if user is None or user.password_hash is None:
        # Burn a hash anyway so the timing doesn't distinguish unknown emails.
        await anyio.to_thread.run_sync(_hash_password, password)
        raise AuthenticationError(_INVALID_CREDENTIALS)
    ok = await anyio.to_thread.run_sync(_verify_password, password, user.password_hash)
    if not ok:
        raise AuthenticationError(_INVALID_CREDENTIALS)
    token = await _issue_session(session, user)
    return user, token


async def _live_session(session: AsyncSession, token: str) -> AuthSession:
    record = (
        await session.execute(
            select(AuthSession).where(AuthSession.token_hash == _token_hash(token))
        )
    ).scalar_one_or_none()
    if record is None or record.revoked_at is not None or record.expires_at <= datetime.now(UTC):
        raise AuthenticationError("session is invalid or expired")
    return record


async def resolve_session(session: AsyncSession, token: str) -> User:
    record = await _live_session(session, token)
    user = await session.get(User, record.user_id)
    if user is None:
        raise AuthenticationError("session is invalid or expired")
    return user


async def logout(session: AsyncSession, token: str) -> None:
    record = await _live_session(session, token)
    record.revoked_at = datetime.now(UTC)
    await session.commit()
