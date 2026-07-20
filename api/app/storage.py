from __future__ import annotations

import os
from pathlib import Path
from tempfile import NamedTemporaryFile


def _s3():
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=os.getenv("S3_ENDPOINT") or None,
        aws_access_key_id=os.getenv("S3_ACCESS_KEY"),
        aws_secret_access_key=os.getenv("S3_SECRET_KEY"),
        region_name=os.getenv("AWS_REGION", "us-east-1"),
    )


def _enabled() -> bool:
    return os.getenv("STORAGE_MODE", "local").lower() == "s3"


def store_object(storage_key: str, payload: bytes, local_root: Path) -> None:
    if not _enabled():
        target = local_root / storage_key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        return
    client = _s3()
    bucket = os.getenv("S3_BUCKET", "docuguardian")
    try:
        client.head_bucket(Bucket=bucket)
    except Exception:
        client.create_bucket(Bucket=bucket)
    client.put_object(Bucket=bucket, Key=storage_key, Body=payload)


def materialize_object(storage_key: str, local_root: Path) -> Path:
    if not _enabled():
        return local_root / storage_key
    temporary = NamedTemporaryFile(prefix="docuguardian-", suffix=Path(storage_key).suffix, delete=False)
    temporary.close()
    _s3().download_file(os.getenv("S3_BUCKET", "docuguardian"), storage_key, temporary.name)
    return Path(temporary.name)


def delete_object(storage_key: str, local_root: Path) -> None:
    if not _enabled():
        (local_root / storage_key).unlink(missing_ok=True)
        return
    _s3().delete_object(Bucket=os.getenv("S3_BUCKET", "docuguardian"), Key=storage_key)
