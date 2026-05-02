"""Contract tests for ``noesis_clients.persistence.resolve_sqlite_path``.

Pins the fallback chain and URL parsing so downstream services can
trust the resolution before the T3.5 Postgres migration arrives.
"""

from __future__ import annotations

import pytest

from noesis_clients.persistence import (
    UnsupportedDatabaseURL,
    resolve_sqlite_path,
)


def _resolve(**overrides) -> str:
    defaults = {
        "url_env": "SVC_DATABASE_URL",
        "data_dir_env": "SVC_DATA_DIR",
        "default_data_dir": "/data",
        "default_filename": "svc.db",
    }
    defaults.update(overrides)
    return resolve_sqlite_path(**defaults)


def test_url_absolute_sqlite_path(monkeypatch):
    """Four-slash SQLite URL → absolute POSIX path."""
    monkeypatch.setenv("SVC_DATABASE_URL", "sqlite:////data/mneme.db")
    assert _resolve() == "/data/mneme.db"


def test_url_relative_sqlite_path(monkeypatch):
    """Three-slash SQLite URL → relative path."""
    monkeypatch.setenv("SVC_DATABASE_URL", "sqlite:///tmp/test.db")
    assert _resolve() == "tmp/test.db"


def test_unsupported_scheme_raises(monkeypatch):
    monkeypatch.setenv("SVC_DATABASE_URL", "postgresql://user:pw@host/db")
    with pytest.raises(UnsupportedDatabaseURL, match="sqlite:///"):
        _resolve()


def test_empty_url_falls_back_to_data_dir(monkeypatch):
    monkeypatch.delenv("SVC_DATABASE_URL", raising=False)
    monkeypatch.setenv("SVC_DATA_DIR", "/custom/dir")
    assert _resolve() == "/custom/dir/svc.db"


def test_whitespace_url_treated_as_empty(monkeypatch):
    """A stray whitespace-only value shouldn't trigger URL parsing."""
    monkeypatch.setenv("SVC_DATABASE_URL", "   ")
    monkeypatch.setenv("SVC_DATA_DIR", "/somewhere")
    assert _resolve() == "/somewhere/svc.db"


def test_neither_var_set_uses_defaults(monkeypatch):
    monkeypatch.delenv("SVC_DATABASE_URL", raising=False)
    monkeypatch.delenv("SVC_DATA_DIR", raising=False)
    assert _resolve() == "/data/svc.db"


def test_url_takes_precedence_over_data_dir(monkeypatch):
    """When both are set, the URL wins — that's the migration path."""
    monkeypatch.setenv("SVC_DATABASE_URL", "sqlite:////override/path.db")
    monkeypatch.setenv("SVC_DATA_DIR", "/legacy/dir")
    assert _resolve() == "/override/path.db"


def test_custom_default_filename(monkeypatch):
    monkeypatch.delenv("SVC_DATABASE_URL", raising=False)
    monkeypatch.setenv("SVC_DATA_DIR", "/d")
    assert _resolve(default_filename="other.db") == "/d/other.db"
