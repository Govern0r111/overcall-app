from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from overcall.config import Settings
from overcall.main import create_app


@pytest.fixture
def api_settings() -> Settings:
    return Settings(app_env="test", database_url=None, release="test")


@pytest.fixture
def client(api_settings: Settings) -> TestClient:
    with TestClient(create_app(api_settings)) as test_client:
        yield test_client
