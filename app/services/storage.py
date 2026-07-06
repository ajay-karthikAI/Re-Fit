"""S3 object storage (MinIO locally). boto3 is sync — call these helpers via
anyio.to_thread.run_sync from async code."""

from functools import lru_cache
from typing import Any

import boto3
from botocore.exceptions import ClientError

from app.config import get_settings


@lru_cache
def _client() -> Any:  # boto3 clients have no importable static type without stubs
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        region_name="us-east-1",
    )


@lru_cache
def _ensure_bucket() -> str:
    """Create the bucket if it doesn't exist yet; cached so we check once per process."""
    bucket = get_settings().s3_bucket
    client = _client()
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError:
        client.create_bucket(Bucket=bucket)
    return bucket


def put_object(key: str, body: bytes, content_type: str) -> None:
    _client().put_object(Bucket=_ensure_bucket(), Key=key, Body=body, ContentType=content_type)


def get_object(key: str) -> bytes:
    response = _client().get_object(Bucket=_ensure_bucket(), Key=key)
    return response["Body"].read()


def presigned_get_url(key: str, expires_in: int = 900) -> str:
    return _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": _ensure_bucket(), "Key": key},
        ExpiresIn=expires_in,
    )
