"""Storage-URL resolution helpers.

Every Noesis service with durable state currently reads a
service-specific ``<SVC>_DATA_DIR`` env var and joins a hardcoded
filename onto it — `/data/mneme.db`, `/data/praxis.db`, and so on.
That works for single-node SQLite on a Railway volume but won't
generalise when we migrate to Postgres / pgvector (Tier-3, T3.5).

This module provides a forward-compatible **SQLAlchemy-style URL
parser** so new code (and later migrations) can read

    <SVC>_DATABASE_URL = sqlite:////data/mneme.db
    <SVC>_DATABASE_URL = postgresql://user:pw@host/db

from one knob, while still falling back to the legacy
``<SVC>_DATA_DIR`` convention where that's what's deployed. When the
flip-the-backend moment arrives, each service swaps one env var; no
code change required.

Usage::

    from noesis_clients.persistence import resolve_sqlite_path

    db_file = resolve_sqlite_path(
        url_env="MNEME_DATABASE_URL",
        data_dir_env="MNEME_DATA_DIR",
        default_data_dir="/data",
        default_filename="mneme.db",
    )

We deliberately only support ``sqlite:///`` in this helper — the
Postgres path will come with its own helper once T3.5 is actually
signed off. Until then, defining the env-var shape in one place
prevents services from drifting into nine different half-conventions.
"""

from __future__ import annotations

import os

SQLITE_SCHEME = "sqlite:///"


class UnsupportedDatabaseURL(ValueError):
    """Raised when a <SVC>_DATABASE_URL uses a scheme we don't yet handle."""


def resolve_sqlite_path(
    *,
    url_env: str,
    data_dir_env: str,
    default_data_dir: str = "/data",
    default_filename: str,
) -> str:
    """Return the filesystem path a service should open with ``sqlite3.connect``.

    Resolution order:

    1. If ``os.environ[url_env]`` is set to ``sqlite:///<path>``, return
       ``<path>``. (SQLAlchemy's four-slash convention means absolute
       POSIX paths look like ``sqlite:////data/mneme.db``; the
       three-slash form gives a relative path.)
    2. If that URL's scheme is anything other than ``sqlite:///``,
       raise ``UnsupportedDatabaseURL`` — the caller is asking for
       something we don't yet know how to open, and silently falling
       back to SQLite would paper over a real config error.
    3. Otherwise, read ``os.environ[data_dir_env]`` (falling back to
       ``default_data_dir``) and join ``default_filename`` onto it.

    This lets a deployment migrate one service at a time: flip the
    ``<SVC>_DATABASE_URL`` env var while leaving ``<SVC>_DATA_DIR``
    untouched, restart, verify, delete the legacy var.
    """
    url = os.environ.get(url_env, "").strip()
    if url:
        if url.startswith(SQLITE_SCHEME):
            # ``sqlite:////abs/path`` → ``/abs/path``
            # ``sqlite:///rel/path`` → ``rel/path``
            return url[len(SQLITE_SCHEME):]
        raise UnsupportedDatabaseURL(
            f"{url_env} uses scheme other than 'sqlite:///'; got {url!r}. "
            "Only SQLite URLs are supported today — Postgres handling "
            "lands with Tier-3 T3.5."
        )
    data_dir = os.environ.get(data_dir_env, default_data_dir)
    return os.path.join(data_dir, default_filename)


__all__ = [
    "SQLITE_SCHEME",
    "UnsupportedDatabaseURL",
    "resolve_sqlite_path",
]
