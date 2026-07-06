"""SQLAlchemy models. Import them all here so Base.metadata (and Alembic
autogenerate) always sees the full schema."""

from app.models.application import Application, ApplicationStatus
from app.models.bullet_embedding import BulletEmbedding
from app.models.cover_letter import CoverLetter, CoverLetterTone
from app.models.document import Document, DocumentKind
from app.models.followup import Followup, FollowupKind
from app.models.job_target import JobTarget
from app.models.pipeline_run import PipelineRun, PipelineRunStatus
from app.models.profile import Profile
from app.models.resume_version import ResumeVersion
from app.models.upload import Upload
from app.models.user import User

__all__ = [
    "Application",
    "ApplicationStatus",
    "BulletEmbedding",
    "CoverLetter",
    "CoverLetterTone",
    "Document",
    "DocumentKind",
    "Followup",
    "FollowupKind",
    "JobTarget",
    "PipelineRun",
    "PipelineRunStatus",
    "Profile",
    "ResumeVersion",
    "Upload",
    "User",
]
