"""Tests for model-source provenance, versions/resolve, and source observability.

Covers the focused discovery-layer additions: every source stamps provenance
onto its specs, the source interface exposes ``versions``/``resolve``, and
sources describe themselves for ``modeldock sources``.
"""

from __future__ import annotations

from pathlib import Path
from typing import List
from unittest.mock import MagicMock, patch

from modeldock.adapters.registry.composite import CompositeRegistry
from modeldock.adapters.registry.huggingface_catalog import HuggingFaceCatalogProvider
from modeldock.common.config import Settings
from modeldock.core.manager import ModelManager
from modeldock.domain.model import Category, ModelRef, ModelSpec, ModelVariant, RuntimeBackend
from modeldock.domain.source import HUGGING_FACE, SourceInfo, SourceTrust

# ---------------------------------------------------------------------------
# ModelSpec.version_tags
# ---------------------------------------------------------------------------


def test_version_tags_leads_with_default_and_dedupes() -> None:
    spec = ModelSpec(
        name="qwen3",
        category=Category.CHAT,
        default_tag="latest",
        variants=[ModelVariant(tag="latest"), ModelVariant(tag="8b"), ModelVariant(tag="4b")],
    )
    assert spec.version_tags() == ["latest", "8b", "4b"]


def test_version_tags_without_variants_is_just_default() -> None:
    spec = ModelSpec(name="x", category=Category.CHAT, default_tag="latest", variants=[])
    assert spec.version_tags() == ["latest"]


# ---------------------------------------------------------------------------
# HuggingFace provider stamps provenance
# ---------------------------------------------------------------------------


def _hf_client(payload: List[dict]) -> MagicMock:
    client = MagicMock()
    resp = MagicMock()
    resp.json.return_value = payload
    client.get.return_value = resp
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    return client


def test_huggingface_specs_carry_provenance(tmp_path: Path) -> None:
    payload = [
        {"id": "org/Chatty-7B-GGUF", "pipeline_tag": "text-generation", "tags": ["gguf"]},
    ]
    with patch(
        "modeldock.adapters.registry.huggingface_catalog.create_client",
        return_value=_hf_client(payload),
    ):
        provider = HuggingFaceCatalogProvider(tmp_path, RuntimeBackend.LM_STUDIO)

    specs = provider.list_all()
    assert specs and all(s.source == HUGGING_FACE for s in specs)

    # versions() derives from the spec's tags; resolve() returns the canonical spec.
    ref = ModelRef.parse("org/Chatty-7B-GGUF")
    assert provider.versions(ref) == ["latest"]
    assert provider.resolve(ref).name == "org/Chatty-7B-GGUF"

    # describe() reports one live, HF-backed source.
    described = provider.describe()
    assert len(described) == 1
    info = described[0]
    assert info.name == HUGGING_FACE
    assert info.trust == SourceTrust.VERIFIED
    assert info.live is True
    assert info.model_count == len(specs)


def test_huggingface_versions_unknown_is_empty(tmp_path: Path) -> None:
    with patch(
        "modeldock.adapters.registry.huggingface_catalog.create_client",
        return_value=_hf_client([]),
    ):
        provider = HuggingFaceCatalogProvider(tmp_path, RuntimeBackend.LLAMACPP)
    assert provider.versions(ModelRef.parse("ghost")) == []


# ---------------------------------------------------------------------------
# CompositeRegistry aggregation
# ---------------------------------------------------------------------------


class _DescribingRegistry:
    """A source that can describe itself, for composite aggregation tests."""

    def __init__(self, name: str, specs: List[ModelSpec]) -> None:
        self._name = name
        self._specs = specs

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

    def describe(self) -> List[SourceInfo]:
        return [SourceInfo(name=self._name, trust=SourceTrust.CUSTOM, live=True, model_count=1)]


def test_composite_describe_aggregates_all_sources() -> None:
    a = _DescribingRegistry("A", [ModelSpec(name="a", category=Category.CHAT, aliases=["a"])])
    b = _DescribingRegistry("B", [ModelSpec(name="b", category=Category.CHAT, aliases=["b"])])
    composite = CompositeRegistry([a, b])

    names = [info.name for info in composite.describe()]
    assert names == ["A", "B"]


def test_composite_describe_handles_source_without_describe() -> None:
    class _Bare:
        def list_all(self) -> List[ModelSpec]:
            return [ModelSpec(name="x", category=Category.CHAT, aliases=["x"])]

        def search(self, q: str) -> List[ModelSpec]:
            return self.list_all()

        def get(self, ref: ModelRef) -> ModelSpec:
            return self.list_all()[0]

        def by_category(self, c: Category) -> List[ModelSpec]:
            return self.list_all()

        def recommend(self, t: str) -> List[ModelSpec]:
            return self.list_all()

    composite = CompositeRegistry([_Bare()])
    infos = composite.describe()
    assert len(infos) == 1
    assert infos[0].model_count == 1


def test_composite_versions_and_resolve_delegate() -> None:
    spec = ModelSpec(
        name="dup",
        category=Category.CHAT,
        aliases=["dup"],
        default_tag="latest",
        variants=[ModelVariant(tag="latest"), ModelVariant(tag="7b")],
    )
    composite = CompositeRegistry([_DescribingRegistry("A", [spec])])
    assert composite.resolve(ModelRef.parse("dup")).name == "dup"
    assert composite.versions(ModelRef.parse("dup")) == ["latest", "7b"]


# ---------------------------------------------------------------------------
# ModelManager sources/resolve/versions
# ---------------------------------------------------------------------------


def test_manager_sources_reports_bundled_source(tmp_path: Path) -> None:
    mgr = ModelManager(settings=Settings(cache_dir=tmp_path, catalog_source="bundled"))
    infos = mgr.sources()
    assert any(i.trust == SourceTrust.BUNDLED for i in infos)


def test_manager_resolve_and_versions_carry_provenance(tmp_path: Path) -> None:
    mgr = ModelManager(settings=Settings(cache_dir=tmp_path, catalog_source="bundled"))
    spec = mgr.resolve("llama3")
    assert spec.name == "llama3"
    assert spec.source  # provenance stamped
    assert "latest" in mgr.versions("llama3")


def test_manager_sources_fallback_for_registry_without_describe() -> None:
    class _Bare:
        def list_all(self) -> List[ModelSpec]:
            return [ModelSpec(name="x", category=Category.CHAT)]

        def search(self, q: str) -> List[ModelSpec]:
            return []

        def get(self, ref: ModelRef) -> ModelSpec:
            return self.list_all()[0]

        def by_category(self, c: Category) -> List[ModelSpec]:
            return []

        def recommend(self, t: str) -> List[ModelSpec]:
            return []

    mgr = ModelManager(registry=_Bare())
    infos = mgr.sources()
    assert len(infos) == 1
    assert infos[0].model_count == 1
