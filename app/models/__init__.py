"""SQLAlchemy models. Import them all here so Base.metadata (and Alembic
autogenerate) always sees the full schema."""

from app.models.answer_profile import (
    AnswerProfile,
    RelocationPreference,
    SalaryType,
    WorkAuthStatus,
)
from app.models.application import Application, ApplicationStatus
from app.models.auth_session import AuthSession
from app.models.bullet_embedding import BulletEmbedding
from app.models.cover_letter import CoverLetter, CoverLetterTone
from app.models.document import Document, DocumentKind
from app.models.followup import Followup, FollowupKind
from app.models.job_target import JobTarget
from app.models.pipeline_run import PipelineRun, PipelineRunStatus
from app.models.posting import Posting
from app.models.profile import Profile
from app.models.resume_version import ResumeVersion
from app.models.saved_search import Digest, PostingMatch, SavedSearch
from app.models.short_answer import ShortAnswer, ShortAnswerKind, hash_question
from app.models.source_board import BoardHealth, SourceBoard, SourceKind
from app.models.upload import Upload
from app.models.user import User

__all__ = [
    "AnswerProfile",
    "Application",
    "ApplicationStatus",
    "AuthSession",
    "BulletEmbedding",
    "CoverLetter",
    "CoverLetterTone",
    "Digest",
    "Document",
    "DocumentKind",
    "Followup",
    "FollowupKind",
    "JobTarget",
    "PipelineRun",
    "PipelineRunStatus",
    "Posting",
    "PostingMatch",
    "Profile",
    "SavedSearch",
    "RelocationPreference",
    "ResumeVersion",
    "SalaryType",
    "ShortAnswer",
    "ShortAnswerKind",
    "BoardHealth",
    "SourceBoard",
    "SourceKind",
    "Upload",
    "User",
    "WorkAuthStatus",
    "hash_question",
]
