"""Direct tests for logos.__main__."""

from __future__ import annotations

import runpy
import sys

import pytest


def test___main___passes_argv_to_cli_main(monkeypatch):
    received: list[str] = []

    def _fake_main(argv: list[str]) -> int:
        received.extend(argv)
        return 0

    monkeypatch.setattr("logos.cli.main", _fake_main)
    monkeypatch.setattr(sys, "argv", ["logos", "P -> Q, P |- Q"])

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_module("logos", run_name="__main__")

    assert exc_info.value.code == 0
    assert received == ["P -> Q, P |- Q"]
