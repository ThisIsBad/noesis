from __future__ import annotations

import io
import json
import socket
import threading
import time
from pathlib import Path

import pytest

from theoria.cli import main
from theoria.models import DecisionTrace, ReasoningStep, StepKind
from theoria.server import make_server
from theoria.store import TraceStore


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def running_server():
    store = TraceStore()
    port = _free_port()
    server, _ = make_server(host="127.0.0.1", port=port, store=store)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.05)
    # Preload samples for list/export/diff tests.
    store.put_many(
        [
            _make_trace(
                "t-one", source="logos", kind="policy", verdict="block", title="Block delete", tags=["policy", "block"]
            ),
            _make_trace(
                "t-two",
                source="praxis",
                kind="plan",
                verdict="plan-selected",
                title="Dual-write migration",
                tags=["plan"],
            ),
        ]
    )
    base = f"http://127.0.0.1:{port}"
    try:
        yield base, store
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)


def _make_trace(trace_id: str, **kw) -> DecisionTrace:
    from theoria.models import Outcome

    return DecisionTrace(
        id=trace_id,
        title=kw.get("title", trace_id),
        question="?",
        source=kw.get("source", "test"),
        kind=kw.get("kind", "custom"),
        root="q",
        steps=[ReasoningStep(id="q", kind=StepKind.QUESTION, label="Q")],
        outcome=Outcome(verdict=kw.get("verdict", "allow"), summary="") if "verdict" in kw else None,
        tags=kw.get("tags", []),
    )


def test_no_args_and_flag_only_default_to_serve() -> None:
    """Back-compat: `theoria` and `theoria --port 1234` should map to serve.

    We don't actually run serve here — just check the parser routing.
    """
    from theoria.cli import _build_parser

    def _route(argv: list[str]) -> str:
        raw = list(argv)
        from theoria.cli import _COMMANDS

        if not raw or raw[0] not in _COMMANDS:
            if not raw or raw[0].startswith("-"):
                raw = ["serve", *raw]
        args = _build_parser().parse_args(raw)
        return args.command or "serve"

    assert _route([]) == "serve"
    assert _route(["--port", "1234"]) == "serve"
    assert _route(["--host", "0.0.0.0", "--port", "9000"]) == "serve"
    assert _route(["list"]) == "list"


def test_sample_subcommand_emits_json(capsys) -> None:
    rc = main(["sample", "--index", "0"])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    assert "id" in payload and "steps" in payload


def test_list_subcommand_table_format(running_server, capsys) -> None:
    base, _ = running_server
    rc = main(["list", "--url", base])
    out = capsys.readouterr().out
    assert rc == 0
    assert "t-one" in out and "t-two" in out
    assert "logos" in out
    assert "praxis" in out


def test_list_subcommand_with_filter(running_server, capsys) -> None:
    base, _ = running_server
    rc = main(["list", "--url", base, "--source", "logos", "--format", "ids"])
    out = capsys.readouterr().out
    assert rc == 0
    assert out.strip() == "t-one"


def test_list_subcommand_json_format(running_server, capsys) -> None:
    base, _ = running_server
    rc = main(["list", "--url", base, "--format", "json"])
    out = capsys.readouterr().out
    assert rc == 0
    data = json.loads(out)
    assert isinstance(data, list) and len(data) == 2


def test_post_subcommand_round_trip(running_server, capsys, tmp_path: Path) -> None:
    base, store = running_server
    trace = _make_trace("from-cli", source="custom")
    path = tmp_path / "trace.json"
    path.write_text(json.dumps(trace.to_dict()), encoding="utf-8")

    rc = main(["post", str(path), "--url", base])
    out = capsys.readouterr().out
    assert rc == 0
    assert "→ 201" in out
    assert store.get("from-cli") is not None


def test_post_subcommand_reads_stdin(running_server, capsys, monkeypatch) -> None:
    base, store = running_server
    trace = _make_trace("from-stdin", source="custom")
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(trace.to_dict())))
    rc = main(["post", "-", "--url", base])
    capsys.readouterr()
    assert rc == 0
    assert store.get("from-stdin") is not None


def test_export_subcommand_markdown(running_server, capsys) -> None:
    base, _ = running_server
    rc = main(["export", "--id", "t-one", "--format", "markdown", "--url", base])
    out = capsys.readouterr().out
    assert rc == 0
    assert out.startswith("# ")


def test_export_subcommand_json(running_server, capsys) -> None:
    base, _ = running_server
    rc = main(["export", "--id", "t-one", "--format", "json", "--url", base])
    out = capsys.readouterr().out
    assert rc == 0
    data = json.loads(out)
    assert data["id"] == "t-one"


def test_export_subcommand_handles_404(running_server, capsys) -> None:
    base, _ = running_server
    rc = main(["export", "--id", "does-not-exist", "--format", "json", "--url", base])
    err = capsys.readouterr().err
    assert rc == 1
    assert "HTTP 404" in err


def test_diff_subcommand_markdown(running_server, capsys) -> None:
    base, _ = running_server
    rc = main(["diff", "t-one", "t-two", "--format", "markdown", "--url", base])
    out = capsys.readouterr().out
    assert rc == 0
    assert out.startswith("# Trace diff")


def test_diff_subcommand_json(running_server, capsys) -> None:
    base, _ = running_server
    rc = main(["diff", "t-one", "t-two", "--format", "json", "--url", base])
    out = capsys.readouterr().out
    assert rc == 0
    data = json.loads(out)
    assert data["a_id"] == "t-one" and data["b_id"] == "t-two"


def test_tail_subcommand_connection_error_exits_nonzero(capsys) -> None:
    # Point at an unused port — should fail cleanly rather than hang.
    port = _free_port()
    rc = main(["tail", "--url", f"http://127.0.0.1:{port}"])
    err = capsys.readouterr().err
    assert rc == 1
    assert "could not connect" in err
