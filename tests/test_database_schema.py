"""Integration checks for the V1 SQL migration.

Set DATABASE_URL to an empty disposable PostgreSQL database to run these tests.
They deliberately leave a rollback-only transaction, so they do not retain test data.
"""
from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PSQL = os.environ.get("PSQL", "psql")
DATABASE_URL = os.environ.get("DATABASE_URL")


@unittest.skipUnless(DATABASE_URL, "DATABASE_URL is required for PostgreSQL integration tests")
class SchemaIntegrityTests(unittest.TestCase):
    def psql(self, sql: str, *, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [PSQL, DATABASE_URL, "-X", "-v", "ON_ERROR_STOP=1", "-c", sql],
            text=True, capture_output=True, check=check, cwd=ROOT,
        )

    @classmethod
    def setUpClass(cls) -> None:
        migration = ROOT / "db" / "migrations" / "0001_v1_schema.sql"
        subprocess.run([PSQL, DATABASE_URL, "-X", "-v", "ON_ERROR_STOP=1", "-f", str(migration)], check=True, cwd=ROOT)
        integrity = ROOT / "db" / "migrations" / "0002_attempt_integrity.sql"
        subprocess.run([PSQL, DATABASE_URL, "-X", "-v", "ON_ERROR_STOP=1", "-f", str(integrity)], check=True, cwd=ROOT)
        seed = ROOT / "db" / "seeds" / "001_v1_example.sql"
        subprocess.run([PSQL, DATABASE_URL, "-X", "-v", "ON_ERROR_STOP=1", "-f", str(seed)], check=True, cwd=ROOT)

    def test_seed_loads_and_core_tables_exist(self) -> None:
        result = self.psql("SELECT count(*) FROM users;")
        self.assertIn("2", result.stdout)

    def test_constraints_reject_invalid_data(self) -> None:
        # A confidence outside [0,1] must fail at the database boundary.
        sql = """
        INSERT INTO skill_profiles (user_id, skill, estimated_level, confidence, model_version, last_evidence_at)
        VALUES ('10000000-0000-0000-0000-000000000001', 'fluency', 50, 1.1, 'test', now());
        """
        result = self.psql(sql, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("skill_profiles_confidence_check", result.stderr)

    def test_attempt_ordinal_and_recording_cardinality(self) -> None:
        invalid_retry = """
        INSERT INTO challenge_attempts (user_id, assignment_id, comparison_group_id, ordinal)
        VALUES ('10000000-0000-0000-0000-000000000001', '50000000-0000-0000-0000-000000000001', gen_random_uuid(), 2);
        """
        self.assertNotEqual(self.psql(invalid_retry, check=False).returncode, 0)
        duplicate_raw = """
        INSERT INTO recordings (attempt_id, kind, storage_provider, object_key, checksum_sha256, content_type, byte_size, duration_ms)
        VALUES ('60000000-0000-0000-0000-000000000001', 'raw', 's3', 'private/example.webm', repeat('a', 64), 'audio/webm', 10, 10),
               ('60000000-0000-0000-0000-000000000001', 'raw', 's3', 'private/example-2.webm', repeat('b', 64), 'audio/webm', 10, 10);
        """
        self.assertNotEqual(self.psql(duplicate_raw, check=False).returncode, 0)
