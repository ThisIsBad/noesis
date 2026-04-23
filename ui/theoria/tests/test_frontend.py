"""Playwright smoke tests for the browser UI.

Skipped automatically when Playwright is not installed or its
Chromium binary is missing — both common in lean CI / dev setups.
Full local setup::

    pip install playwright
    playwright install chromium

Covers the three things a human would actually verify by eye:
    1. The page loads and renders the expected chrome.
    2. "Load samples" populates the trace list via SSE / refresh.
    3. Clicking a trace in the list renders an SVG reasoning graph
       and the details panel on node click.
"""

from __future__ import annotations

import socket
import threading
import time

import pytest

playwright = pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright  # noqa: E402

from theoria.samples import build_samples  # noqa: E402
from theoria.server import make_server  # noqa: E402
from theoria.store import TraceStore  # noqa: E402


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def browser():
    try:
        with sync_playwright() as pw:
            try:
                browser = pw.chromium.launch()
            except Exception as exc:
                pytest.skip(f"Chromium unavailable: {exc}")
            try:
                yield browser
            finally:
                browser.close()
    except Exception as exc:  # pragma: no cover - playwright init failures
        pytest.skip(f"Playwright init failed: {exc}")


@pytest.fixture
def theoria_url():
    store = TraceStore()
    store.put_many(build_samples())
    port = _free_port()
    server, _ = make_server(host="127.0.0.1", port=port, store=store)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.05)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)


def test_page_loads_and_renders_chrome(browser, theoria_url) -> None:
    page = browser.new_page()
    page.goto(theoria_url)
    page.wait_for_selector(".brand-name")
    assert page.locator(".brand-name").text_content() == "Theoria"
    # The toolbar buttons are present.
    assert page.locator("#btn-load-samples").is_visible()
    assert page.locator("#btn-refresh").is_visible()
    page.close()


def test_trace_list_populates_from_samples(browser, theoria_url) -> None:
    page = browser.new_page()
    page.goto(theoria_url)
    # The store is pre-seeded with four samples — the list should show them.
    page.wait_for_selector(".trace-item", timeout=3000)
    count = page.locator(".trace-item").count()
    assert count >= 4
    # Every sample surfaces the expected source/kind tags.
    tags = page.locator(".trace-item .tag").all_text_contents()
    assert any(t == "logos" for t in tags)
    assert any(t == "praxis" for t in tags)
    assert any(t == "telos" for t in tags)
    page.close()


def test_selecting_trace_renders_svg_graph_and_details(browser, theoria_url) -> None:
    page = browser.new_page()
    page.goto(theoria_url)
    page.wait_for_selector(".trace-item", timeout=3000)

    # Click the first trace in the sidebar.
    page.locator(".trace-item").first.click()

    # A graph should render — at least one node group.
    page.wait_for_selector(".node", timeout=3000)
    node_count = page.locator(".node").count()
    assert node_count >= 2

    # Click a node and check the details panel populates.
    page.locator(".node").first.click()
    page.wait_for_selector("#details-body dl", timeout=2000)
    assert "ID" in page.locator("#details-body").text_content()
    page.close()


def test_load_samples_button_is_idempotent(browser, theoria_url) -> None:
    page = browser.new_page()
    page.goto(theoria_url)
    page.wait_for_selector(".trace-item", timeout=3000)
    before = page.locator(".trace-item").count()

    # Clicking "Load samples" re-inserts the same IDs — count should not grow.
    page.locator("#btn-load-samples").click()
    page.wait_for_timeout(200)
    after = page.locator(".trace-item").count()
    assert after == before
    page.close()
