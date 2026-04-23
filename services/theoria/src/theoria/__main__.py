"""CLI entry point: ``python -m theoria``."""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

from theoria.server import serve
from theoria.store import TraceStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="theoria",
        description="Decision-logic visualization server for the Noesis ecosystem.",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("THEORIA_HOST", "127.0.0.1"),
        help="Bind host (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("THEORIA_PORT", "8765")),
        help="Bind port (default: 8765)",
    )
    parser.add_argument(
        "--persist",
        default=os.environ.get("THEORIA_PERSIST"),
        help="Optional JSONL file for trace persistence",
    )
    parser.add_argument(
        "--no-samples",
        action="store_true",
        help="Do not pre-load the built-in sample traces",
    )
    parser.add_argument(
        "--log-level",
        default=os.environ.get("THEORIA_LOG_LEVEL", "INFO"),
        help="Python logging level (default: INFO)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    persist_path = Path(args.persist) if args.persist else None
    store = TraceStore(persist_path=persist_path)

    serve(
        host=args.host,
        port=args.port,
        store=store,
        load_samples=not args.no_samples,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
