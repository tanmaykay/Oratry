"""Private object-storage port and Cloudflare R2 S3-compatible adapter."""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Protocol, runtime_checkable


def normalize_sha256_hex(value: str) -> str:
    """Return the one checksum representation persisted by Oratry.

    External S3 APIs represent SHA-256 checksums as base64 while the database
    and browser-facing API use lowercase hexadecimal. Keeping this conversion
    at the storage boundary prevents provider encodings leaking into business
    state.
    """
    normalized = value.lower()
    if len(normalized) != 64 or any(character not in "0123456789abcdef" for character in normalized):
        raise ValueError("checksum must be a lowercase SHA-256 hexadecimal digest")
    return normalized


def sha256_hex_to_s3_base64(value: str) -> str:
    return base64.b64encode(bytes.fromhex(normalize_sha256_hex(value))).decode("ascii")


def sha256_s3_base64_to_hex(value: str) -> str | None:
    """Normalize an S3 ChecksumSHA256 response; reject malformed values."""
    try:
        raw = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        return None
    if len(raw) != 32:
        return None
    return raw.hex()


@dataclass(frozen=True)
class UploadInstruction:
    method: str
    url: str
    object_key: str
    headers: dict[str, str]
    expires_in: timedelta


@dataclass(frozen=True)
class DownloadInstruction:
    """A short-lived private object read instruction for an authenticated owner."""
    url: str
    expires_in: timedelta


@dataclass(frozen=True)
class ObjectMetadata:
    object_key: str
    content_type: str
    byte_size: int
    checksum_sha256: str | None


@runtime_checkable
class ObjectStorageProvider(Protocol):
    provider_name: str

    def create_upload(
        self, *, object_key: str, content_type: str, max_bytes: int, checksum_sha256: str
    ) -> UploadInstruction: ...
    def head(self, object_key: str) -> ObjectMetadata: ...
    def download(self, object_key: str, destination: Path) -> None: ...
    def create_download(self, *, object_key: str) -> DownloadInstruction: ...
    def delete(self, object_key: str) -> None: ...


class R2ObjectStorageProvider:
    """R2 adapter. Objects remain private; presigned URLs are short-lived PUTs."""

    provider_name = "cloudflare-r2"

    def __init__(self, *, endpoint_url: str, bucket: str, access_key_id: str, secret_access_key: str, upload_ttl_seconds: int = 900, download_ttl_seconds: int = 300):
        self.bucket = bucket
        self.upload_ttl_seconds = upload_ttl_seconds
        self.download_ttl_seconds = download_ttl_seconds
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:  # pragma: no cover - dependency installation is runtime-specific
            raise RuntimeError("boto3 is required for the Cloudflare R2 adapter") from exc
        self.client = boto3.client(
            "s3", endpoint_url=endpoint_url, aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key, region_name="auto",
            # The durable worker, not the SDK, owns retries. A single stalled
            # R2 call must not consume the worker lease or hide recovery from
            # the learner for a minute.
            config=Config(connect_timeout=5, read_timeout=10, retries={"max_attempts": 0}),
        )

    def create_upload(self, *, object_key: str, content_type: str, max_bytes: int, checksum_sha256: str) -> UploadInstruction:
        # `content-length-range` cannot be enforced for a single presigned PUT;
        # the API verifies object metadata before enqueueing analysis.
        checksum_header = sha256_hex_to_s3_base64(checksum_sha256)
        url = self.client.generate_presigned_url(
            "put_object", Params={
                "Bucket": self.bucket,
                "Key": object_key,
                "ContentType": content_type,
                # Botocore signs this as x-amz-checksum-sha256. The storage
                # port converts S3's base64 response encoding back to hex.
                "ChecksumSHA256": checksum_header,
            },
            ExpiresIn=self.upload_ttl_seconds, HttpMethod="PUT",
        )
        return UploadInstruction(
            "PUT", url, object_key,
            {"Content-Type": content_type, "x-amz-checksum-sha256": checksum_header},
            timedelta(seconds=self.upload_ttl_seconds),
        )

    def create_download(self, *, object_key: str) -> DownloadInstruction:
        """Issue a short-lived GET only after application authorization."""
        url = self.client.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": object_key},
            ExpiresIn=self.download_ttl_seconds, HttpMethod="GET",
        )
        return DownloadInstruction(url, timedelta(seconds=self.download_ttl_seconds))

    def head(self, object_key: str) -> ObjectMetadata:
        item = self.client.head_object(Bucket=self.bucket, Key=object_key)
        checksum = item.get("ChecksumSHA256")
        return ObjectMetadata(
            object_key,
            item.get("ContentType", "application/octet-stream"),
            int(item["ContentLength"]),
            sha256_s3_base64_to_hex(checksum) if isinstance(checksum, str) else None,
        )

    def delete(self, object_key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=object_key)

    def download(self, object_key: str, destination: Path) -> None:
        """Download a private object for a worker only; never create a public URL."""
        self.client.download_file(self.bucket, object_key, str(destination))
