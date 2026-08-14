"""Tests for backend-aware category installs in ModelManager (issue #19)."""

from __future__ import annotations

from typing import Any, List

import pytest

import modeldock as md
from modeldock.common.errors import ModelNotFoundError
from modeldock.domain.model import Capability, Category, ModelRef, RuntimeBackend
from tests.conftest import FakeCache, FakeRegistry, FakeRuntime


class _MappedRuntime(FakeRuntime):
    """A runtime that names models differently from the shared catalog."""

    backend = RuntimeBackend.LM_STUDIO

    def models_for_category(self, category: Category) -> List[ModelRef]:
        if category is Category.CODING:
            return [
                ModelRef.parse("publisher/Coder-7B-GGUF", backend=RuntimeBackend.LM_STUDIO),
                ModelRef.parse("publisher/Coder-32B-GGUF", backend=RuntimeBackend.LM_STUDIO),
            ]
        return []

    def models_for_capability(self, capability: Capability) -> List[ModelRef]:
        if capability is Capability.VISION:
            return [ModelRef.parse("publisher/Vision-7B-GGUF", backend=RuntimeBackend.LM_STUDIO)]
        return []


def _manager(runtime: Any) -> md.ModelManager:
    return md.ModelManager(runtime=runtime, registry=FakeRegistry(), cache=FakeCache())


# --- routing ---------------------------------------------------------------


def test_backend_mapping_wins_over_the_catalog() -> None:
    mgr = _manager(_MappedRuntime())

    names = [ref.name for ref in mgr.suggest_category("coding")]

    assert names == ["publisher/Coder-7B-GGUF", "publisher/Coder-32B-GGUF"]


def test_catalog_used_when_runtime_has_no_mapping() -> None:
    """A runtime without its own naming keeps the previous behavior exactly."""
    mgr = _manager(FakeRuntime())

    names = [ref.name for ref in mgr.suggest_category("chat")]

    assert names == [spec.name for spec in FakeRegistry().by_category(Category.CHAT)]


def test_catalog_used_for_categories_the_mapping_skips() -> None:
    """Partial mappings fall through per category, not all-or-nothing."""
    mgr = _manager(_MappedRuntime())

    assert [r.name for r in mgr.suggest_category("chat")] == [
        spec.name for spec in FakeRegistry().by_category(Category.CHAT)
    ]


def test_install_category_pulls_the_mapped_models() -> None:
    runtime = _MappedRuntime()
    mgr = _manager(runtime)

    refs = mgr.install_category("coding")

    assert [r.name for r in refs] == ["publisher/Coder-7B-GGUF", "publisher/Coder-32B-GGUF"]
    assert [r.name for r in runtime.pulled] == [
        "publisher/Coder-7B-GGUF",
        "publisher/Coder-32B-GGUF",
    ]


def test_install_category_keeps_the_backend_on_each_ref() -> None:
    refs = _manager(_MappedRuntime()).install_category("coding")
    assert all(r.backend is RuntimeBackend.LM_STUDIO for r in refs)


def test_suggest_does_not_install() -> None:
    runtime = _MappedRuntime()
    _manager(runtime).suggest_category("coding")
    assert runtime.pulled == []


# --- capability routing ----------------------------------------------------


def test_suggest_capability_prefers_the_backend_mapping() -> None:
    mgr = _manager(_MappedRuntime())
    assert [r.name for r in mgr.suggest_capability("vision")] == ["publisher/Vision-7B-GGUF"]


def test_suggest_capability_falls_back_to_the_catalog() -> None:
    mgr = _manager(FakeRuntime())
    names = [ref.name for ref in mgr.suggest_capability("chat")]
    assert names == [s.name for s in FakeRegistry().list_all() if Capability.CHAT in s.capabilities]


# --- errors ----------------------------------------------------------------


def test_empty_category_raises_instead_of_silently_doing_nothing() -> None:
    class _EmptyRegistry(FakeRegistry):
        def by_category(self, category: Category) -> list:
            return []

    mgr = md.ModelManager(runtime=FakeRuntime(), registry=_EmptyRegistry(), cache=FakeCache())

    with pytest.raises(ModelNotFoundError):
        mgr.install_category("coding")


def test_unknown_category_still_raises_value_error() -> None:
    mgr = _manager(FakeRuntime())
    with pytest.raises(ValueError):
        mgr.suggest_category("not-a-category")


def test_unknown_capability_raises_value_error() -> None:
    mgr = _manager(FakeRuntime())
    with pytest.raises(ValueError):
        mgr.suggest_capability("not-a-capability")
