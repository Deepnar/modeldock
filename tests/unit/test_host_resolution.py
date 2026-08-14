"""Unit tests for shared runtime host resolution (issue #18).

Covers the precedence chain, normalization, and auto-discovery in
``BaseRuntime.resolve_host``, plus the LM Studio and Ollama adapters that use it.
"""

from __future__ import annotations

from typing import Any, List, Optional

import pytest

from modeldock.adapters.runtimes.base import BaseRuntime, normalize_host
from modeldock.adapters.runtimes.lmstudio import LMStudioRuntime
from modeldock.adapters.runtimes.ollama import OllamaRuntime
from modeldock.domain.model import RuntimeBackend

_LMS_ENV = ("MODELDOCK_LMSTUDIO_HOST", "LM_STUDIO_HOST")


@pytest.fixture(autouse=True)
def _clear_host_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never let the developer's own environment steer these tests."""
    for name in (*_LMS_ENV, "MODELDOCK_OLLAMA_HOST", "OLLAMA_HOST"):
        monkeypatch.delenv(name, raising=False)


class _ProbeRecorder:
    """Stands in for httpx.get, answering 200 only for allowed base URLs."""

    def __init__(self, reachable: Optional[List[str]] = None) -> None:
        self.reachable = reachable or []
        self.probed: List[str] = []

    def __call__(self, url: str, timeout: float = 0.0) -> Any:
        self.probed.append(url)
        for base in self.reachable:
            if url.startswith(base):
                return type("R", (), {"status_code": 200})()
        raise OSError("connection refused")


@pytest.fixture()
def probe(monkeypatch: pytest.MonkeyPatch):
    def _install(reachable: Optional[List[str]] = None) -> _ProbeRecorder:
        recorder = _ProbeRecorder(reachable)
        monkeypatch.setattr("httpx.get", recorder)
        return recorder

    return _install


# --- normalize_host --------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("http://localhost:1234", "http://localhost:1234"),
        ("http://localhost:1234/", "http://localhost:1234"),
        ("localhost:1234", "http://localhost:1234"),
        ("http://localhost:1234/v1", "http://localhost:1234"),
        ("http://localhost:1234/v1/", "http://localhost:1234"),
        ("  http://box:1234  ", "http://box:1234"),
        ("https://remote.example:443", "https://remote.example:443"),
        ("", ""),
    ],
)
def test_normalize_host(raw: str, expected: str) -> None:
    assert normalize_host(raw) == expected


# --- precedence ------------------------------------------------------------


def test_explicit_host_wins_over_env(monkeypatch: pytest.MonkeyPatch, probe: Any) -> None:
    recorder = probe(["http://localhost:1234"])
    monkeypatch.setenv("LM_STUDIO_HOST", "http://from-env:1234")

    runtime = LMStudioRuntime(host="http://explicit:1234")

    assert runtime._resolve_host() == "http://explicit:1234"
    assert recorder.probed == []  # a configured host is never probed


def test_modeldock_env_wins_over_vendor_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODELDOCK_LMSTUDIO_HOST", "http://modeldock:1234")
    monkeypatch.setenv("LM_STUDIO_HOST", "http://vendor:1234")

    assert LMStudioRuntime()._resolve_host() == "http://modeldock:1234"


def test_vendor_env_used_when_modeldock_env_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LM_STUDIO_HOST", "http://vendor:1234")

    assert LMStudioRuntime()._resolve_host() == "http://vendor:1234"


def test_env_host_is_normalized(monkeypatch: pytest.MonkeyPatch) -> None:
    """Users paste the /v1 URL from LM Studio's UI; it must not double up."""
    monkeypatch.setenv("LM_STUDIO_HOST", "localhost:4321/v1/")

    assert LMStudioRuntime()._resolve_host() == "http://localhost:4321"


# --- discovery -------------------------------------------------------------


def test_discovers_first_reachable_candidate(probe: Any) -> None:
    # localhost refused, 127.0.0.1 answers — the IPv6-first case.
    recorder = probe(["http://127.0.0.1:1234"])

    assert LMStudioRuntime()._resolve_host() == "http://127.0.0.1:1234"
    assert recorder.probed[0].startswith("http://localhost:1234")


def test_discovers_container_gateway(probe: Any) -> None:
    probe(["http://host.docker.internal:1234"])

    assert LMStudioRuntime()._resolve_host() == "http://host.docker.internal:1234"


def test_falls_back_to_default_when_nothing_reachable(probe: Any) -> None:
    recorder = probe([])

    assert LMStudioRuntime()._resolve_host() == "http://localhost:1234"
    assert len(recorder.probed) == 3  # every candidate tried before giving up


def test_probe_targets_the_models_endpoint(probe: Any) -> None:
    recorder = probe(["http://localhost:1234"])
    LMStudioRuntime()._resolve_host()
    assert recorder.probed == ["http://localhost:1234/v1/models"]


def test_non_200_candidate_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Something is listening, but it is not an LM Studio server."""

    def _always_404(url: str, timeout: float = 0.0) -> Any:
        return type("R", (), {"status_code": 404})()

    monkeypatch.setattr("httpx.get", _always_404)

    assert LMStudioRuntime()._resolve_host() == "http://localhost:1234"


# --- caching ---------------------------------------------------------------


def test_resolved_host_is_cached(probe: Any) -> None:
    recorder = probe(["http://127.0.0.1:1234"])
    runtime = LMStudioRuntime()

    first = runtime._resolve_host()
    second = runtime._resolve_host()

    assert first == second
    assert len(recorder.probed) == 2  # one discovery pass, not two


def test_clear_host_cache_forces_reresolution(probe: Any) -> None:
    probe(["http://127.0.0.1:1234"])
    runtime = LMStudioRuntime()
    assert runtime._resolve_host() == "http://127.0.0.1:1234"

    runtime._host = "http://reconfigured:1234"
    runtime.clear_host_cache()

    assert runtime._resolve_host() == "http://reconfigured:1234"


# --- shared by other adapters ----------------------------------------------


def test_ollama_uses_the_shared_helper(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_HOST", "remote:11434")
    assert OllamaRuntime()._resolve_host() == "http://remote:11434"


def test_ollama_discovers_and_defaults(probe: Any) -> None:
    probe(["http://127.0.0.1:11434"])
    assert OllamaRuntime()._resolve_host() == "http://127.0.0.1:11434"

    probe([])
    assert OllamaRuntime()._resolve_host() == "http://localhost:11434"


def test_helper_is_available_to_any_adapter(probe: Any) -> None:
    """A third-party adapter gets the same behavior from BaseRuntime."""
    probe([])

    class _Custom(BaseRuntime):
        backend = RuntimeBackend.JAN

    resolved = _Custom().resolve_host(
        env_vars=("MODELDOCK_CUSTOM_HOST",),
        default="custom:9999",
        candidates=("http://nope:1",),
        probe_path="/health",
    )
    assert resolved == "http://custom:9999"


def test_discovery_skipped_without_probe_path(probe: Any) -> None:
    """Adapters that declare no probe endpoint never make network calls."""
    recorder = probe(["http://candidate:1"])

    class _Custom(BaseRuntime):
        backend = RuntimeBackend.JAN

    resolved = _Custom().resolve_host(
        default="http://fallback:1", candidates=("http://candidate:1",)
    )

    assert resolved == "http://fallback:1"
    assert recorder.probed == []
