"""End-to-end tests for LM Studio category installs (issue #19).

Runs a real HTTP server on a real socket that speaks the LM Studio endpoints
involved in a category install — ``/v1/models``, ``/api/v1/models/download``
and its status poll — and drives it through ``ModelManager`` with no transport
mocking. The point is to prove the curated mapping produces identifiers the
adapter actually pulls, end to end, rather than Ollama tags the server would
reject.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Iterator, List, Set, Tuple

import pytest

from modeldock.common.config import Settings
from modeldock.core.manager import ModelManager
from modeldock.domain.model import Category, ModelRef, RuntimeBackend

pytestmark = pytest.mark.e2e

#: Model IDs the fake server accepts downloads for; populated per test.
_DOWNLOADED: Set[str] = set()
_REQUESTED: List[str] = []


class _LMStudioHandler(BaseHTTPRequestHandler):
    """Stand-in for LM Studio: serves installed models and accepts downloads."""

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if self.path == "/v1/models":
            self._json(
                200,
                {
                    "object": "list",
                    "data": [{"id": m, "object": "model"} for m in sorted(_DOWNLOADED)],
                },
            )
        elif self.path == "/api/v1/models/download/status":
            self._json(200, {"status": "completed"})
        else:
            self._json(404, {})

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length) or b"{}")
        if self.path == "/api/v1/models/download":
            model = str(payload.get("model", ""))
            _REQUESTED.append(model)
            # LM Studio is addressed by "publisher/repo"; a bare Ollama tag is
            # not something it can resolve, so reject it the way the real
            # server would.
            if "/" not in model:
                self._json(404, {"error": f"unknown model {model}"})
                return
            _DOWNLOADED.add(model.split(":")[0])
            self._json(200, {"status": "started"})
        else:
            self._json(404, {})

    def log_message(self, *args: object) -> None:
        """Silence the default stderr access log."""


@pytest.fixture()
def live_server(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    _DOWNLOADED.clear()
    _REQUESTED.clear()
    server = HTTPServer(("127.0.0.1", 0), _LMStudioHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host = f"http://127.0.0.1:{server.server_address[1]}"
    # Point the adapter at the test server the way a user would. (A first-class
    # `lmstudio_host` setting arrives with issue #18; this branch uses the
    # environment variable the adapter already honors.)
    monkeypatch.setenv("LM_STUDIO_HOST", host)
    try:
        yield host
    finally:
        server.shutdown()
        server.server_close()


def _manager(host: str) -> ModelManager:
    return ModelManager(
        backend=RuntimeBackend.LM_STUDIO,
        settings=Settings(catalog_source="bundled", progress_style="silent"),
    )


def _split(model_id: str) -> Tuple[str, str]:
    publisher, _, repo = model_id.partition("/")
    return publisher, repo


# --- suggestions are backend-native ----------------------------------------


def test_suggestions_are_lmstudio_ids_not_ollama_tags(live_server: str) -> None:
    """The bundled catalog would offer 'qwen2.5-coder'; LM Studio needs the HF id."""
    manager = _manager(live_server)

    names = [ref.name for ref in manager.suggest_category("coding")]

    assert names, "no coding suggestions for LM Studio"
    assert all("/" in name for name in names)
    assert "qwen2.5-coder" not in names  # the Ollama tag from the shared catalog


@pytest.mark.parametrize("category", [c.value for c in Category])
def test_every_category_suggests_installable_ids(live_server: str, category: str) -> None:
    for ref in _manager(live_server).suggest_category(category):
        publisher, repo = _split(ref.name)
        assert publisher and repo


# --- installing against the live server ------------------------------------


def test_install_category_downloads_through_the_server(live_server: str) -> None:
    manager = _manager(live_server)

    refs = manager.install_category("embedding")

    assert refs
    # Every suggestion was actually requested from the server...
    assert _REQUESTED, "no download request reached the server"
    assert all("/" in requested for requested in _REQUESTED)
    # ...and the server rejected none of them.
    assert {ref.name for ref in refs} <= _DOWNLOADED


def test_installed_models_are_visible_afterwards(live_server: str) -> None:
    manager = _manager(live_server)
    installed_before = manager.installed()
    assert installed_before == []

    manager.install_category("embedding")

    names = {ref.name for ref in manager.installed()}
    assert names == {ref.name for ref in manager.suggest_category("embedding")}


def test_installed_models_report_as_installed(live_server: str) -> None:
    manager = _manager(live_server)
    manager.install_category("embedding")

    for ref in manager.suggest_category("embedding"):
        assert manager.verify(ref.name) is True


def test_reinstall_is_idempotent(live_server: str) -> None:
    """Second run finds them present and does not re-request a download."""
    manager = _manager(live_server)
    manager.install_category("embedding")
    requests_after_first = len(_REQUESTED)

    manager.install_category("embedding")

    assert len(_REQUESTED) == requests_after_first


def test_ollama_tag_would_have_been_rejected(live_server: str) -> None:
    """Guards the premise: the pre-fix behavior really does fail on LM Studio."""
    manager = _manager(live_server)

    ollama_style_name = ModelRef.parse("qwen2.5-coder", backend=RuntimeBackend.LM_STUDIO)

    result = manager._runtime.pull(ollama_style_name)

    assert result.success is False
    assert "qwen2.5-coder" in _REQUESTED[-1]
