"""Version history, diff, compare, and soft-delete services."""

from datetime import UTC, datetime
import re
import uuid
from typing import Any

import anyio.to_thread
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Application, Document, DocumentKind, JobTarget, Profile, ResumeVersion
from app.schemas.jd import JobRequirements
from app.schemas.resume import StructuredResume
from app.schemas.score import ATSScore
from app.schemas.tailor import TailorDiffEntry
from app.schemas.version_history import (
    DiffChange,
    DiffSummaryHeader,
    EnrichedVersionDiff,
    ExperienceDiffGroup,
    ProjectDiffGroup,
    ResumeVersionListItem,
    VersionDocumentAvailability,
    VersionJobTargetSummary,
)
from app.services.diffing import diff_structured_resumes
from app.services.errors import ConflictError, NotFoundError
from app.services.score import score_resume
from app.services.score_cache import build_score_cache, headline_from_cache

_EXPERIENCE_BULLET_RE = re.compile(r"^/experience/(\d+)/bullets/(\d+)$")
_PROJECT_BULLET_RE = re.compile(r"^/projects/(\d+)/bullets/(\d+)$")


async def cache_score_for_version(
    session: AsyncSession,
    version: ResumeVersion,
    job_target: JobTarget,
    *,
    score: ATSScore | None = None,
) -> ATSScore | None:
    if job_target.extracted_requirements is None:
        return None
    if score is None:
        resume = StructuredResume.model_validate(version.data)
        requirements = JobRequirements.model_validate(job_target.extracted_requirements)
        score = await anyio.to_thread.run_sync(lambda: score_resume(resume, requirements))
    version.score_cache = build_score_cache(job_target.id, score)
    await session.flush()
    return score


async def _get_active_version(session: AsyncSession, version_id: uuid.UUID) -> ResumeVersion:
    version = await session.get(ResumeVersion, version_id)
    if version is None or version.deleted_at is not None:
        raise NotFoundError(f"resume version {version_id} not found")
    return version


async def _documents_for_versions(
    session: AsyncSession, version_ids: list[uuid.UUID]
) -> dict[uuid.UUID, set[DocumentKind]]:
    if not version_ids:
        return {}
    result = await session.execute(
        select(Document).where(Document.resume_version_id.in_(version_ids))
    )
    documents: dict[uuid.UUID, set[DocumentKind]] = {
        version_id: set() for version_id in version_ids
    }
    for document in result.scalars().all():
        documents.setdefault(document.resume_version_id, set()).add(document.kind)
    return documents


def _availability(kinds: set[DocumentKind]) -> VersionDocumentAvailability:
    formats: list[str] = []
    if DocumentKind.resume_pdf in kinds:
        formats.append("pdf")
    if DocumentKind.resume_docx in kinds:
        formats.append("docx")
    return VersionDocumentAvailability(
        pdf="pdf" in formats,
        docx="docx" in formats,
        rendered_formats=formats,
    )


async def list_profile_versions(
    session: AsyncSession, profile_id: uuid.UUID
) -> list[ResumeVersionListItem]:
    profile = await session.get(Profile, profile_id)
    if profile is None:
        raise NotFoundError(f"profile {profile_id} not found")

    result = await session.execute(
        select(ResumeVersion)
        .where(ResumeVersion.profile_id == profile_id, ResumeVersion.deleted_at.is_(None))
        .order_by(ResumeVersion.created_at.desc())
    )
    versions = list(result.scalars().all())
    job_target_ids = [version.job_target_id for version in versions if version.job_target_id]
    job_targets: dict[uuid.UUID, JobTarget] = {}
    if job_target_ids:
        job_result = await session.execute(
            select(JobTarget).where(JobTarget.id.in_(job_target_ids))
        )
        job_targets = {job.id: job for job in job_result.scalars().all()}

    documents = await _documents_for_versions(session, [version.id for version in versions])
    items: list[ResumeVersionListItem] = []
    for version in versions:
        job_target = job_targets.get(version.job_target_id) if version.job_target_id else None
        if job_target is not None and headline_from_cache(version.score_cache) is None:
            await cache_score_for_version(session, version, job_target)
        items.append(
            ResumeVersionListItem(
                id=version.id,
                label=version.label,
                job_target=(
                    VersionJobTargetSummary(
                        id=job_target.id,
                        company=job_target.company,
                        title=job_target.title,
                    )
                    if job_target is not None
                    else None
                ),
                template_id=version.template_id,
                created_at=version.created_at,
                headline_score=headline_from_cache(version.score_cache),
                document_availability=_availability(documents.get(version.id, set())),
            )
        )
    await session.commit()
    return items


def _total_bullets(resume: StructuredResume) -> int:
    return sum(len(item.bullets) for item in resume.experience) + sum(
        len(project.bullets) for project in resume.projects
    )


def _change_from_entry(entry: dict[str, Any] | TailorDiffEntry) -> DiffChange:
    data = entry.model_dump(mode="json") if isinstance(entry, TailorDiffEntry) else entry
    return DiffChange(
        ref=str(data.get("bullet_ref") or data.get("ref")),
        before=data.get("before"),
        after=data.get("after"),
        requirement_targeted=data.get("requirement_targeted"),
    )


def _experience_label(resume: StructuredResume, index: int) -> tuple[str | None, str | None]:
    if index >= len(resume.experience):
        return None, None
    item = resume.experience[index]
    return item.company, item.title


def _project_label(resume: StructuredResume, index: int) -> str | None:
    if index >= len(resume.projects):
        return None
    return resume.projects[index].name


def enrich_diff(
    *,
    target_resume: StructuredResume,
    changes: list[dict[str, Any] | TailorDiffEntry],
    version_id: uuid.UUID | None = None,
    compare_from_version_id: uuid.UUID | None = None,
    compare_to_version_id: uuid.UUID | None = None,
    raw_diff: dict[str, Any] | None = None,
) -> EnrichedVersionDiff:
    diff_changes = [_change_from_entry(change) for change in changes]
    experience_groups: dict[int, ExperienceDiffGroup] = {}
    project_groups: dict[int, ProjectDiffGroup] = {}
    section_reorderings: list[DiffChange] = []
    other_changes: list[DiffChange] = []

    bullet_refs: set[str] = set()
    requirements: set[str] = set()
    for change in diff_changes:
        if change.requirement_targeted:
            requirements.add(change.requirement_targeted)
        experience_match = _EXPERIENCE_BULLET_RE.fullmatch(change.ref)
        if experience_match:
            index = int(experience_match.group(1))
            bullet_refs.add(change.ref)
            company, title = _experience_label(target_resume, index)
            group = experience_groups.setdefault(
                index,
                ExperienceDiffGroup(
                    experience_ref=f"/experience/{index}",
                    experience_index=index,
                    company=company,
                    title=title,
                ),
            )
            group.changes.append(change)
            continue

        project_match = _PROJECT_BULLET_RE.fullmatch(change.ref)
        if project_match:
            index = int(project_match.group(1))
            bullet_refs.add(change.ref)
            group = project_groups.setdefault(
                index,
                ProjectDiffGroup(
                    project_ref=f"/projects/{index}",
                    project_index=index,
                    name=_project_label(target_resume, index),
                ),
            )
            group.changes.append(change)
            continue

        if change.ref in {"/skills", "/education"} or change.ref.startswith("/skills/"):
            section_reorderings.append(change)
        else:
            other_changes.append(change)

    raw = raw_diff or {}
    stats = raw.get("stats") if isinstance(raw.get("stats"), dict) else {}
    skills_reordered = bool(stats.get("skills_reordered")) or any(
        change.ref == "/skills" for change in section_reorderings
    )
    summary = DiffSummaryHeader(
        bullets_rewritten=len(bullet_refs),
        bullets_unchanged=max(0, _total_bullets(target_resume) - len(bullet_refs)),
        skills_reordered=skills_reordered,
        requirements_targeted=sorted(requirements),
    )
    return EnrichedVersionDiff(
        version_id=version_id,
        compare_from_version_id=compare_from_version_id,
        compare_to_version_id=compare_to_version_id,
        summary=summary,
        experience_groups=[experience_groups[index] for index in sorted(experience_groups)],
        project_groups=[project_groups[index] for index in sorted(project_groups)],
        section_reorderings=section_reorderings,
        other_changes=other_changes,
        discarded_rewrites=list(raw.get("discarded_rewrites") or []),
        raw_diff=raw,
    )


async def get_enriched_diff(session: AsyncSession, version_id: uuid.UUID) -> EnrichedVersionDiff:
    version = await _get_active_version(session, version_id)
    raw = version.diff or {}
    changes = list(raw.get("changes") or [])
    return enrich_diff(
        target_resume=StructuredResume.model_validate(version.data),
        changes=changes,
        version_id=version.id,
        raw_diff=raw,
    )


async def compare_versions(
    session: AsyncSession, from_version_id: uuid.UUID, to_version_id: uuid.UUID
) -> EnrichedVersionDiff:
    from_version = await _get_active_version(session, from_version_id)
    to_version = await _get_active_version(session, to_version_id)
    changes = diff_structured_resumes(
        StructuredResume.model_validate(from_version.data),
        StructuredResume.model_validate(to_version.data),
    )
    return enrich_diff(
        target_resume=StructuredResume.model_validate(to_version.data),
        changes=changes,
        compare_from_version_id=from_version.id,
        compare_to_version_id=to_version.id,
        raw_diff={"changes": [change.model_dump(mode="json") for change in changes]},
    )


async def soft_delete_version(session: AsyncSession, version_id: uuid.UUID) -> None:
    version = await _get_active_version(session, version_id)
    result = await session.execute(
        select(Application.id).where(Application.resume_version_id == version.id).limit(1)
    )
    if result.scalar_one_or_none() is not None:
        raise ConflictError("cannot delete a resume version referenced by an application")
    version.deleted_at = datetime.now(UTC)
    await session.commit()
