"""Route Mneme persistent storage into a pytest tmp dir.

``mneme.mcp_server_http`` does ``os.makedirs(MNEME_DATA_DIR, exist_ok=True)``
and instantiates ``MnemeCore`` (SQLite + ChromaDB) at import time. The default
is ``/data`` which is not writable in CI, so importing the module from a
test (``test_auth.py``) crashes collection with ``PermissionError``.

Setting ``MNEME_DATA_DIR`` in ``pytest_configure`` runs before collection, so
the very first import of ``mneme.mcp_server_http`` sees the writable path.
"""
from __future__ import annotations

import os
import tempfile


def pytest_configure(config: object) -> None:  # noqa: ARG001
    os.environ.setdefault(
        "MNEME_DATA_DIR",
        tempfile.mkdtemp(prefix="mneme-ci-"),
    )
