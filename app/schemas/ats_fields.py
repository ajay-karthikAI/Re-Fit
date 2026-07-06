"""Types for the ATS field taxonomy and the resolved field plan.

The taxonomy data itself and the orchestration live in ``app/data/ats_fields.py``;
these are just the Pydantic shapes they produce (Pydantic-everywhere, per CLAUDE.md).
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.models.short_answer import ShortAnswerKind

ATSName = Literal["greenhouse", "lever", "ashby", "unknown"]
"""The ATSs whose field taxonomies we encode directly, plus ``unknown``."""

FieldSource = Literal["answer_profile", "profile", "generated", "manual_only"]
"""Where a field's value comes from:

- ``answer_profile`` — a durable, user-owned fact (see AnswerProfile).
- ``profile`` — a fact from the user's canonical resume/contact info.
- ``generated`` — produced by refit (a short-answer block, or a rendered doc to upload).
- ``manual_only`` — never auto-filled; always the user's own action (e.g. EEO self-ID).
"""

FieldStatus = Literal["ready", "needs_generation", "needs_user_input", "manual_only", "error"]
"""Resolution outcome for a field in a concrete plan.

``build_field_plan`` only ever emits the first four; ``error`` is reserved for
the apply-kit, which resolves ``needs_generation`` fields inline and marks the
ones whose generation failed (with a reason) rather than silently dropping them."""


class FieldSpec(BaseModel):
    """One field a given ATS presents on its application form."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str
    label: str
    source: FieldSource
    mapped_from: str | None = None
    """Dotted path to the backing value, e.g. ``"answer_profile.work_auth"`` or
    ``"profile.contact.full_name"``. ``None`` for generated/manual_only fields."""
    question_kind: ShortAnswerKind | None = None
    """Set only on generated short-answer fields, so the generator knows which
    evidence-pack prompt to run (why_company / why_role / custom)."""
    notes: str | None = None


class FieldPlanItem(BaseModel):
    """A FieldSpec resolved against a specific user's answer profile and resume."""

    model_config = ConfigDict(extra="forbid")

    field_spec: FieldSpec
    resolved_value: str | None
    status: FieldStatus
    error: str | None = None
    """Set only when ``status == "error"``: the reason generation failed, so the
    UI can surface it instead of dropping the field."""
