from datetime import timedelta

from app.storage import (
    ObjectMetadata, ObjectStorageProvider, R2ObjectStorageProvider, UploadInstruction,
    sha256_hex_to_s3_base64, sha256_s3_base64_to_hex,
)


class FakeStorage:
    provider_name = "fake"
    def create_upload(self, *, object_key, content_type, max_bytes, checksum_sha256):
        return UploadInstruction("PUT", "https://example.test/upload", object_key, {"Content-Type": content_type}, timedelta(minutes=15))
    def head(self, object_key):
        return ObjectMetadata(object_key, "audio/webm", 10, "a" * 64)
    def delete(self, object_key):
        self.deleted = object_key


def test_object_storage_contract_carries_private_upload_and_metadata():
    storage = FakeStorage()
    assert isinstance(storage, ObjectStorageProvider)
    assert storage.create_upload(object_key="private/u/a/raw.webm", content_type="audio/webm", max_bytes=100, checksum_sha256="a" * 64).method == "PUT"
    assert storage.head("private/u/a/raw.webm").checksum_sha256 == "a" * 64


def test_s3_checksum_encoding_and_r2_head_normalization():
    checksum = "ab" * 32
    encoded = sha256_hex_to_s3_base64(checksum)
    assert encoded == "q6urq6urq6urq6urq6urq6urq6urq6urq6urq6urq6s="
    assert sha256_s3_base64_to_hex(encoded) == checksum
    assert sha256_s3_base64_to_hex("not base64") is None
    assert sha256_s3_base64_to_hex("YQ==") is None


class _R2Client:
    def __init__(self):
        self.presign = None

    def generate_presigned_url(self, operation, *, Params, ExpiresIn, HttpMethod):
        self.presign = (operation, Params, ExpiresIn, HttpMethod)
        return "https://storage.example.test/signed"

    def head_object(self, *, Bucket, Key):
        return {"ContentType": "audio/webm", "ContentLength": 10, "ChecksumSHA256": sha256_hex_to_s3_base64("a" * 64)}


def test_r2_signed_put_binds_checksum_header_and_head_returns_hex():
    adapter = object.__new__(R2ObjectStorageProvider)
    adapter.bucket = "private-recordings"
    adapter.upload_ttl_seconds = 42
    adapter.client = _R2Client()
    instruction = adapter.create_upload(object_key="private/u/a/raw", content_type="audio/webm", max_bytes=100, checksum_sha256="a" * 64)
    assert instruction.headers == {"Content-Type": "audio/webm", "x-amz-checksum-sha256": sha256_hex_to_s3_base64("a" * 64)}
    operation, params, expires_in, method = adapter.client.presign
    assert (operation, expires_in, method) == ("put_object", 42, "PUT")
    assert params["ChecksumSHA256"] == sha256_hex_to_s3_base64("a" * 64)
    assert adapter.head("private/u/a/raw").checksum_sha256 == "a" * 64
