from pydantic import SecretStr, ValidationError

from overcall.config import Settings


def test_secret_values_are_masked_in_repr() -> None:
    settings = Settings(
        app_env="test",
        ingest_key_pepper=SecretStr("x" * 40),
        internal_token=SecretStr("y" * 40),
    )

    assert "x" * 40 not in repr(settings)
    assert "y" * 40 not in repr(settings)


def test_production_fails_fast_when_required_secrets_are_missing() -> None:
    try:
        Settings(app_env="production")
    except ValidationError as exc:
        assert "DATABASE_URL" in str(exc)
        assert "SUPABASE_URL" in str(exc)
        assert "INGEST_KEY_PEPPER" in str(exc)
        assert "INTERNAL_TOKEN" in str(exc)
    else:
        raise AssertionError("Production settings accepted missing secrets")


def test_wildcard_cors_is_rejected() -> None:
    try:
        Settings(app_env="test", cors_origins="*")
    except ValidationError as exc:
        assert "wildcard CORS" in str(exc)
    else:
        raise AssertionError("Wildcard CORS origin was accepted")


def test_remote_database_requires_ssl_but_local_development_does_not() -> None:
    local = Settings(
        app_env="development",
        database_url="postgresql+asyncpg://overcall:overcall@localhost:54329/overcall",
    )
    remote = Settings(
        app_env="development",
        database_url="postgresql+asyncpg://user:password@db.example.test:5432/overcall",
    )

    assert local.database_ssl is False
    assert remote.database_ssl is True
