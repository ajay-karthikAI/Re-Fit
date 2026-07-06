"""Resume template registry."""

from dataclasses import dataclass
import re
from typing import Literal

import anyio.to_thread
from pydantic import BaseModel, ConfigDict

from app.services import storage

TemplateId = Literal["classic", "compact", "modern", "mono"]
TemplateFormat = Literal["pdf", "docx"]
TemplateVariableType = Literal["color", "number"]

_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
_TEMPLATE_ORDER: tuple[TemplateId, ...] = ("classic", "compact", "modern", "mono")
PREVIEW_PREFIX = "template-previews"


class TemplateVariableSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: TemplateVariableType
    default: str | float
    description: str
    minimum: float | None = None
    maximum: float | None = None


class TemplateSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: TemplateId
    name: str
    description: str
    supports: list[TemplateFormat]
    variables: dict[str, TemplateVariableSpec]


class TemplatePreviewSpec(TemplateSpec):
    preview_png_url: str


@dataclass(frozen=True)
class TemplateRenderSettings:
    template_id: TemplateId
    accent_color: str
    font_scale: float
    font_stack: str
    heading_font_stack: str
    contact_font_stack: str
    docx_body_font: str
    docx_heading_font: str
    docx_contact_font: str
    pdf_font_attempts: tuple[float, float, float]
    margin_in: float
    docx_body_size: float
    docx_heading_size: float
    docx_subheading_size: float
    docx_contact_size: float
    docx_line_spacing: float
    docx_section_before: float
    docx_heading_after: float
    docx_bullet_after: float


_SPECS: dict[TemplateId, TemplateSpec] = {
    "classic": TemplateSpec(
        id="classic",
        name="Classic",
        description="Traditional single-column resume with balanced spacing and serif-neutral restraint.",
        supports=["pdf", "docx"],
        variables={
            "accent_color": TemplateVariableSpec(
                type="color",
                default="#24526b",
                description="Header and section accent color.",
            ),
            "font_scale": TemplateVariableSpec(
                type="number",
                default=1.0,
                description="Multiplier applied to the family base font sizes.",
                minimum=0.9,
                maximum=1.1,
            ),
        },
    ),
    "compact": TemplateSpec(
        id="compact",
        name="Compact",
        description="Tighter spacing for dense senior resumes that need to stay within two pages.",
        supports=["pdf", "docx"],
        variables={
            "accent_color": TemplateVariableSpec(
                type="color",
                default="#24526b",
                description="Header and section accent color.",
            ),
            "font_scale": TemplateVariableSpec(
                type="number",
                default=1.0,
                description="Multiplier applied to the compact 10pt base.",
                minimum=0.9,
                maximum=1.08,
            ),
        },
    ),
    "modern": TemplateSpec(
        id="modern",
        name="Modern",
        description="Sans-serif treatment with a stronger name block and thin teal section rules.",
        supports=["pdf", "docx"],
        variables={
            "accent_color": TemplateVariableSpec(
                type="color",
                default="#1f766f",
                description="Restrained teal accent used for rules and headings.",
            ),
            "font_scale": TemplateVariableSpec(
                type="number",
                default=1.0,
                description="Multiplier applied to the family base font sizes.",
                minimum=0.9,
                maximum=1.1,
            ),
        },
    ),
    "mono": TemplateSpec(
        id="mono",
        name="Mono",
        description="Developer-signal aesthetic with monospaced name, contact, and headings only.",
        supports=["pdf", "docx"],
        variables={
            "accent_color": TemplateVariableSpec(
                type="color",
                default="#3f5f6b",
                description="Disciplined blue-gray accent for heading rules.",
            ),
            "font_scale": TemplateVariableSpec(
                type="number",
                default=1.0,
                description="Multiplier applied to the family base font sizes.",
                minimum=0.9,
                maximum=1.1,
            ),
        },
    ),
}


def list_template_specs() -> list[TemplateSpec]:
    return [_SPECS[template_id] for template_id in _TEMPLATE_ORDER]


def get_template_spec(template_id: str) -> TemplateSpec:
    try:
        return _SPECS[template_id]  # type: ignore[index]
    except KeyError as exc:
        raise ValueError(f"unknown template {template_id!r}") from exc


def template_preview_key(template_id: str) -> str:
    spec = get_template_spec(template_id)
    return f"{PREVIEW_PREFIX}/{spec.id}.png"


async def list_templates_with_previews(*, expires_in: int = 900) -> list[TemplatePreviewSpec]:
    previews: list[TemplatePreviewSpec] = []
    for spec in list_template_specs():
        key = template_preview_key(spec.id)
        preview_url = await anyio.to_thread.run_sync(storage.presigned_get_url, key, expires_in)
        previews.append(
            TemplatePreviewSpec(
                **spec.model_dump(mode="json"),
                preview_png_url=preview_url,
            )
        )
    return previews


def _coerce_font_scale(value: object, spec: TemplateVariableSpec) -> float:
    try:
        scale = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("font_scale must be a number") from exc
    if spec.minimum is not None and scale < spec.minimum:
        raise ValueError(f"font_scale must be >= {spec.minimum:g}")
    if spec.maximum is not None and scale > spec.maximum:
        raise ValueError(f"font_scale must be <= {spec.maximum:g}")
    return round(scale, 3)


def normalize_template_variables(
    template_id: str,
    variables: dict[str, object] | None = None,
) -> dict[str, str | float]:
    spec = get_template_spec(template_id)
    provided = variables or {}
    allowed = set(spec.variables)
    unknown = sorted(set(provided) - allowed)
    if unknown:
        raise ValueError(f"unknown template variable(s): {', '.join(unknown)}")

    normalized: dict[str, str | float] = {}
    for key, variable_spec in spec.variables.items():
        raw_value = provided.get(key, variable_spec.default)
        if key == "accent_color":
            value = str(raw_value)
            if not _COLOR_RE.fullmatch(value):
                raise ValueError("accent_color must be a hex color like #24526b")
            normalized[key] = value.lower()
        elif key == "font_scale":
            normalized[key] = _coerce_font_scale(raw_value, variable_spec)
    return normalized


def render_settings(
    template_id: str,
    variables: dict[str, object] | None = None,
) -> TemplateRenderSettings:
    spec = get_template_spec(template_id)
    normalized = normalize_template_variables(spec.id, variables)
    accent_color = str(normalized["accent_color"])
    font_scale = float(normalized["font_scale"])

    if spec.id == "compact":
        return TemplateRenderSettings(
            template_id=spec.id,
            accent_color=accent_color,
            font_scale=font_scale,
            font_stack='Aptos, Calibri, "Helvetica Neue", Arial, sans-serif',
            heading_font_stack='Aptos Display, Aptos, Calibri, "Helvetica Neue", Arial, sans-serif',
            contact_font_stack='Aptos, Calibri, "Helvetica Neue", Arial, sans-serif',
            docx_body_font="Aptos",
            docx_heading_font="Aptos Display",
            docx_contact_font="Aptos",
            pdf_font_attempts=tuple(value * font_scale for value in (10.0, 9.5, 9.0)),
            margin_in=0.62,
            docx_body_size=9.8 * font_scale,
            docx_heading_size=11.0 * font_scale,
            docx_subheading_size=10.0 * font_scale,
            docx_contact_size=8.6 * font_scale,
            docx_line_spacing=1.0,
            docx_section_before=5,
            docx_heading_after=2,
            docx_bullet_after=1,
        )

    if spec.id == "modern":
        return TemplateRenderSettings(
            template_id=spec.id,
            accent_color=accent_color,
            font_scale=font_scale,
            font_stack='Inter, Aptos, Calibri, "Helvetica Neue", Arial, sans-serif',
            heading_font_stack='Inter, Aptos Display, Aptos, Calibri, "Helvetica Neue", Arial, sans-serif',
            contact_font_stack='Inter, Aptos, Calibri, "Helvetica Neue", Arial, sans-serif',
            docx_body_font="Aptos",
            docx_heading_font="Aptos Display",
            docx_contact_font="Aptos",
            pdf_font_attempts=tuple(value * font_scale for value in (11.0, 10.5, 10.0)),
            margin_in=0.7,
            docx_body_size=10.5 * font_scale,
            docx_heading_size=12.4 * font_scale,
            docx_subheading_size=10.7 * font_scale,
            docx_contact_size=9.0 * font_scale,
            docx_line_spacing=1.05,
            docx_section_before=8,
            docx_heading_after=3,
            docx_bullet_after=2,
        )

    if spec.id == "mono":
        return TemplateRenderSettings(
            template_id=spec.id,
            accent_color=accent_color,
            font_scale=font_scale,
            font_stack='Aptos, Calibri, "Helvetica Neue", Arial, sans-serif',
            heading_font_stack='"SF Mono", "Cascadia Mono", Consolas, "Liberation Mono", Menlo, monospace',
            contact_font_stack='"SF Mono", "Cascadia Mono", Consolas, "Liberation Mono", Menlo, monospace',
            docx_body_font="Aptos",
            docx_heading_font="Consolas",
            docx_contact_font="Consolas",
            pdf_font_attempts=tuple(value * font_scale for value in (10.8, 10.3, 9.8)),
            margin_in=0.72,
            docx_body_size=10.4 * font_scale,
            docx_heading_size=11.4 * font_scale,
            docx_subheading_size=10.4 * font_scale,
            docx_contact_size=8.8 * font_scale,
            docx_line_spacing=1.05,
            docx_section_before=8,
            docx_heading_after=3,
            docx_bullet_after=2,
        )

    return TemplateRenderSettings(
        template_id=spec.id,
        accent_color=accent_color,
        font_scale=font_scale,
        font_stack='Aptos, Calibri, "Helvetica Neue", Arial, sans-serif',
        heading_font_stack='Aptos Display, Aptos, Calibri, "Helvetica Neue", Arial, sans-serif',
        contact_font_stack='Aptos, Calibri, "Helvetica Neue", Arial, sans-serif',
        docx_body_font="Aptos",
        docx_heading_font="Aptos Display",
        docx_contact_font="Aptos",
        pdf_font_attempts=tuple(value * font_scale for value in (11.0, 10.5, 10.0)),
        margin_in=0.7,
        docx_body_size=10.5 * font_scale,
        docx_heading_size=12.0 * font_scale,
        docx_subheading_size=10.5 * font_scale,
        docx_contact_size=9.0 * font_scale,
        docx_line_spacing=1.05,
        docx_section_before=8,
        docx_heading_after=3,
        docx_bullet_after=2,
    )
