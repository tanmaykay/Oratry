import pytest
from pydantic import ValidationError

from app.core import Settings


def test_non_local_environment_rejects_sqlite():
    with pytest.raises(ValidationError, match="PostgreSQL"):
        Settings(app_environment="production", database_url="sqlite:///./oratry.db", jwt_secret="x" * 32)


def test_non_local_environment_rejects_default_jwt_secret():
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(app_environment="production", database_url="postgresql+psycopg://user:pass@db/oratry")


def test_local_environment_keeps_zero_dependency_configuration():
    settings = Settings(app_environment="local", database_url="sqlite:///./oratry.db")
    assert settings.database_url.startswith("sqlite")
