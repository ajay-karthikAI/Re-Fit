"""Run the Phase 1 eval matrix and emit the exit report.

This script intentionally exercises the real pipeline path: stored upload,
parse, JD extraction, embeddings, tailoring, scoring, rendering, and document
storage. It requires Postgres, Redis/worker only for API mode, and MinIO from
docker compose; this direct harness calls the service orchestration in-process.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
from pathlib import Path
import sys
import uuid
from typing import Any

import anyio.to_thread
import yaml

from app.db import get_session_factory
from app.models import JobTarget, Profile, ResumeVersion, Upload, User
from app.schemas.jd import JobRequirements
from app.schemas.resume import StructuredResume
from app.services import storage
from app.services.claims import verify_rewrite
from app.services.cover_letter import MAX_WORDS, MIN_WORDS, generate_cover_letter
from app.services.extract import extract_text
from app.services.pipeline import run_full_pipeline_async
from app.services.render import render_docx_result, render_pdf_result
from app.services.templates import TemplateId
from scripts._llm_guard import HEURISTIC_REPORT_HEADER, guard_llm_or_exit

CORPUS_DIR = Path("tests/corpus")
PAIRS_PATH = CORPUS_DIR / "pairs.yaml"
REPORT_DIR = Path("eval_reports")
ALL_TEMPLATES: tuple[TemplateId, ...] = ("classic", "compact", "modern", "mono")


def _content_type(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        return "application/pdf"
    if path.suffix.lower() == ".docx":
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return "application/octet-stream"


def _fmt_cost(value: Any) -> str:
    if value is None:
        return "n/a (set LLM_INPUT_COST_PER_MILLION and LLM_OUTPUT_COST_PER_MILLION)"
    return f"${float(value):.4f}"


def _score_summary(score: dict[str, Any]) -> str:
    keyword = score["keyword_coverage"]
    missing = ", ".join(keyword["missing_terms"]) or "none"
    return f"{score['headline_score']:.2f} (keyword {keyword['score']:.2f}; missing: {missing})"


def _resolve_experience_index(pointer: str) -> int | None:
    parts = pointer.strip("/").split("/")
    if len(parts) >= 4 and parts[0] == "experience" and parts[2] == "bullets":
        return int(parts[1])
    return None


async def _create_eval_inputs(
    pair_id: str, resume_path: Path, jd_path: Path
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    async with get_session_factory()() as session:
        user = User(email=f"eval-{pair_id}-{uuid.uuid4()}@example.com")
        session.add(user)
        await session.flush()

        file_bytes = resume_path.read_bytes()
        extracted = extract_text(file_bytes, resume_path.name)
        s3_key = f"eval_uploads/{user.id}/{uuid.uuid4()}/{resume_path.name}"
        await anyio.to_thread.run_sync(
            storage.put_object,
            s3_key,
            file_bytes,
            _content_type(resume_path),
        )
        upload = Upload(
            user_id=user.id,
            s3_key=s3_key,
            filename=resume_path.name,
            source_format=extracted.source_format,
        )
        session.add(upload)

        job_target = JobTarget(
            user_id=user.id,
            raw_description=jd_path.read_text(),
            company=f"Eval {pair_id}",
            title="Eval Target",
        )
        session.add(job_target)
        await session.commit()
        return user.id, upload.id, job_target.id


async def _verify_accepted_claims(results: dict[str, Any], job_target_id: uuid.UUID) -> list[str]:
    async with get_session_factory()() as session:
        source_version = await session.get(ResumeVersion, uuid.UUID(results["source_version_id"]))
        if source_version is None:
            return ["source version missing"]
        job_target = await session.get(JobTarget, job_target_id)
        if job_target is None or job_target.extracted_requirements is None:
            return ["job requirements missing"]

        source_resume = StructuredResume.model_validate(source_version.data)
        requirements = JobRequirements.model_validate(job_target.extracted_requirements)

    failures: list[str] = []
    for entry in results["diff"]:
        pointer = entry["bullet_ref"]
        experience_index = _resolve_experience_index(pointer)
        if experience_index is None:
            continue
        verification = verify_rewrite(
            original=entry["before"],
            rewritten=entry["after"],
            profile=source_resume,
            requirements=requirements,
            parent_experience=source_resume.experience[experience_index],
        )
        if not verification.passed:
            failures.append(f"{pointer}: {'; '.join(verification.reasons)}")
    return failures


async def _run_pair(pair: dict[str, str]) -> dict[str, Any]:
    pair_id = pair["id"]
    resume_path = CORPUS_DIR / pair["resume"]
    jd_path = CORPUS_DIR / pair["jd"]
    started = datetime.now(UTC)
    user_id, upload_id, job_target_id = await _create_eval_inputs(pair_id, resume_path, jd_path)

    try:
        results = await run_full_pipeline_async(user_id, upload_id, job_target_id)
        accepted_failures = await _verify_accepted_claims(results, job_target_id)
        before = results["scores"]["before"]["headline_score"]
        after = results["scores"]["after"]["headline_score"]
        return {
            "id": pair_id,
            "resume": str(resume_path),
            "jd": str(jd_path),
            "status": "succeeded",
            "started_at": started.isoformat(),
            "_job_target_id": str(job_target_id),
            "version_id": results["version_id"],
            "download_url": results["download_url"],
            "before_score": before,
            "after_score": after,
            "score_delta": round(after - before, 2),
            "results": results,
            "accepted_claim_failures": accepted_failures,
            "error": None,
        }
    except Exception as exc:
        return {
            "id": pair_id,
            "resume": str(resume_path),
            "jd": str(jd_path),
            "status": "failed",
            "started_at": started.isoformat(),
            "_job_target_id": str(job_target_id),
            "version_id": None,
            "download_url": None,
            "before_score": None,
            "after_score": None,
            "score_delta": None,
            "results": None,
            "accepted_claim_failures": [],
            "error": str(exc),
        }


async def _kit_context(
    results: dict[str, Any], job_target_id: uuid.UUID
) -> tuple[StructuredResume, StructuredResume, JobRequirements, str]:
    """Canonical profile, tailored resume, requirements, and raw JD for a run."""
    async with get_session_factory()() as session:
        version = await session.get(ResumeVersion, uuid.UUID(results["version_id"]))
        job_target = await session.get(JobTarget, job_target_id)
        if version is None or job_target is None or job_target.extracted_requirements is None:
            raise RuntimeError("kit context missing version or requirements")
        profile = await session.get(Profile, version.profile_id)
        if profile is None:
            raise RuntimeError("kit context missing canonical profile")
        return (
            StructuredResume.model_validate(profile.data),
            StructuredResume.model_validate(version.data),
            JobRequirements.model_validate(job_target.extracted_requirements),
            job_target.raw_description,
        )


def _roundtrip_templates(resume: StructuredResume) -> tuple[list[dict[str, Any]], list[str]]:
    """Render the tailored resume in every template and both formats; report failures."""
    rows: list[dict[str, Any]] = []
    failures: list[str] = []
    for template in ALL_TEMPLATES:
        row: dict[str, Any] = {"template": template}
        try:
            pdf = render_pdf_result(resume, template=template)
            if not pdf.content or (pdf.page_count or 0) < 1:
                failures.append(f"{template} pdf produced no pages")
            row["pdf_pages"] = pdf.page_count
        except Exception as exc:  # noqa: BLE001 - eval records, does not raise
            failures.append(f"{template} pdf render error: {exc}")
            row["pdf_pages"] = None
        try:
            docx = render_docx_result(resume, template=template)
            if not docx.content:
                failures.append(f"{template} docx produced no bytes")
            row["docx_bytes"] = len(docx.content)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{template} docx render error: {exc}")
            row["docx_bytes"] = None
        rows.append(row)
    return rows, failures


async def _run_pair_phase2(pair: dict[str, str]) -> dict[str, Any]:
    """Phase 2 exit check: full kit (tailor + letter + all-format renders) per pair."""
    base = await _run_pair(pair)
    if base["status"] != "succeeded":
        base.update(
            letter=None,
            letter_word_count=None,
            letter_claim_violations=["pipeline did not complete"],
            template_roundtrip=[],
            template_failures=["pipeline did not complete"],
        )
        return base

    try:
        job_target_id = uuid.UUID(base["_job_target_id"])
        profile, tailored, requirements, raw_jd = await _kit_context(base["results"], job_target_id)
        letter = await generate_cover_letter(profile, requirements, raw_jd, tailored)
        letter_violations = list(letter.claim_report.violations)
        if not letter.claim_report.passed and not letter_violations:
            letter_violations = ["claim report not passed"]
        if not MIN_WORDS <= letter.word_count <= MAX_WORDS:
            letter_violations.append(
                f"letter word count {letter.word_count} outside {MIN_WORDS}-{MAX_WORDS}"
            )
        roundtrip, template_failures = await anyio.to_thread.run_sync(
            _roundtrip_templates, tailored
        )
        base.update(
            letter=letter.body_markdown,
            letter_word_count=letter.word_count,
            letter_claim_violations=letter_violations,
            template_roundtrip=roundtrip,
            template_failures=template_failures,
        )
    except Exception as exc:  # noqa: BLE001 - record as a pair failure
        base["status"] = "failed"
        base["error"] = f"phase2 kit error: {exc}"
        base.update(
            letter=None,
            letter_word_count=None,
            letter_claim_violations=[str(exc)],
            template_roundtrip=[],
            template_failures=[str(exc)],
        )
    return base


def _report_pair_phase2(row: dict[str, Any]) -> str:
    lines = [_report_pair(row), ""]
    if row["status"] != "succeeded":
        return "\n".join(lines)
    lines.append("### Cover Letter")
    lines.append(f"- Word count: {row['letter_word_count']} (target {MIN_WORDS}-{MAX_WORDS})")
    violations = row["letter_claim_violations"]
    lines.append(f"- Claim violations: {len(violations)}")
    for violation in violations:
        lines.append(f"  - {violation}")
    lines.append("")
    lines.append("> " + "\n> ".join((row["letter"] or "").splitlines()))
    lines.append("")
    lines.append("### Template Round-trip")
    for entry in row["template_roundtrip"]:
        lines.append(
            f"- `{entry['template']}`: pdf pages={entry['pdf_pages']}, "
            f"docx bytes={entry['docx_bytes']}"
        )
    if row["template_failures"]:
        lines.append("")
        lines.append("#### Template failures")
        lines.extend(f"- {failure}" for failure in row["template_failures"])
    return "\n".join(lines)


def _write_report_phase2(
    note: str, rows: list[dict[str, Any]], *, heuristic_mode: bool = False
) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    path = REPORT_DIR / f"phase2_{timestamp}.md"
    failed = [row for row in rows if row["status"] != "succeeded"]
    letter_failures = [row for row in rows if row.get("letter_claim_violations")]
    template_failures = [row for row in rows if row.get("template_failures")]

    body = [
        "# Phase 2 Eval Report",
        "",
        *([HEURISTIC_REPORT_HEADER, ""] if heuristic_mode else []),
        f"Generated: {datetime.now(UTC).isoformat()}",
        "",
        "Full-kit exit check: tailor + cover letter + all-format renders per pair.",
        "Manually review each cover-letter excerpt below for fabrication.",
        "",
        "## Corpus Note",
        "",
        note or "No corpus note provided.",
        "",
        "## Summary",
        "",
        f"- Pairs: {len(rows)}",
        f"- Stage errors: {len(failed)}",
        f"- Pairs with letter claim/word violations: {len(letter_failures)}",
        f"- Pairs with template round-trip failures: {len(template_failures)}",
        "",
    ]
    body.extend(_report_pair_phase2(row) + "\n" for row in rows)
    path.write_text("\n".join(body))
    return path


def _load_pairs(path: Path) -> tuple[str, list[dict[str, str]]]:
    data = yaml.safe_load(path.read_text())
    note = str(data.get("note", "")).strip()
    pairs = list(data["pairs"])
    if len(pairs) < 10:
        raise ValueError(f"{path} must contain at least 10 pairs")
    return note, pairs


def _report_pair(row: dict[str, Any]) -> str:
    lines = [
        f"## {row['id']}",
        "",
        f"- Resume: `{row['resume']}`",
        f"- JD: `{row['jd']}`",
        f"- Status: **{row['status']}**",
    ]
    if row["error"]:
        lines.append(f"- Error: `{row['error']}`")
        return "\n".join(lines)

    results = row["results"]
    before = results["scores"]["before"]
    after = results["scores"]["after"]
    usage = results["token_usage"]
    discarded = results["discarded_rewrites"]
    accepted_failures = row["accepted_claim_failures"]
    lines.extend(
        [
            f"- Version: `{row['version_id']}`",
            f"- PDF: {row['download_url']}",
            f"- Before score: {_score_summary(before)}",
            f"- After score: {_score_summary(after)}",
            f"- Score delta: {row['score_delta']:.2f}",
            f"- Rewrites accepted/discarded: "
            f"{results['rewrite_stats']['rewrites_accepted']}/"
            f"{results['rewrite_stats']['rewrites_discarded']}",
            f"- Accepted claim-check failures: {len(accepted_failures)}",
            f"- Pipeline timings: `{results.get('pipeline_timings', {})}`",
            f"- Token usage: input={usage['input_tokens']}, output={usage['output_tokens']}, "
            f"total={usage['total_tokens']}",
            f"- Estimated cost: {_fmt_cost(results['estimated_cost_usd'])}",
            "",
            "### Diff",
        ]
    )
    if results["diff"]:
        for entry in results["diff"]:
            lines.extend(
                [
                    f"- `{entry['bullet_ref']}` targeting `{entry['requirement_targeted']}`",
                    f"  - Before: {entry['before']}",
                    f"  - After: {entry['after']}",
                ]
            )
    else:
        lines.append("- No accepted rewrites.")

    lines.append("")
    lines.append("### Discarded Rewrites / Claim Checks")
    if discarded:
        for item in discarded:
            lines.append(f"- `{item['bullet_ref']}`: {'; '.join(item['reasons'])}")
    else:
        lines.append("- None.")
    if accepted_failures:
        lines.append("")
        lines.append("### Accepted Rewrite Verification Failures")
        lines.extend(f"- {failure}" for failure in accepted_failures)
    return "\n".join(lines)


def _write_report(note: str, rows: list[dict[str, Any]], *, heuristic_mode: bool = False) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    path = REPORT_DIR / f"{timestamp}.md"
    failed = [row for row in rows if row["status"] != "succeeded"]
    negative = [row for row in rows if row["score_delta"] is not None and row["score_delta"] < 0]
    accepted_failures = [row for row in rows if row["accepted_claim_failures"]]

    body = [
        "# Phase 1 Eval Report",
        "",
        *([HEURISTIC_REPORT_HEADER, ""] if heuristic_mode else []),
        f"Generated: {datetime.now(UTC).isoformat()}",
        "",
        "## Corpus Note",
        "",
        note or "No corpus note provided.",
        "",
        "## Summary",
        "",
        f"- Pairs: {len(rows)}",
        f"- Stage errors: {len(failed)}",
        f"- Negative score deltas: {len(negative)}",
        f"- Accepted rewrite claim failures: {len(accepted_failures)}",
        "",
    ]
    body.extend(_report_pair(row) + "\n" for row in rows)
    path.write_text("\n".join(body))
    return path


async def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pairs", type=Path, default=PAIRS_PATH)
    parser.add_argument(
        "--phase2",
        action="store_true",
        help="Run the full-kit Phase 2 exit check (tailor + letter + all-format renders).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Run only the first N pairs (for a bounded smoke of the report).",
    )
    parser.add_argument(
        "--allow-heuristic",
        action="store_true",
        help="Permit running with NO real LLM key, using the heuristic approximation.",
    )
    args = parser.parse_args()

    heuristic_mode = guard_llm_or_exit(args.allow_heuristic, "eval_phase1")

    note, pairs = _load_pairs(args.pairs)
    if args.limit is not None:
        pairs = pairs[: args.limit]

    rows = []
    for pair in pairs:
        print(f"running {pair['id']}...", flush=True)
        rows.append(await (_run_pair_phase2(pair) if args.phase2 else _run_pair(pair)))

    if args.phase2:
        report_path = _write_report_phase2(note, rows, heuristic_mode=heuristic_mode)
    else:
        report_path = _write_report(note, rows, heuristic_mode=heuristic_mode)
    print(f"wrote {report_path}")

    failed = [row for row in rows if row["status"] != "succeeded"]
    negative = [row for row in rows if row["score_delta"] is not None and row["score_delta"] < 0]
    accepted_failures = [row for row in rows if row["accepted_claim_failures"]]
    problems = (
        f"stage_errors={len(failed)} "
        f"negative_deltas={len(negative)} "
        f"accepted_claim_failures={len(accepted_failures)}"
    )
    exit_bad = bool(failed or negative or accepted_failures)
    if args.phase2:
        letter_failures = [row for row in rows if row.get("letter_claim_violations")]
        template_failures = [row for row in rows if row.get("template_failures")]
        problems += (
            f" letter_violations={len(letter_failures)} template_failures={len(template_failures)}"
        )
        exit_bad = exit_bad or bool(letter_failures or template_failures)

    if exit_bad:
        print(f"eval failed: {problems}", file=sys.stderr)
        return 1
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(_main()))


if __name__ == "__main__":
    main()
