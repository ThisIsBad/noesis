"""In-process unit tests for logos.cli (coverage for cli.py)."""

from __future__ import annotations

import json

from logos import cli


def test_cli_main_plain_output(capsys):
    code = cli.main(["P -> Q, P |- Q"])
    out = capsys.readouterr().out

    assert code == 0
    assert "valid=True" in out
    assert "rule=Modus Ponens" in out


def test_cli_main_json_parse_error(capsys):
    code = cli.main(["P @ Q |- Q", "--json"])
    out = capsys.readouterr().out

    assert code == 2
    payload = json.loads(out)
    assert payload["error"] == "parse_error"
    assert "message" in payload


def test_result_to_dict_with_explanation_fields():
    result = cli.verify("P -> Q, Q |- P")
    payload = cli._result_to_dict(result, include_explanation=True)

    assert payload["valid"] is False
    assert "explanation" in payload
    assert "counterexample" in payload
