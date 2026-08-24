"""Tests for CatalogProviderRegistry — built-ins plus third-party plugin discovery."""

from __future__ import annotations

from pathlib import Path
from typing import Any, List
from unittest.mock import MagicMock, patch

from modeldock.adapters.registry.catalog_registry import CatalogProviderRegistry
from modeldock.adapters.registry.composite import CompositeRegistry
from modeldock.common.config import Settings
from modeldock.core.manager import ModelManager
from modeldock.domain.model import Category, ModelRef, ModelSpec, RuntimeBackend


class _FakePluginRegistry:
    """A minimal RegistryPort a third-party plugin might provide."""

    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = cache_dir
        self._specs = [ModelSpec(name="vllm-org/Fast-Serve-7B", category=Category.CHAT)]

    def search(self, query: str) -> List[ModelSpec]:
        return list(self._specs)

    def get(self, ref: ModelRef) -> ModelSpec:
        for spec in self._specs:
            if spec.name == ref.name:
                return spec
        from modeldock.common.errors import ModelNotFoundError

        raise ModelNotFoundError(ref.name)

    def by_category(self, category: Category) -> List[ModelSpec]:
        return [s for s in self._specs if s.category == category]

    def recommend(self, task: str) -> List[ModelSpec]:
        return list(self._specs)

    def list_all(self) -> List[ModelSpec]:
        return list(self._specs)


def _fake_entry_point(name: str, target: Any, raises_on_load: bool = False) -> MagicMock:
    ep = MagicMock()
    ep.name = name
    if raises_on_load:
        ep.load.side_effect = RuntimeError("broken plugin")
    else:
        ep.load.return_value = target
    return ep


def _patched_entry_points(entries: List[MagicMock]) -> MagicMock:
    """Build a mock for importlib.metadata.entry_points() supporting .select()."""
    eps = MagicMock()
    eps.select.return_value = entries
    return eps


class TestBuiltins:
    def test_lmstudio_resolves_to_huggingface_provider(self, tmp_path: Path) -> None:
        from modeldock.adapters.registry.huggingface_catalog import HuggingFaceCatalogProvider

        with patch("modeldock.adapters.registry.huggingface_catalog.create_client") as mock_factory:
            mock_client = MagicMock()
            mock_client.get.side_effect = Exception("offline")
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_factory.return_value = mock_client
            registry = CatalogProviderRegistry().get(RuntimeBackend.LM_STUDIO, tmp_path)

        assert isinstance(registry, HuggingFaceCatalogProvider)

    def test_ollama_has_no_live_catalog(self, tmp_path: Path) -> None:
        assert CatalogProviderRegistry().get(RuntimeBackend.OLLAMA, tmp_path) is None

    def test_available_backends_includes_builtins(self) -> None:
        backends = CatalogProviderRegistry().available_backends()
        assert RuntimeBackend.LM_STUDIO in backends
        assert RuntimeBackend.LLAMACPP in backends


class TestEntryPointDiscovery:
    def test_plugin_registers_a_new_backend(self, tmp_path: Path) -> None:
        entries = [_fake_entry_point("vllm", _FakePluginRegistry)]
        with patch(
            "modeldock.adapters.registry.catalog_registry.entry_points",
            return_value=_patched_entry_points(entries),
        ):
            registry = CatalogProviderRegistry()

        assert RuntimeBackend.VLLM in registry.available_backends()
        catalog = registry.get(RuntimeBackend.VLLM, tmp_path)
        assert isinstance(catalog, _FakePluginRegistry)
        assert catalog.list_all()[0].name == "vllm-org/Fast-Serve-7B"

    def test_plugin_overrides_a_builtin(self, tmp_path: Path) -> None:
        entries = [_fake_entry_point("lmstudio", _FakePluginRegistry)]
        with patch(
            "modeldock.adapters.registry.catalog_registry.entry_points",
            return_value=_patched_entry_points(entries),
        ):
            registry = CatalogProviderRegistry()
            catalog = registry.get(RuntimeBackend.LM_STUDIO, tmp_path)

        assert isinstance(catalog, _FakePluginRegistry)

    def test_broken_plugin_is_skipped_not_fatal(self, tmp_path: Path) -> None:
        entries = [
            _fake_entry_point("vllm", None, raises_on_load=True),
            _fake_entry_point("jan", _FakePluginRegistry),
        ]
        with patch(
            "modeldock.adapters.registry.catalog_registry.entry_points",
            return_value=_patched_entry_points(entries),
        ):
            registry = CatalogProviderRegistry()

        assert registry.get(RuntimeBackend.VLLM, tmp_path) is None
        assert isinstance(registry.get(RuntimeBackend.JAN, tmp_path), _FakePluginRegistry)

    def test_unknown_entry_point_name_is_skipped(self, tmp_path: Path) -> None:
        entries = [_fake_entry_point("not-a-real-backend", _FakePluginRegistry)]
        with patch(
            "modeldock.adapters.registry.catalog_registry.entry_points",
            return_value=_patched_entry_points(entries),
        ):
            registry = CatalogProviderRegistry()

        assert set(registry.available_backends()) == {
            RuntimeBackend.LM_STUDIO,
            RuntimeBackend.LLAMACPP,
        }

    def test_factory_exception_degrades_to_none(self, tmp_path: Path) -> None:
        def _boom(cache_dir: Path) -> Any:
            raise RuntimeError("cannot build catalog")

        entries = [_fake_entry_point("vllm", _boom)]
        with patch(
            "modeldock.adapters.registry.catalog_registry.entry_points",
            return_value=_patched_entry_points(entries),
        ):
            registry = CatalogProviderRegistry()
            assert registry.get(RuntimeBackend.VLLM, tmp_path) is None


class TestManagerIntegrationWithPlugin:
    def test_manager_merges_third_party_plugin_into_discovery(self, tmp_path: Path) -> None:
        entries = [_fake_entry_point("vllm", _FakePluginRegistry)]
        with (
            patch(
                "modeldock.adapters.registry.catalog_registry.entry_points",
                return_value=_patched_entry_points(entries),
            ),
            patch("modeldock.adapters.registry.ollama_library.create_client") as ollama_factory,
        ):
            mock_client = MagicMock()
            mock_client.get.side_effect = Exception("offline")
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            ollama_factory.return_value = mock_client

            manager = ModelManager(
                backend=RuntimeBackend.VLLM,
                settings=Settings(cache_dir=tmp_path),
            )

        assert isinstance(manager._registry_port, CompositeRegistry)
        names = {s.name for s in manager._registry_port.list_all()}
        assert "vllm-org/Fast-Serve-7B" in names
        assert "llama3" in names  # bundled fallback still merged in
