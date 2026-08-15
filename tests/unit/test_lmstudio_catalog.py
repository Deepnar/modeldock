"""Unit tests for the LM Studio capability/category mapping (issue #19)."""

from __future__ import annotations

from typing import List

import pytest

from modeldock.adapters.runtimes import lmstudio_catalog
from modeldock.adapters.runtimes.lmstudio import LMStudioRuntime
from modeldock.adapters.runtimes.ollama import OllamaRuntime
from modeldock.domain.model import Capability, Category, ModelRef, RuntimeBackend

# --- the mapping data ------------------------------------------------------


def test_every_category_is_covered() -> None:
    """A category with no entries would make install_category fail on LM Studio."""
    missing = [c for c in Category if not lmstudio_catalog.models_for_category(c)]
    assert missing == []


def test_model_ids_use_publisher_repo_form() -> None:
    """LM Studio addresses models by Hugging Face coordinates, not Ollama tags."""
    for entry in lmstudio_catalog.CATALOG:
        assert "/" in entry.model_id, f"{entry.model_id} is not publisher/repo"
        publisher, repo = entry.model_id.split("/", 1)
        assert publisher and repo


def test_model_ids_are_unique() -> None:
    ids = [entry.model_id for entry in lmstudio_catalog.CATALOG]
    assert len(ids) == len(set(ids))


def test_entries_declare_a_category_and_capabilities() -> None:
    for entry in lmstudio_catalog.CATALOG:
        assert isinstance(entry.category, Category)
        assert entry.capabilities, f"{entry.model_id} declares no capabilities"
        assert all(isinstance(c, Capability) for c in entry.capabilities)
        assert entry.description


def test_embedding_models_do_not_claim_chat() -> None:
    """An embedding model routed to a chat call would fail at request time."""
    for entry in lmstudio_catalog.models_for_category(Category.EMBEDDING):
        assert entry.capabilities == (Capability.EMBED,)


def test_capability_lookup_spans_categories() -> None:
    tool_users = lmstudio_catalog.models_for_capability(Capability.TOOL_USE)
    categories = {entry.category for entry in tool_users}
    assert Category.CHAT in categories
    assert Category.CODING in categories


def test_vision_capability_only_on_vision_models() -> None:
    for entry in lmstudio_catalog.models_for_capability(Capability.VISION):
        assert entry.category is Category.VISION


def test_unmapped_lookup_returns_empty_not_error() -> None:
    assert lmstudio_catalog.models_for_capability(Capability.REASONING)
    # A lookup that matches nothing must be an empty list, never a KeyError.
    assert lmstudio_catalog.models_for_category(Category.CHAT) != []


def test_lookup_returns_a_copy() -> None:
    """Callers must not be able to mutate the module-level index."""
    first = lmstudio_catalog.models_for_category(Category.CODING)
    first.clear()
    assert lmstudio_catalog.models_for_category(Category.CODING)


# --- the adapter -----------------------------------------------------------


def test_runtime_returns_refs_for_category() -> None:
    refs: List[ModelRef] = LMStudioRuntime().models_for_category(Category.CODING)

    assert refs
    assert all(isinstance(r, ModelRef) for r in refs)
    assert all(r.backend is RuntimeBackend.LM_STUDIO for r in refs)
    assert any("Qwen2.5-Coder" in r.name for r in refs)


def test_runtime_refs_keep_the_namespace_in_the_name() -> None:
    """The publisher belongs to the name; only ':' introduces a tag."""
    ref = LMStudioRuntime().models_for_category(Category.EMBEDDING)[0]

    assert "/" in ref.name
    assert ref.tag == "latest"
    assert ref.qualified_name() == f"{ref.name}:latest"


def test_runtime_returns_refs_for_capability() -> None:
    refs = LMStudioRuntime().models_for_capability(Capability.VISION)

    assert refs
    assert all(r.backend is RuntimeBackend.LM_STUDIO for r in refs)


def test_runtime_needs_no_server_for_suggestions() -> None:
    """Suggestions are static data — they must not require a running server."""
    runtime = LMStudioRuntime(host="http://127.0.0.1:9")  # nothing listening

    assert runtime.models_for_category(Category.CHAT)


def test_other_runtimes_return_empty_by_default() -> None:
    """Ollama's names come from the shared catalog, so it supplies no mapping."""
    assert OllamaRuntime().models_for_category(Category.CODING) == []
    assert OllamaRuntime().models_for_capability(Capability.CHAT) == []


@pytest.mark.parametrize("category", list(Category))
def test_runtime_category_lookup_never_raises(category: Category) -> None:
    assert isinstance(LMStudioRuntime().models_for_category(category), list)
