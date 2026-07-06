"""AnswerProfile CRUD: durable, user-authored facts pasted into ATS forms.

No LLM call anywhere in this file, on purpose — these are facts only the
user knows (salary, work authorization, ...), never something to infer.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AnswerProfile
from app.schemas.answer_profile import AnswerProfileCompleteness, AnswerProfileWrite
from app.services.errors import NotFoundError
from app.services.users import get_user

REQUIRED_FOR_COMPLETENESS = ("work_auth", "sponsorship_needed", "relocation")
"""Fields that genuinely block form-filling if unset. Salary, notice period,
pronouns, and EEO prefs are optional and never affect completeness."""


async def _get_answer_profile_row(
    session: AsyncSession, user_id: uuid.UUID
) -> AnswerProfile | None:
    result = await session.execute(select(AnswerProfile).where(AnswerProfile.user_id == user_id))
    return result.scalar_one_or_none()


async def upsert_answer_profile(
    session: AsyncSession, user_id: uuid.UUID, payload: AnswerProfileWrite
) -> AnswerProfile:
    await get_user(session, user_id)
    profile = await _get_answer_profile_row(session, user_id)
    data = payload.model_dump()
    if profile is None:
        profile = AnswerProfile(user_id=user_id, **data)
        session.add(profile)
    else:
        for field, value in data.items():
            setattr(profile, field, value)
    await session.commit()
    await session.refresh(profile)
    return profile


async def get_answer_profile(session: AsyncSession, user_id: uuid.UUID) -> AnswerProfile:
    await get_user(session, user_id)
    profile = await _get_answer_profile_row(session, user_id)
    if profile is None:
        raise NotFoundError(f"user {user_id} has no answer profile")
    return profile


def completeness(profile: AnswerProfile | None) -> AnswerProfileCompleteness:
    """Pure: never stored, always recomputed from the current row (or lack of one)."""
    if profile is None:
        missing = list(REQUIRED_FOR_COMPLETENESS)
    else:
        missing = [field for field in REQUIRED_FOR_COMPLETENESS if getattr(profile, field) is None]
    return AnswerProfileCompleteness(complete=not missing, missing_fields=missing)


async def get_completeness(session: AsyncSession, user_id: uuid.UUID) -> AnswerProfileCompleteness:
    await get_user(session, user_id)
    profile = await _get_answer_profile_row(session, user_id)
    return completeness(profile)
