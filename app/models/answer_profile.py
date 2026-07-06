import enum
import uuid
from typing import Any

from sqlalchemy import Enum, ForeignKey, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class WorkAuthStatus(enum.StrEnum):
    citizen = "citizen"
    permanent_resident = "permanent_resident"
    visa_holder = "visa_holder"
    needs_sponsorship = "needs_sponsorship"
    other = "other"


class SalaryType(enum.StrEnum):
    annual = "annual"
    hourly = "hourly"


class RelocationPreference(enum.StrEnum):
    yes = "yes"
    no = "no"
    case_by_case = "case_by_case"


class AnswerProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Durable, user-owned facts needed on every application form but not part
    of the resume itself. Exactly one per user. Never LLM-filled — a missing
    field must prompt the user, never be guessed.
    """

    __tablename__ = "answer_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )
    work_auth: Mapped[WorkAuthStatus] = mapped_column(Enum(WorkAuthStatus, name="work_auth_status"))
    sponsorship_needed: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    salary_min: Mapped[int | None] = mapped_column(Integer)
    salary_max: Mapped[int | None] = mapped_column(Integer)
    salary_currency: Mapped[str] = mapped_column(
        String(length=3), default="USD", server_default="USD"
    )
    salary_type: Mapped[SalaryType] = mapped_column(Enum(SalaryType, name="salary_type"))
    relocation: Mapped[RelocationPreference] = mapped_column(
        Enum(RelocationPreference, name="relocation_preference")
    )
    notice_period_days: Mapped[int | None] = mapped_column(Integer)
    pronouns: Mapped[str | None]
    referral_source_default: Mapped[str | None]
    eeo_prefs: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    """Free-form, user-controlled EEO/veteran/disability self-ID preferences. Never LLM-touched."""
