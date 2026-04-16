import os
import pytest
import httpx


def service_url(name: str) -> str:
    env_var = f"NOESIS_{name.upper()}_URL"
    url = os.getenv(env_var)
    if not url:
        pytest.skip(f"{env_var} not set — skipping integration test")
    return url


@pytest.fixture
def mneme_url() -> str:
    return service_url("mneme")


@pytest.fixture
def praxis_url() -> str:
    return service_url("praxis")


@pytest.fixture
def telos_url() -> str:
    return service_url("telos")


@pytest.fixture
def logos_url() -> str:
    return service_url("logos")


@pytest.fixture
def episteme_url() -> str:
    return service_url("episteme")


@pytest.fixture
def http() -> httpx.Client:
    return httpx.Client(timeout=30.0)
