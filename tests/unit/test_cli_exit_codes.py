"""Unit tests: every CLI failure path must exit non-zero.

Each test injects a stub manager via monkeypatch so no real runtime is needed.
Covers the three failure categories named in issue #46:
  model-not-found → exit 1
  pull-failed     → exit 1
  verify-failed   → exit 1
...plus additional failure paths audited across all commands.
"""

from __future__ import annotations

from typing import Any, Optional

import pytest
from typer.testing import CliRunner

import modeldock.cli.commands.info as info_cmd_mod
import modeldock.cli.commands.search as search_cmd_mod
import modeldock.cli.factory as factory
from modeldock.cli.app import app
from modeldock.common.errors import (
    CacheError,
    DownloadError,
    ModelNotFoundError,
    ModelNotInstalledError,
)
from modeldock.domain.model import ModelRef

runner = CliRunner()


# ---------------------------------------------------------------------------
# Stub helpers
# ---------------------------------------------------------------------------


class _RaisingManager:
    """Manager stub that raises a configurable exception on any model operation."""

    def __init__(self, exc: Exception, **_: Any) -> None:
        self._exc = exc

    def install(self, name: str) -> ModelRef:
        raise self._exc

    def update(self, name: str, confirm: bool = False) -> ModelRef:
        raise self._exc

    def remove(self, name: str) -> None:
        raise self._exc

    def load(self, name: str, **_: Any) -> Any:
        raise self._exc

    def run(self, name: str, **_: Any) -> Any:
        raise self._exc

    def install_category(self, category: str) -> list[ModelRef]:
        raise self._exc

    def search(self, query: str) -> list[Any]:
        raise self._exc

    def info(self, name: str) -> Any:
        raise self._exc


class _SuccessOnSecondManager:
    """Raises on the first install call, records whether second was attempted."""

    second_called: bool = False

    def __init__(self, **_: Any) -> None:
        self._first = True

    def install(self, name: str) -> ModelRef:
        if self._first:
            self._first = False
            raise ModelNotFoundError(name)
        type(self).second_called = True
        return ModelRef.parse(name)


class _FakeRunResult:
    def __init__(self, success: bool, error: Optional[str] = None) -> None:
        self.success = success
        self.error = error


class _FailedRunManager:
    def __init__(self, **_: Any) -> None:
        pass

    def run(self, name: str, **_: Any) -> _FakeRunResult:
        return _FakeRunResult(success=False, error="backend crashed")


# ---------------------------------------------------------------------------
# install failures
# ---------------------------------------------------------------------------


def test_install_model_not_found_exits_1(monkeypatch: pytest.MonkeyPatch) -> None:
    exc = ModelNotFoundError("ghost")
    monkeypatch.setattr(factory, "ModelManager", lambda **kw: _RaisingManager(exc, **kw))
    result = runner.invoke(app, ["install", "ghost"])
    assert result.exit_code == 1


def test_install_download_failure_exits_1(monkeypatch: pytest.MonkeyPatch) -> None:
    exc = DownloadError("llama3", "connection refused")
    monkeypatch.setattr(factory, "ModelManager", lambda **kw: _RaisingManager(exc, **kw))
    result = runner.invoke(app, ["install", "llama3"])
    assert result.exit_code == 1


def test_install_verify_failure_exits_1(monkeypatch: pytest.MonkeyPatch) -> None:
    exc = CacheError("checksum mismatch after download")
    monkeypatch.setattr(factory, "ModelManager", lambda **kw: _RaisingManager(exc, **kw))
    result = runner.invoke(app, ["install", "llama3"])
    assert result.exit_code == 1


def test_install_first_failure_aborts_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failure on model A must abort the loop — model B must not be attempted."""
    _SuccessOnSecondManager.second_called = False
    monkeypatch.setattr(factory, "ModelManager", lambda **kw: _SuccessOnSecondManager(**kw))
    result = runner.invoke(app, ["install", "ghost-a", "ghost-b"])
    assert result.exit_code == 1
    assert not _SuccessOnSecondManager.second_called


# ---------------------------------------------------------------------------
# update failures
# ---------------------------------------------------------------------------


def test_update_model_not_found_exits_1(monkeypatch: pytest.MonkeyPatch) -> None:
    exc = ModelNotFoundError("ghost")
    monkeypatch.setattr(factory, "ModelManager", lambda **kw: _RaisingManager(exc, **kw))
    result = runner.invoke(app, ["update", "ghost", "--yes"])
    assert result.exit_code == 1


def test_update_download_failure_exits_1(monkeypatch: pytest.MonkeyPatch) -> None:
    exc = DownloadError("llama3", "timeout")
    monkeypatch.setattr(factory, "ModelManager", lambda **kw: _RaisingManager(exc, **kw))
    result = runner.invoke(app, ["update", "llama3", "--yes"])
    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# remove failures
# ---------------------------------------------------------------------------


def test_remove_model_not_found_exits_1(monkeypatch: pytest.MonkeyPatch) -> None:
    exc = ModelNotFoundError("ghost")
    monkeypatch.setattr(factory, "ModelManager", lambda **kw: _RaisingManager(exc, **kw))
    result = runner.invoke(app, ["remove", "ghost", "--yes"])
    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# info failures
# ---------------------------------------------------------------------------


def test_info_model_not_found_exits_1(monkeypatch: pytest.MonkeyPatch) -> None:
    exc = ModelNotFoundError("ghost")
    monkeypatch.setattr(info_cmd_mod, "ModelManager", lambda: _RaisingManager(exc))
    result = runner.invoke(app, ["info", "ghost"])
    assert result.exit_code == 1


def test_info_unexpected_error_exits_1(monkeypatch: pytest.MonkeyPatch) -> None:
    exc = RuntimeError("catalog unavailable")
    monkeypatch.setattr(info_cmd_mod, "ModelManager", lambda: _RaisingManager(exc))
    result = runner.invoke(app, ["info", "llama3"])
    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# search failures
# ---------------------------------------------------------------------------


def test_search_unexpected_error_exits_1(monkeypatch: pytest.MonkeyPatch) -> None:
    exc = RuntimeError("catalog down")
    monkeypatch.setattr(search_cmd_mod, "ModelManager", lambda: _RaisingManager(exc))
    result = runner.invoke(app, ["search", "coding"])
    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# load failures
# ---------------------------------------------------------------------------


def test_load_model_not_installed_exits_1(monkeypatch: pytest.MonkeyPatch) -> None:
    exc = ModelNotInstalledError("ghost")
    monkeypatch.setattr(factory, "ModelManager", lambda **kw: _RaisingManager(exc, **kw))
    result = runner.invoke(app, ["load", "load", "ghost"])
    assert result.exit_code == 1


def test_load_download_failure_exits_1(monkeypatch: pytest.MonkeyPatch) -> None:
    exc = DownloadError("llama3", "network error")
    monkeypatch.setattr(factory, "ModelManager", lambda **kw: _RaisingManager(exc, **kw))
    result = runner.invoke(app, ["load", "load", "llama3", "--auto-install"])
    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# run failures
# ---------------------------------------------------------------------------


def test_run_model_not_found_exits_1(monkeypatch: pytest.MonkeyPatch) -> None:
    exc = ModelNotFoundError("ghost")
    monkeypatch.setattr(factory, "ModelManager", lambda **kw: _RaisingManager(exc, **kw))
    result = runner.invoke(app, ["run", "ghost"])
    assert result.exit_code == 1


def test_run_result_success_false_exits_1(monkeypatch: pytest.MonkeyPatch) -> None:
    """run() returning a result with success=False must exit 1 (non-exception path)."""
    monkeypatch.setattr(factory, "ModelManager", lambda **kw: _FailedRunManager(**kw))
    result = runner.invoke(app, ["run", "llama3"])
    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# install-category failures
# ---------------------------------------------------------------------------


def test_install_category_not_found_exits_1(monkeypatch: pytest.MonkeyPatch) -> None:
    exc = ModelNotFoundError("bogus-category")
    monkeypatch.setattr(factory, "ModelManager", lambda **kw: _RaisingManager(exc, **kw))
    result = runner.invoke(app, ["install-category", "bogus"])
    assert result.exit_code == 1
