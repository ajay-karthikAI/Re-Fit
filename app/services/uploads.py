import uuid

import anyio.to_thread
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Upload
from app.schemas.parse import ParseResult
from app.schemas.upload import UploadResult
from app.services import storage
from app.services.errors import NotFoundError
from app.services.extract import extract_text
from app.services.parser import parse_resume
from app.services.profiles import upsert_canonical_profile
from app.services.users import get_user


async def create_upload(
    session: AsyncSession, user_id: uuid.UUID, file: UploadFile
) -> UploadResult:
    await get_user(session, user_id)

    filename = file.filename or "upload"
    file_bytes = await file.read()
    # Extract first: invalid/oversized files are rejected before we touch S3.
    extracted = extract_text(file_bytes, filename)

    s3_key = f"uploads/{user_id}/{uuid.uuid4()}/{filename}"
    content_type = file.content_type or "application/octet-stream"
    await anyio.to_thread.run_sync(storage.put_object, s3_key, file_bytes, content_type)

    upload = Upload(
        user_id=user_id,
        s3_key=s3_key,
        filename=filename,
        source_format=extracted.source_format,
    )
    session.add(upload)
    await session.commit()
    await session.refresh(upload)

    return UploadResult(
        upload_id=upload.id,
        filename=upload.filename,
        s3_key=upload.s3_key,
        source_format=extracted.source_format,
        created_at=upload.created_at,
        extracted=extracted,
    )


async def parse_upload(
    session: AsyncSession, upload_id: uuid.UUID, model: str | None = None
) -> ParseResult:
    """Run LLM normalization on an upload and store the result as the user's
    canonical profile."""
    upload = await session.get(Upload, upload_id)
    if upload is None:
        raise NotFoundError(f"upload {upload_id} not found")

    file_bytes = await anyio.to_thread.run_sync(storage.get_object, upload.s3_key)
    extracted = extract_text(file_bytes, upload.filename)
    result = await parse_resume(extracted, model=model)
    await upsert_canonical_profile(session, upload.user_id, result.resume)
    return result
