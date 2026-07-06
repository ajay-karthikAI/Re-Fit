"""Pure StructuredResume diff helpers."""

from typing import Any

from app.schemas.resume import StructuredResume
from app.schemas.tailor import TailorDiffEntry


def json_ref(*parts: object) -> str:
    return "/" + "/".join(str(part).replace("~", "~0").replace("/", "~1") for part in parts)


def _append_if_changed(
    changes: list[TailorDiffEntry],
    ref: str,
    before: Any,
    after: Any,
) -> None:
    if before != after:
        changes.append(
            TailorDiffEntry(
                bullet_ref=ref,
                before=before,
                after=after,
            )
        )


def diff_structured_resumes(
    before: StructuredResume,
    after: StructuredResume,
) -> list[TailorDiffEntry]:
    """Return JSON-pointer changes between two structured resumes.

    This function is intentionally pure and does not know about job
    requirements, LLM candidates, or persistence.
    """
    before_dump = before.model_dump(mode="json")
    after_dump = after.model_dump(mode="json")
    changes: list[TailorDiffEntry] = []

    _append_if_changed(
        changes, json_ref("summary"), before_dump.get("summary"), after_dump.get("summary")
    )
    _append_if_changed(
        changes, json_ref("contact"), before_dump.get("contact"), after_dump.get("contact")
    )

    before_experience = before_dump.get("experience") or []
    after_experience = after_dump.get("experience") or []
    max_experience = max(len(before_experience), len(after_experience))
    for index in range(max_experience):
        if index >= len(before_experience) or index >= len(after_experience):
            _append_if_changed(
                changes,
                json_ref("experience", index),
                before_experience[index] if index < len(before_experience) else None,
                after_experience[index] if index < len(after_experience) else None,
            )
            continue

        before_item = before_experience[index]
        after_item = after_experience[index]
        for field in ["company", "title", "location", "start_date", "end_date", "technologies"]:
            _append_if_changed(
                changes,
                json_ref("experience", index, field),
                before_item.get(field),
                after_item.get(field),
            )

        before_bullets = before_item.get("bullets") or []
        after_bullets = after_item.get("bullets") or []
        max_bullets = max(len(before_bullets), len(after_bullets))
        for bullet_index in range(max_bullets):
            _append_if_changed(
                changes,
                json_ref("experience", index, "bullets", bullet_index),
                before_bullets[bullet_index] if bullet_index < len(before_bullets) else None,
                after_bullets[bullet_index] if bullet_index < len(after_bullets) else None,
            )

    _append_if_changed(
        changes, json_ref("education"), before_dump.get("education"), after_dump.get("education")
    )
    _append_if_changed(
        changes, json_ref("skills"), before_dump.get("skills"), after_dump.get("skills")
    )

    before_projects = before_dump.get("projects") or []
    after_projects = after_dump.get("projects") or []
    max_projects = max(len(before_projects), len(after_projects))
    for index in range(max_projects):
        if index >= len(before_projects) or index >= len(after_projects):
            _append_if_changed(
                changes,
                json_ref("projects", index),
                before_projects[index] if index < len(before_projects) else None,
                after_projects[index] if index < len(after_projects) else None,
            )
            continue

        before_project = before_projects[index]
        after_project = after_projects[index]
        for field in ["name", "description", "technologies", "url"]:
            _append_if_changed(
                changes,
                json_ref("projects", index, field),
                before_project.get(field),
                after_project.get(field),
            )

        before_bullets = before_project.get("bullets") or []
        after_bullets = after_project.get("bullets") or []
        max_bullets = max(len(before_bullets), len(after_bullets))
        for bullet_index in range(max_bullets):
            _append_if_changed(
                changes,
                json_ref("projects", index, "bullets", bullet_index),
                before_bullets[bullet_index] if bullet_index < len(before_bullets) else None,
                after_bullets[bullet_index] if bullet_index < len(after_bullets) else None,
            )

    return [change for change in changes if change.before != change.after]
