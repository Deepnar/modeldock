"""Tests for CompositeRegistry and its wiring into ModelManager._resolve_registry."""

from __future__ import annotations

from pathlib import Path
from typing import List
from unittest.mock import MagicMock, patch

import pytest

from modeldock.adapters.registry.bundled import BundledRegistry
from modeldock.adapters.registry.composite import CompositeRegistry
from modeldock.adapters.registry.ollama_library import OllamaLibraryRegistry
from modeldock.common.config import Settings
from modeldock.common.errors import ModelNotFoundError
from modeldock.core.manager import ModelManager
from modeldock.domain.model import Category, ModelRef, ModelSpec, RuntimeBackend

# ---------------------------------------------------------------------------
# CompositeRegistry unit tests
# ---------------------------------------------------------------------------


def _spec(name: str, category: Category = Category.CHAT) -> ModelSpec:
    return ModelSpec(name=name, category=category, aliases=[name])


class _FakeRegistry:
    """Minimal RegistryPort stand-in for composite merge tests."""

    def __init__(self, specs: List[ModelSpec]) -> None:
        self._specs = specs

    def search(self, query: str) -> List[ModelSpec]:
        return list(self._specs)

    def get(self, ref: ModelRef) -> ModelSpec:
        for spec in self._specs:
            if spec.name == ref.name:
                return spec
        raise ModelNotFoundError(ref.name)

    def by_category(self, category: Category) -> List[ModelSpec]:
        return [s for s in self._specs if s.category == category]

    def recommend(self, task: str) -> List[ModelSpec]:
        return list(self._specs)

    def list_all(self) -> List[ModelSpec]:
        return list(self._specs)


class TestCompositeRegistry:
    def test_requires_at_least_one_source(self) -> None:
        with pytest.raises(ValueError):
            CompositeRegistry([])

    def test_list_all_merges_sources(self) -> None:
        first = _FakeRegistry([_spec("a"), _spec("b")])
        second = _FakeRegistry([_spec("c")])
        registry = CompositeRegistry([first, second])

        names = {s.name for s in registry.list_all()}
        assert names == {"a", "b", "c"}

    def test_earlier_source_wins_on_name_collision(self) -> None:
        winner = _spec("dup", category=Category.CODING)
        loser = _spec("dup", category=Category.CHAT)
        registry = CompositeRegistry([_FakeRegistry([winner]), _FakeRegistry([loser])])

        specs = registry.list_all()
        assert len(specs) == 1
        assert specs[0].category == Category.CODING

    def test_get_falls_through_to_second_source(self) -> None:
        registry = CompositeRegistry(
            [_FakeRegistry([_spec("only-in-first")]), _FakeRegistry([_spec("only-in-second")])]
        )

        assert registry.get(ModelRef.parse("only-in-second")).name == "only-in-second"

    def test_get_raises_when_no_source_resolves(self) -> None:
        registry = CompositeRegistry([_FakeRegistry([]), _FakeRegistry([])])

        with pytest.raises(ModelNotFoundError):
            registry.get(ModelRef.parse("nonexistent"))

    def test_by_category_merges_and_filters(self) -> None:
        registry = CompositeRegistry(
            [
                _FakeRegistry([_spec("chat-a", Category.CHAT)]),
                _FakeRegistry([_spec("code-a", Category.CODING)]),
            ]
        )

        assert [s.name for s in registry.by_category(Category.CODING)] == ["code-a"]

    def test_search_merges_sources(self) -> None:
        registry = CompositeRegistry([_FakeRegistry([_spec("a")]), _FakeRegistry([_spec("b")])])
        names = {s.name for s in registry.search("")}
        assert names == {"a", "b"}


# ---------------------------------------------------------------------------
# ModelManager._resolve_registry wiring
# ---------------------------------------------------------------------------


def _mock_client(payload: object = None, raises: bool = False) -> MagicMock:
    mock_client = MagicMock()
    if raises:
        mock_client.get.side_effect = Exception("network unavailable")
    else:
        mock_response = MagicMock()
        if isinstance(payload, str):
            mock_response.text = payload
        else:
            mock_response.json.return_value = payload
        mock_client.get.return_value = mock_response
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    return mock_client


class TestManagerRegistryResolution:
    def test_ollama_backend_gets_no_composite(self, tmp_path: Path) -> None:
        """Ollama already names models the shared catalog understands."""
        with patch("modeldock.adapters.registry.ollama_library.create_client") as mock_factory:
            mock_factory.return_value = _mock_client(raises=True)

            manager = ModelManager(
                backend=RuntimeBackend.OLLAMA,
                settings=Settings(cache_dir=tmp_path),
            )

        assert isinstance(manager._registry_port, BundledRegistry)

    def test_lmstudio_auto_merges_live_hf_with_base_catalog(self, tmp_path: Path) -> None:
        with (
            patch("modeldock.adapters.registry.ollama_library.create_client") as ollama_factory,
            patch("modeldock.adapters.registry.huggingface_catalog.create_client") as hf_factory,
        ):
            ollama_factory.return_value = _mock_client(raises=True)  # forces bundled base
            hf_factory.return_value = _mock_client(
                payload=[
                    {
                        "id": "unit-test-org/Live-Chat-Model-GGUF",
                        "pipeline_tag": "text-generation",
                        "tags": ["gguf", "conversational"],
                    }
                ]
            )

            manager = ModelManager(
                backend=RuntimeBackend.LM_STUDIO,
                settings=Settings(cache_dir=tmp_path),
            )

        assert isinstance(manager._registry_port, CompositeRegistry)
        names = {s.name for s in manager._registry_port.list_all()}
        assert "unit-test-org/Live-Chat-Model-GGUF" in names
        # The bundled fallback's entries are still present, merged in.
        assert "llama3" in names

    def test_lmstudio_bundled_source_skips_live_catalog_entirely(self, tmp_path: Path) -> None:
        """catalog_source="bundled" is an explicit opt-out: no network, no merge."""
        with patch("modeldock.adapters.registry.huggingface_catalog.create_client") as hf_factory:
            manager = ModelManager(
                backend=RuntimeBackend.LM_STUDIO,
                settings=Settings(cache_dir=tmp_path, catalog_source="bundled"),
            )

            hf_factory.assert_not_called()

        assert isinstance(manager._registry_port, BundledRegistry)

    def test_lmstudio_ollama_source_skips_live_hf_catalog(self, tmp_path: Path) -> None:
        """catalog_source="ollama" is an explicit opt-out too: single source, no merge."""
        with (
            patch("modeldock.adapters.registry.ollama_library.create_client") as ollama_factory,
            patch("modeldock.adapters.registry.huggingface_catalog.create_client") as hf_factory,
        ):
            ollama_factory.return_value = _mock_client(payload="<html></html>")

            manager = ModelManager(
                backend=RuntimeBackend.LM_STUDIO,
                settings=Settings(cache_dir=tmp_path, catalog_source="ollama"),
            )

            hf_factory.assert_not_called()

        assert isinstance(manager._registry_port, OllamaLibraryRegistry)

    def test_llamacpp_auto_also_gets_composite(self, tmp_path: Path) -> None:
        with (
            patch("modeldock.adapters.registry.ollama_library.create_client") as ollama_factory,
            patch("modeldock.adapters.registry.huggingface_catalog.create_client") as hf_factory,
        ):
            ollama_factory.return_value = _mock_client(raises=True)
            hf_factory.return_value = _mock_client(raises=True)  # empty live catalog is fine too

            manager = ModelManager(
                backend=RuntimeBackend.LLAMACPP,
                settings=Settings(cache_dir=tmp_path),
            )

        assert isinstance(manager._registry_port, CompositeRegistry)
