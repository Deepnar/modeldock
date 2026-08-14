"""End-to-end tests for LM Studio server discovery (issue #18).

These run a real HTTP server on a real socket that speaks LM Studio's
OpenAI-compatible ``/v1/models`` endpoint, and drive it through the whole
stack — ``ModelManager`` -> ``RuntimeRegistry`` -> ``LMStudioRuntime`` -> httpx
— with no mocking of the transport. That is what distinguishes them from the
unit tests in ``tests/unit/test_host_resolution.py``.
"""

from __future__ import annotations

import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Iterator, List, Tuple

import pytest

from modeldock.adapters.runtimes.lmstudio import LMStudioRuntime
from modeldock.core.manager import ModelManager
from modeldock.domain.model import ModelRef, RuntimeBackend

pytestmark = pytest.mark.e2e

_MODEL_IDS = ["qwen/qwen3-4b", "lmstudio-community/Meta-Llama-3.1-8B-Instruct-GGUF"]

# The address LM Studio listens on by default, and the one discovery must find
# when "localhost" is not the working spelling.
_DEFAULT_PORT = 1234


class _LMStudioHandler(BaseHTTPRequestHandler):
    """Minimal stand-in for LM Studio's local server."""

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if self.path == "/v1/models":
            body = (
                b'{"object":"list","data":['
                + b",".join(b'{"id":"%s","object":"model"}' % m.encode() for m in _MODEL_IDS)
                + b"]}"
            )
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args: object) -> None:
        """Silence the default stderr access log."""


def _serve(bind: str, port: int) -> Tuple[HTTPServer, int]:
    server = HTTPServer((bind, port), _LMStudioHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, server.server_address[1]


def _port_is_free(bind: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((bind, port))
        except OSError:
            return False
    return True


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("MODELDOCK_LMSTUDIO_HOST", "LM_STUDIO_HOST"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture()
def server_on_ephemeral_port() -> Iterator[str]:
    server, port = _serve("127.0.0.1", 0)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture()
def server_on_default_port() -> Iterator[str]:
    if not _port_is_free("127.0.0.1", _DEFAULT_PORT):
        pytest.skip(f"port {_DEFAULT_PORT} is already in use on this machine")
    server, port = _serve("127.0.0.1", _DEFAULT_PORT)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        server.server_close()


# --- discovery against a live server ---------------------------------------


def test_discovers_live_server_on_default_port(server_on_default_port: str) -> None:
    """With nothing configured, the adapter finds a server on the usual port."""
    runtime = LMStudioRuntime()

    assert runtime._resolve_host().endswith(f":{_DEFAULT_PORT}")
    assert runtime.is_available() is True


def test_lists_models_from_live_server(server_on_default_port: str) -> None:
    refs = LMStudioRuntime().list_installed()

    assert [r.name for r in refs] == _MODEL_IDS
    assert all(r.backend is RuntimeBackend.LM_STUDIO for r in refs)


def test_is_installed_round_trips_against_live_server(server_on_default_port: str) -> None:
    runtime = LMStudioRuntime()

    assert runtime.is_installed(ModelRef.parse("qwen/qwen3-4b")) is True
    assert runtime.is_installed(ModelRef.parse("qwen/not-there")) is False


# --- explicit override -----------------------------------------------------


def test_env_override_reaches_a_nonstandard_port(
    server_on_ephemeral_port: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A server on an arbitrary port is usable purely via configuration."""
    monkeypatch.setenv("MODELDOCK_LMSTUDIO_HOST", server_on_ephemeral_port)
    runtime = LMStudioRuntime()

    assert runtime._resolve_host() == server_on_ephemeral_port
    assert runtime.is_available() is True
    assert [r.name for r in runtime.list_installed()] == _MODEL_IDS


def test_explicit_host_reaches_a_nonstandard_port(server_on_ephemeral_port: str) -> None:
    runtime = LMStudioRuntime(host=server_on_ephemeral_port)

    assert runtime.is_available() is True
    assert [r.name for r in runtime.list_installed()] == _MODEL_IDS


def test_url_with_v1_suffix_is_accepted(server_on_ephemeral_port: str) -> None:
    """The URL LM Studio's UI shows ends in /v1; pasting it must still work."""
    runtime = LMStudioRuntime(host=f"{server_on_ephemeral_port}/v1")

    assert runtime.is_available() is True
    assert [r.name for r in runtime.list_installed()] == _MODEL_IDS


def test_unreachable_host_reports_unavailable_without_raising() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        dead_port = probe.getsockname()[1]

    runtime = LMStudioRuntime(host=f"http://127.0.0.1:{dead_port}")

    assert runtime.is_available() is False
    assert runtime.list_installed() == []


# --- through the full manager stack ----------------------------------------


def test_manager_uses_configured_lmstudio_host(
    server_on_ephemeral_port: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`lmstudio_host` in config reaches the adapter via ModelManager."""
    monkeypatch.setenv("MODELDOCK_CATALOG_SOURCE", "bundled")
    from modeldock.common.config import Settings

    manager = ModelManager(
        backend=RuntimeBackend.LM_STUDIO,
        settings=Settings(lmstudio_host=server_on_ephemeral_port, catalog_source="bundled"),
    )

    names: List[str] = [ref.name for ref in manager.installed()]
    assert names == _MODEL_IDS
    assert manager.runtime_status().available is True


def test_manager_env_host_reaches_adapter(
    server_on_ephemeral_port: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MODELDOCK_LMSTUDIO_HOST", server_on_ephemeral_port)
    monkeypatch.setenv("MODELDOCK_CATALOG_SOURCE", "bundled")

    manager = ModelManager(backend=RuntimeBackend.LM_STUDIO)

    assert [ref.name for ref in manager.installed()] == _MODEL_IDS
