"""Shared fixtures for the Noesis integration suite.

Each deployed service is exposed by two env vars::

    NOESIS_<SERVICE>_URL     — public Railway origin, no trailing slash
    NOESIS_<SERVICE>_SECRET  — bearer token (optional; required if the
                               service was deployed with <SERVICE>_SECRET set)

Any test that needs a service gets a fixture (e.g. ``mneme_url``) which
skips the test when the URL is unset. Bearer secrets are supplied by the
matching ``_secret`` fixture (empty string if unset) and baked into the
``mcp_session`` / ``http`` helpers.

A local ``eval/.env.e2e`` file is auto-loaded if present. See
``eval/.env.e2e.example`` for the template.
"""
from __future__ import annotations

import os
from pathlib import Path

import httpx
import pytest

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover — optional dep
    load_dotenv = None


_ENV_PATH = Path(__file__).resolve().parents[1] / ".env.e2e"
if load_dotenv is not None and _ENV_PATH.exists():
    load_dotenv(_ENV_PATH, override=False)


SERVICES = (
    "mneme", "telos", "praxis", "logos",
    "episteme", "empiria", "techne", "kosmos",
)


def _service_url(name: str) -> str:
    env_var = f"NOESIS_{name.upper()}_URL"
    url = os.getenv(env_var)
    if not url:
        pytest.skip(f"{env_var} not set — skipping integration test")
    return url.rstrip("/")


def _service_secret(name: str) -> str:
    return os.getenv(f"NOESIS_{name.upper()}_SECRET", "")


# ── URL fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def mneme_url() -> str:
    return _service_url("mneme")


@pytest.fixture
def telos_url() -> str:
    return _service_url("telos")


@pytest.fixture
def praxis_url() -> str:
    return _service_url("praxis")


@pytest.fixture
def logos_url() -> str:
    return _service_url("logos")


@pytest.fixture
def episteme_url() -> str:
    return _service_url("episteme")


@pytest.fixture
def empiria_url() -> str:
    return _service_url("empiria")


@pytest.fixture
def techne_url() -> str:
    return _service_url("techne")


@pytest.fixture
def kosmos_url() -> str:
    return _service_url("kosmos")


# ── Secret fixtures ───────────────────────────────────────────────────────────

@pytest.fixture
def mneme_secret() -> str:
    return _service_secret("mneme")


@pytest.fixture
def telos_secret() -> str:
    return _service_secret("telos")


@pytest.fixture
def praxis_secret() -> str:
    return _service_secret("praxis")


@pytest.fixture
def logos_secret() -> str:
    return _service_secret("logos")


@pytest.fixture
def episteme_secret() -> str:
    return _service_secret("episteme")


@pytest.fixture
def empiria_secret() -> str:
    return _service_secret("empiria")


@pytest.fixture
def techne_secret() -> str:
    return _service_secret("techne")


@pytest.fixture
def kosmos_secret() -> str:
    return _service_secret("kosmos")


# ── HTTP client ───────────────────────────────────────────────────────────────

@pytest.fixture
def http() -> httpx.Client:
    return httpx.Client(timeout=30.0)
