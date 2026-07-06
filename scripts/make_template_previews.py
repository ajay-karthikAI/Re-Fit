"""Render and upload template preview PNGs.

Usage:
    uv run python -m scripts.make_template_previews
    uv run python -m scripts.make_template_previews --output-dir output/template_previews
"""

from argparse import ArgumentParser
from pathlib import Path

import pymupdf

from app.schemas.resume import StructuredResume
from app.services import storage
from app.services.render import render_pdf_result
from app.services.templates import list_template_specs, template_preview_key


def fixture_resume() -> StructuredResume:
    return StructuredResume(
        contact={
            "full_name": "Sam Okafor",
            "email": "sam.okafor@example.com",
            "phone": "(555) 019-4452",
            "location": "Chicago, IL",
            "linkedin_url": "https://www.linkedin.com/in/sam-okafor",
        },
        summary=(
            "Senior backend engineer focused on reliable APIs, data systems, and operational "
            "ownership for logistics products."
        ),
        experience=[
            {
                "company": "Nimbus Freight",
                "title": "Senior Backend Engineer",
                "location": "Chicago, IL",
                "start_date": "2020-05",
                "end_date": None,
                "bullets": [
                    "Own rate-quoting service in Go and Postgres, sustaining 8k rps peak.",
                    "Led cloud migration from EC2 to EKS across 11 production services.",
                    "Reduced p99 quote latency from 900ms to 210ms through query tuning.",
                    "Designed Python APIs for shipment workflows with durable validation.",
                ],
                "technologies": ["Go", "Postgres", "Python", "EKS", "EC2"],
            },
            {
                "company": "Parkside Labs",
                "title": "Backend Engineer",
                "location": "Remote",
                "start_date": "2017-09",
                "end_date": "2020-04",
                "bullets": [
                    "Built booking APIs in Django for 200k monthly users.",
                    "Improved observability for production services with actionable alerts.",
                    "Partnered with product teams on launch plans and incident follow-up.",
                ],
                "technologies": ["Django", "PostgreSQL", "Redis"],
            },
        ],
        education=[
            {
                "institution": "University of Illinois Chicago",
                "degree": "BEng",
                "field": "Software Engineering",
                "graduation_date": "2017-05",
                "details": ["Graduated with honors."],
            }
        ],
        skills=[
            {"category": "Backend", "items": ["Python", "Go", "Postgres", "Django", "FastAPI"]},
            {"category": "Platform", "items": ["EKS", "EC2", "Redis", "Kafka", "Terraform"]},
        ],
        projects=[
            {
                "name": "ops-check",
                "description": "Operational checklist service.",
                "bullets": ["Built CLI reporting for production readiness reviews."],
                "technologies": ["Python"],
            }
        ],
    )


def rasterize_page_one(pdf_bytes: bytes, *, zoom: float = 1.45) -> bytes:
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        page = doc[0]
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
        return pixmap.tobytes("png")


def generate_previews(
    *,
    output_dir: Path | None = None,
    upload: bool = True,
) -> dict[str, bytes]:
    resume = fixture_resume()
    previews: dict[str, bytes] = {}
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)

    for spec in list_template_specs():
        pdf = render_pdf_result(resume, template=spec.id)
        png = rasterize_page_one(pdf.content)
        previews[spec.id] = png
        if output_dir is not None:
            (output_dir / f"{spec.id}.png").write_bytes(png)
        if upload:
            storage.put_object(template_preview_key(spec.id), png, "image/png")
    return previews


def main() -> None:
    parser = ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--no-upload", action="store_true")
    args = parser.parse_args()

    previews = generate_previews(output_dir=args.output_dir, upload=not args.no_upload)
    for template_id in previews:
        print(f"generated {template_preview_key(template_id)}")


if __name__ == "__main__":
    main()
