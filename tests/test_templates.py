from pathlib import Path
from typing import Any

from httpx import AsyncClient

from app.services import templates as template_service
from scripts import make_template_previews


async def test_templates_endpoint_lists_four_templates(
    client: AsyncClient,
    monkeypatch: Any,
) -> None:
    def fake_presigned_get_url(key: str, expires_in: int = 900) -> str:
        return f"https://storage.example.test/{key}?expires={expires_in}"

    monkeypatch.setattr(template_service.storage, "presigned_get_url", fake_presigned_get_url)

    response = await client.get("/templates")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert [item["id"] for item in payload] == ["classic", "compact", "modern", "mono"]
    assert all(item["preview_png_url"].endswith("?expires=900") for item in payload)
    assert all(set(item["variables"]) == {"accent_color", "font_scale"} for item in payload)


def test_preview_script_produces_four_pngs(tmp_path: Path, monkeypatch: Any) -> None:
    uploaded: dict[str, bytes] = {}

    def fake_put_object(key: str, body: bytes, content_type: str) -> None:
        uploaded[key] = body
        assert content_type == "image/png"

    monkeypatch.setattr(make_template_previews.storage, "put_object", fake_put_object)

    previews = make_template_previews.generate_previews(output_dir=tmp_path, upload=True)

    assert sorted(previews) == ["classic", "compact", "modern", "mono"]
    assert sorted(uploaded) == [
        "template-previews/classic.png",
        "template-previews/compact.png",
        "template-previews/modern.png",
        "template-previews/mono.png",
    ]
    for template_id, png in previews.items():
        assert png.startswith(b"\x89PNG\r\n\x1a\n")
        assert (tmp_path / f"{template_id}.png").read_bytes() == png
