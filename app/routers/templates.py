from fastapi import APIRouter

from app.services import templates as template_service

router = APIRouter(tags=["templates"])


@router.get("/templates")
async def list_templates() -> list[template_service.TemplatePreviewSpec]:
    return await template_service.list_templates_with_previews()
