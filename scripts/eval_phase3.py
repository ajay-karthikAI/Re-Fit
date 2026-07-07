"""Phase 3 assisted-apply eval.

This harness is intentionally half automation, half manual-review artifact. For
each corpus pair it prepares a real job target, hits the FastAPI
``GET /job-targets/{id}/apply-kit`` endpoint, asserts the mechanical Phase 3
gates, and writes one markdown worksheet per job target in the exact checklist
order a user sees on the Apply Kit screen.

It does *not* prove the 3-minute claim. That requires MANUAL_EVAL.md stopwatch
runs against real ATS pages.
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import re
import sys
from typing import Any
import uuid

import anyio.to_thread
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
import yaml

from app.data.ats_fields import FIELD_TAXONOMY, detect_ats
from app.db import dispose_engine, get_session_factory
from app.main import create_app
from app.models import CoverLetter, JobTarget, ShortAnswer, Upload, User, hash_question
from app.schemas.answer_profile import AnswerProfileWrite
from app.schemas.apply_kit import ApplyKit
from app.schemas.ats_fields import FieldPlanItem
from app.services import answer_profile, storage
from app.services.extract import extract_text
from app.services.pipeline import run_full_pipeline_async
from scripts._llm_guard import HEURISTIC_REPORT_HEADER, guard_llm_or_exit

CORPUS_DIR = Path("tests/corpus")
PAIRS_PATH = CORPUS_DIR / "pairs.yaml"
REPORT_DIR = Path("eval_reports")

ATS_SOURCE_URLS: dict[str, str] = {
    "greenhouse": "https://boards.greenhouse.io/refit/jobs/{slug}",
    "lever": "https://jobs.lever.co/refit/{slug}",
    "ashby": "https://jobs.ashbyhq.com/refit/{slug}",
}
DEFAULT_ATS_CYCLE: tuple[str, ...] = ("greenhouse", "lever", "ashby")

EVAL_ANSWER_PROFILE = AnswerProfileWrite(
    work_auth="citizen",
    sponsorship_needed=False,
    salary_min=150000,
    salary_max=185000,
    salary_currency="USD",
    salary_type="annual",
    relocation="case_by_case",
    notice_period_days=14,
    pronouns=None,
    referral_source_default="Company careers page",
    eeo_prefs=None,
)


@dataclass(frozen=True)
class PreparedTarget:
    pair_id: str
    resume_path: Path
    jd_path: Path
    user_id: uuid.UUID
    upload_id: uuid.UUID
    job_target_id: uuid.UUID
    source_ats: str
    source_url: str


@dataclass(frozen=True)
class ClaimCheck:
    field_key: str
    question: str
    passed: bool
    violations: list[str]
    claims_checked: int


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "target"


def _content_type(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        return "application/pdf"
    if path.suffix.lower() == ".docx":
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return "application/octet-stream"


def _load_pairs(path: Path) -> tuple[str, list[dict[str, str]]]:
    data = yaml.safe_load(path.read_text())
    note = str(data.get("note", "")).strip()
    return note, list(data["pairs"])


def _source_url_for(pair_id: str, ats: str) -> str:
    template = ATS_SOURCE_URLS[ats]
    return template.format(slug=_slug(pair_id))


async def _prepare_target(pair: dict[str, str], source_ats: str) -> PreparedTarget:
    pair_id = pair["id"]
    resume_path = CORPUS_DIR / pair["resume"]
    jd_path = CORPUS_DIR / pair["jd"]
    source_url = _source_url_for(pair_id, source_ats)
    detected_ats = detect_ats(source_url)
    if detected_ats != source_ats:
        raise RuntimeError(f"{source_url} detected as {detected_ats}, expected {source_ats}")

    async with get_session_factory()() as session:
        user = User(email=f"phase3-eval-{pair_id}-{uuid.uuid4()}@example.com")
        session.add(user)
        await session.flush()

        file_bytes = resume_path.read_bytes()
        extracted = extract_text(file_bytes, resume_path.name)
        s3_key = f"phase3_eval_uploads/{user.id}/{uuid.uuid4()}/{resume_path.name}"
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
            company=f"Phase 3 Eval {pair_id}",
            title="Assisted Apply Eval Target",
            source_url=source_url,
            source_ats=source_ats,
        )
        session.add(job_target)
        await session.commit()

        await answer_profile.upsert_answer_profile(session, user.id, EVAL_ANSWER_PROFILE)

        return PreparedTarget(
            pair_id=pair_id,
            resume_path=resume_path,
            jd_path=jd_path,
            user_id=user.id,
            upload_id=upload.id,
            job_target_id=job_target.id,
            source_ats=source_ats,
            source_url=source_url,
        )


def _claim_from_report(field_key: str, question: str, report: dict[str, Any]) -> ClaimCheck:
    claims_checked = sum(
        len(report.get(key) or [])
        for key in (
            "proper_nouns_checked",
            "numbers_checked",
            "company_fact_sentences_checked",
        )
    )
    return ClaimCheck(
        field_key=field_key,
        question=question,
        passed=bool(report.get("passed")),
        violations=[str(item) for item in report.get("violations") or []],
        claims_checked=claims_checked,
    )


async def _claim_checks(
    job_target_id: uuid.UUID,
    fields: Sequence[FieldPlanItem],
) -> dict[str, ClaimCheck]:
    claims: dict[str, ClaimCheck] = {}
    generated_questions = [
        field
        for field in fields
        if field.field_spec.source == "generated" and field.field_spec.question_kind is not None
    ]

    async with get_session_factory()() as session:
        cover_result = await session.execute(
            select(CoverLetter)
            .where(CoverLetter.job_target_id == job_target_id)
            .order_by(CoverLetter.created_at.desc())
        )
        cover = cover_result.scalars().first()
        if cover is None:
            claims["cover_letter"] = ClaimCheck(
                field_key="cover_letter",
                question="Cover letter",
                passed=False,
                violations=["generated cover letter has no persisted claim_report"],
                claims_checked=0,
            )
        else:
            claims["cover_letter"] = _claim_from_report(
                "cover_letter", "Cover letter", cover.claim_report or {}
            )

        for field in generated_questions:
            result = await session.execute(
                select(ShortAnswer).where(
                    ShortAnswer.job_target_id == job_target_id,
                    ShortAnswer.question_hash == hash_question(field.field_spec.label),
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                claims[field.field_spec.key] = ClaimCheck(
                    field_key=field.field_spec.key,
                    question=field.field_spec.label,
                    passed=False,
                    violations=["generated field has no persisted ShortAnswer claim_report"],
                    claims_checked=0,
                )
                continue
            claims[field.field_spec.key] = _claim_from_report(
                field.field_spec.key, row.question, row.claim_report or {}
            )
    return claims


def _check_apply_kit(kit: ApplyKit, claims: dict[str, ClaimCheck]) -> list[str]:
    failures: list[str] = []

    error_fields = [field.field_spec.key for field in kit.field_plan if field.status == "error"]
    if error_fields:
        failures.append("fields in error status: " + ", ".join(error_fields))

    expected_docs = {"resume_pdf", "cover_letter_pdf"}
    docs = {document.key: document for document in kit.documents}
    missing_docs = expected_docs - docs.keys()
    if missing_docs:
        failures.append("missing documents: " + ", ".join(sorted(missing_docs)))
    not_ready = [
        key
        for key in sorted(expected_docs & docs.keys())
        if not docs[key].ready or not docs[key].download_url
    ]
    if not_ready:
        failures.append("documents not ready: " + ", ".join(not_ready))

    if not kit.checklist:
        failures.append("checklist is empty")
    else:
        orders = [step.order for step in kit.checklist]
        expected_orders = list(range(1, len(kit.checklist) + 1))
        if orders != expected_orders:
            failures.append(f"checklist order numbers are {orders}, expected {expected_orders}")
        terminal = kit.checklist[-1]
        if terminal.field_key is not None or terminal.action != "submit":
            failures.append("checklist does not end with the terminal submit step")

    expected_field_order = [spec.key for spec in FIELD_TAXONOMY.get(kit.source_ats, [])]
    actual_field_order = [step.field_key for step in kit.checklist if step.field_key is not None]
    if actual_field_order != expected_field_order:
        failures.append(
            "checklist field order mismatch: "
            f"actual={actual_field_order}, expected={expected_field_order}"
        )

    for claim in claims.values():
        if not claim.passed or claim.violations:
            detail = "; ".join(claim.violations) or "claim_report passed=false"
            failures.append(f"{claim.field_key} fabrication/claim failure: {detail}")

    return failures


def _field_for_key(kit: ApplyKit, key: str | None) -> FieldPlanItem | None:
    if key is None:
        return None
    for field in kit.field_plan:
        if field.field_spec.key == key:
            return field
    return None


def _quote_block(value: str) -> list[str]:
    if not value.strip():
        return ["> (empty)"]
    return ["> " + line if line else ">" for line in value.splitlines()]


def _field_markdown(
    field: FieldPlanItem,
    claims: dict[str, ClaimCheck],
) -> list[str]:
    spec = field.field_spec
    lines = [
        f"### {spec.label}",
        "",
        f"- Field key: `{spec.key}`",
        f"- Source: `{spec.source}`",
        f"- Status: `{field.status}`",
    ]
    if spec.mapped_from:
        lines.append(f"- Mapped from: `{spec.mapped_from}`")
    if spec.question_kind:
        lines.append(f"- Question kind: `{spec.question_kind}`")
    if spec.notes:
        lines.append(f"- Notes: {spec.notes}")
    if field.error:
        lines.append(f"- Error: `{field.error}`")

    claim = claims.get(spec.key)
    if claim is not None:
        lines.extend(
            [
                f"- Claim report: {'passed' if claim.passed else 'failed'}",
                f"- Claims checked: {claim.claims_checked}",
                f"- Claim violations: {len(claim.violations)}",
            ]
        )
        lines.extend(f"  - {violation}" for violation in claim.violations)

    if field.resolved_value is not None:
        heading = "Generated answer" if spec.question_kind else "Resolved value"
        lines.extend(["", f"#### {heading}", ""])
        lines.extend(_quote_block(field.resolved_value))

    return lines


def _write_target_report(
    report_dir: Path,
    target: PreparedTarget,
    kit: ApplyKit,
    claims: dict[str, ClaimCheck],
    failures: list[str],
) -> Path:
    path = report_dir / f"{target.pair_id}.md"
    docs = {document.key: document for document in kit.documents}
    body = [
        f"# Phase 3 Apply Kit Eval: {target.pair_id}",
        "",
        f"- Resume: `{target.resume_path}`",
        f"- JD: `{target.jd_path}`",
        f"- Job target id: `{target.job_target_id}`",
        f"- Source ATS: `{kit.source_ats}`",
        f"- Source URL: {kit.source_url}",
        f"- Status: {'PASS' if not failures else 'FAIL'}",
        "",
        "## Gate Results",
        "",
    ]
    body.extend(f"- {failure}" for failure in failures)
    if not failures:
        body.append("- No automated Phase 3 gate failures.")

    body.extend(["", "## Documents", ""])
    for key in ("resume_pdf", "cover_letter_pdf"):
        document = docs.get(key)
        if document is None:
            body.append(f"- `{key}`: missing")
        else:
            body.append(
                f"- `{document.key}`: ready={document.ready}, url={document.download_url or 'none'}"
            )

    body.extend(["", "## Answer Profile Gaps", ""])
    if kit.answer_profile_gaps:
        for gap in kit.answer_profile_gaps:
            body.append(f"- `{gap.field}`: {gap.label} ({gap.link_target})")
    else:
        body.append("- None.")

    body.extend(["", "## Generated Prose Claim Reports", ""])
    if claims:
        for claim in claims.values():
            body.append(
                f"- `{claim.field_key}`: passed={claim.passed}, "
                f"claims_checked={claim.claims_checked}, violations={len(claim.violations)}"
            )
            body.extend(f"  - {violation}" for violation in claim.violations)
    else:
        body.append("- None.")

    body.extend(
        [
            "",
            "## Checklist And Field Plan",
            "",
            "Read top-to-bottom in the same order as the Apply Kit screen.",
            "",
        ]
    )
    for step in kit.checklist:
        body.extend(
            [
                f"## {step.order}. {step.section}: {step.label}",
                "",
                f"- Action: `{step.action}`",
                f"- Step status: `{step.status}`",
            ]
        )
        field = _field_for_key(kit, step.field_key)
        if field is None:
            body.append("")
            continue
        body.append("")
        body.extend(_field_markdown(field, claims))
        body.append("")

    path.write_text("\n".join(body))
    return path


def _write_failure_report(
    report_dir: Path,
    pair_id: str,
    failures: list[str],
    target: PreparedTarget | None = None,
) -> Path:
    path = report_dir / f"{pair_id}.md"
    body = [
        f"# Phase 3 Apply Kit Eval: {pair_id}",
        "",
        "- Status: FAIL",
    ]
    if target is not None:
        body.extend(
            [
                f"- Resume: `{target.resume_path}`",
                f"- JD: `{target.jd_path}`",
                f"- Job target id: `{target.job_target_id}`",
                f"- Source ATS: `{target.source_ats}`",
                f"- Source URL: {target.source_url}",
            ]
        )
    body.extend(["", "## Gate Results", ""])
    body.extend(f"- {failure}" for failure in failures)
    path.write_text("\n".join(body))
    return path


def _write_index(
    report_dir: Path,
    note: str,
    rows: list[dict[str, Any]],
    *,
    heuristic_mode: bool = False,
) -> Path:
    path = report_dir / "index.md"
    failed = [row for row in rows if row["failures"]]
    body = [
        "# Phase 3 Apply Kit Eval",
        "",
        *([HEURISTIC_REPORT_HEADER, ""] if heuristic_mode else []),
        f"Generated: {datetime.now(UTC).isoformat()}",
        "",
        "Automated gates only. The 3-minute claim still requires MANUAL_EVAL.md.",
        "",
        "## Corpus Note",
        "",
        note or "No corpus note provided.",
        "",
        "## Summary",
        "",
        f"- Job targets: {len(rows)}",
        f"- Automated gate failures: {len(failed)}",
        "",
        "## Job Targets",
        "",
    ]
    for row in rows:
        body.append(
            f"- [{'PASS' if not row['failures'] else 'FAIL'}] "
            f"[{row['pair_id']}]({row['report_name']}) "
            f"- ATS `{row['source_ats']}` - failures={len(row['failures'])}"
        )
        for failure in row["failures"]:
            body.append(f"  - {failure}")
    path.write_text("\n".join(body))
    return path


async def _evaluate_pair(
    client: AsyncClient,
    pair: dict[str, str],
    source_ats: str,
    report_dir: Path,
) -> dict[str, Any]:
    pair_id = pair["id"]
    try:
        target = await _prepare_target(pair, source_ats)
    except Exception as exc:  # noqa: BLE001 - eval records pair failures
        failures = [f"failed to prepare corpus job target: {exc}"]
        report_path = _write_failure_report(report_dir, pair_id, failures)
        return {
            "pair_id": pair_id,
            "source_ats": source_ats,
            "report_name": report_path.name,
            "failures": failures,
        }

    try:
        await run_full_pipeline_async(target.user_id, target.upload_id, target.job_target_id)
    except Exception as exc:  # noqa: BLE001 - eval records pair failures
        failures = [f"pipeline failed before apply-kit assembly: {exc}"]
        report_path = _write_failure_report(report_dir, pair_id, failures, target)
        return {
            "pair_id": pair_id,
            "source_ats": source_ats,
            "report_name": report_path.name,
            "failures": failures,
        }

    try:
        response = await client.get(f"/job-targets/{target.job_target_id}/apply-kit")
    except Exception as exc:  # noqa: BLE001 - eval records pair failures
        failures = [f"GET /apply-kit raised before returning a response: {exc}"]
        report_path = _write_failure_report(report_dir, pair_id, failures, target)
        return {
            "pair_id": pair_id,
            "source_ats": source_ats,
            "report_name": report_path.name,
            "failures": failures,
        }
    if response.status_code != 200:
        failures = [f"GET /apply-kit returned {response.status_code}: {response.text}"]
        kit = None
        report_path = report_dir / f"{target.pair_id}.md"
        report_path.write_text(
            "\n".join(
                [
                    f"# Phase 3 Apply Kit Eval: {target.pair_id}",
                    "",
                    "- Status: FAIL",
                    f"- Job target id: `{target.job_target_id}`",
                    "",
                    "## Gate Results",
                    "",
                    f"- {failures[0]}",
                ]
            )
        )
    else:
        kit = ApplyKit.model_validate(response.json())
        claims = await _claim_checks(target.job_target_id, kit.field_plan)
        failures = _check_apply_kit(kit, claims)
        report_path = _write_target_report(report_dir, target, kit, claims, failures)

    return {
        "pair_id": target.pair_id,
        "source_ats": target.source_ats if kit is None else kit.source_ats,
        "report_name": report_path.name,
        "failures": failures,
    }


def _parse_ats_cycle(value: str) -> tuple[str, ...]:
    items = tuple(item.strip() for item in value.split(",") if item.strip())
    unknown = [item for item in items if item not in ATS_SOURCE_URLS]
    if unknown:
        raise argparse.ArgumentTypeError(
            "unknown ATS value(s): "
            + ", ".join(unknown)
            + f" (expected one of {', '.join(ATS_SOURCE_URLS)})"
        )
    if not items:
        raise argparse.ArgumentTypeError("ATS cycle must not be empty")
    return items


async def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pairs", type=Path, default=PAIRS_PATH)
    parser.add_argument("--report-dir", type=Path, default=REPORT_DIR)
    parser.add_argument(
        "--ats-cycle",
        type=_parse_ats_cycle,
        default=DEFAULT_ATS_CYCLE,
        help="Comma-separated ATS cycle to assign to corpus job targets.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Run only the first N corpus pairs for a bounded smoke.",
    )
    parser.add_argument(
        "--allow-heuristic",
        action="store_true",
        help="Permit running with NO real LLM key, using the heuristic approximation.",
    )
    args = parser.parse_args()

    heuristic_mode = guard_llm_or_exit(args.allow_heuristic, "eval_phase3")

    note, pairs = _load_pairs(args.pairs)
    if args.limit is not None:
        pairs = pairs[: args.limit]

    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    report_dir = args.report_dir / f"phase3_{timestamp}"
    report_dir.mkdir(parents=True, exist_ok=True)

    app = create_app()
    rows: list[dict[str, Any]] = []
    try:
        async with app.router.lifespan_context(app):
            transport = ASGITransport(app=app, raise_app_exceptions=False)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                for index, pair in enumerate(pairs):
                    source_ats = args.ats_cycle[index % len(args.ats_cycle)]
                    print(f"running {pair['id']} ({source_ats})...", flush=True)
                    rows.append(await _evaluate_pair(client, pair, source_ats, report_dir))
    finally:
        await dispose_engine()

    index_path = _write_index(report_dir, note, rows, heuristic_mode=heuristic_mode)
    print(f"wrote {index_path}")

    failed = [row for row in rows if row["failures"]]
    if failed:
        print(f"phase3 eval failed: automated_gate_failures={len(failed)}", file=sys.stderr)
        return 1
    print("phase3 eval automated gates passed")
    manual_path = Path("MANUAL_EVAL.md")
    if manual_path.exists():
        print(f"manual stopwatch worksheet: {manual_path}")
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(_main()))


if __name__ == "__main__":
    main()
