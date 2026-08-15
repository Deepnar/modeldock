"""Curated LM Studio model suggestions per ModelDock category/capability.

Why this exists
---------------
ModelDock's catalog is built from ``ollama.com/library``, whose names
(``qwen2.5-coder``, ``llama3``) are Ollama tags. LM Studio addresses models by
their Hugging Face coordinates instead (``publisher/repo``), so feeding an
Ollama name to LM Studio asks for a model it has never heard of. Category
installs therefore need a per-backend mapping — see issue #19.

Maintaining this list
---------------------
Entries are curated, not discovered: LM Studio exposes no searchable remote
catalog over its local API, so there is nothing to query at runtime. That makes
this table a point-in-time snapshot of LM Studio's commonly published models,
and publishers do rename and retire repos. Treat a miss as expected: callers
surface an actionable message rather than failing hard, and adding or
correcting an entry here is a one-line change requiring no code.

Each entry names the publisher exactly as LM Studio lists it, so a user can
paste the ``model_id`` into LM Studio's search box and find the same model.
"""

from __future__ import annotations

from typing import Dict, List, NamedTuple, Tuple

from modeldock.domain.model import Capability, Category


class LMStudioModel(NamedTuple):
    """One curated LM Studio model suggestion."""

    model_id: str
    category: Category
    capabilities: Tuple[Capability, ...]
    params: str
    description: str


# Ordered smallest-first within each category so the first suggestion is the
# one most likely to run on a laptop.
CATALOG: Tuple[LMStudioModel, ...] = (
    # --- chat -------------------------------------------------------------
    LMStudioModel(
        "lmstudio-community/Llama-3.2-3B-Instruct-GGUF",
        Category.CHAT,
        (Capability.CHAT, Capability.COMPLETION),
        "3B",
        "Meta Llama 3.2 Instruct — small general-purpose chat model.",
    ),
    LMStudioModel(
        "lmstudio-community/Meta-Llama-3.1-8B-Instruct-GGUF",
        Category.CHAT,
        (Capability.CHAT, Capability.COMPLETION, Capability.TOOL_USE),
        "8B",
        "Meta Llama 3.1 Instruct — general-purpose chat with tool calling.",
    ),
    LMStudioModel(
        "lmstudio-community/Mistral-7B-Instruct-v0.3-GGUF",
        Category.CHAT,
        (Capability.CHAT, Capability.COMPLETION, Capability.TOOL_USE),
        "7B",
        "Mistral 7B Instruct — fast, compact general-purpose chat model.",
    ),
    LMStudioModel(
        "lmstudio-community/gemma-2-9b-it-GGUF",
        Category.CHAT,
        (Capability.CHAT, Capability.COMPLETION),
        "9B",
        "Google Gemma 2 Instruct — strong quality for its size.",
    ),
    # --- coding -----------------------------------------------------------
    LMStudioModel(
        "lmstudio-community/Qwen2.5-Coder-1.5B-Instruct-GGUF",
        Category.CODING,
        (Capability.CHAT, Capability.COMPLETION),
        "1.5B",
        "Qwen2.5 Coder — lightweight code completion for constrained machines.",
    ),
    LMStudioModel(
        "lmstudio-community/Qwen2.5-Coder-7B-Instruct-GGUF",
        Category.CODING,
        (Capability.CHAT, Capability.COMPLETION, Capability.TOOL_USE),
        "7B",
        "Qwen2.5 Coder — code generation, completion, and repair.",
    ),
    LMStudioModel(
        "lmstudio-community/Qwen2.5-Coder-32B-Instruct-GGUF",
        Category.CODING,
        (Capability.CHAT, Capability.COMPLETION, Capability.TOOL_USE),
        "32B",
        "Qwen2.5 Coder 32B — highest-quality local coding model in this list.",
    ),
    # --- reasoning --------------------------------------------------------
    LMStudioModel(
        "lmstudio-community/DeepSeek-R1-Distill-Qwen-7B-GGUF",
        Category.REASONING,
        (Capability.CHAT, Capability.COMPLETION, Capability.REASONING),
        "7B",
        "DeepSeek R1 distill — emits explicit reasoning steps.",
    ),
    LMStudioModel(
        "lmstudio-community/DeepSeek-R1-Distill-Qwen-14B-GGUF",
        Category.REASONING,
        (Capability.CHAT, Capability.COMPLETION, Capability.REASONING),
        "14B",
        "DeepSeek R1 distill, larger — stronger multi-step reasoning.",
    ),
    # --- vision -----------------------------------------------------------
    LMStudioModel(
        "lmstudio-community/llava-v1.5-7b-llamafile",
        Category.VISION,
        (Capability.CHAT, Capability.VISION),
        "7B",
        "LLaVA — answers questions about images.",
    ),
    LMStudioModel(
        "lmstudio-community/Qwen2-VL-7B-Instruct-GGUF",
        Category.VISION,
        (Capability.CHAT, Capability.COMPLETION, Capability.VISION),
        "7B",
        "Qwen2-VL — image understanding and document/chart reading.",
    ),
    # --- embedding --------------------------------------------------------
    LMStudioModel(
        "nomic-ai/nomic-embed-text-v1.5-GGUF",
        Category.EMBEDDING,
        (Capability.EMBED,),
        "137M",
        "Nomic Embed Text — general-purpose text embeddings.",
    ),
    LMStudioModel(
        "lmstudio-community/bge-large-en-v1.5-GGUF",
        Category.EMBEDDING,
        (Capability.EMBED,),
        "335M",
        "BGE Large EN — high-quality English text embeddings.",
    ),
    # --- instruct ---------------------------------------------------------
    LMStudioModel(
        "lmstudio-community/Phi-3.1-mini-4k-instruct-GGUF",
        Category.INSTRUCT,
        (Capability.CHAT, Capability.COMPLETION),
        "3.8B",
        "Microsoft Phi-3.1 Mini — instruction following on modest hardware.",
    ),
)


def _by_category() -> Dict[Category, List[LMStudioModel]]:
    index: Dict[Category, List[LMStudioModel]] = {}
    for entry in CATALOG:
        index.setdefault(entry.category, []).append(entry)
    return index


def _by_capability() -> Dict[Capability, List[LMStudioModel]]:
    index: Dict[Capability, List[LMStudioModel]] = {}
    for entry in CATALOG:
        for capability in entry.capabilities:
            index.setdefault(capability, []).append(entry)
    return index


_CATEGORY_INDEX = _by_category()
_CAPABILITY_INDEX = _by_capability()


def models_for_category(category: Category) -> List[LMStudioModel]:
    """Return curated LM Studio models for ``category`` (empty when unmapped)."""
    return list(_CATEGORY_INDEX.get(category, []))


def models_for_capability(capability: Capability) -> List[LMStudioModel]:
    """Return curated LM Studio models exposing ``capability``."""
    return list(_CAPABILITY_INDEX.get(capability, []))


def mapped_categories() -> List[Category]:
    """Return every category this mapping covers."""
    return list(_CATEGORY_INDEX)


__all__ = [
    "CATALOG",
    "LMStudioModel",
    "mapped_categories",
    "models_for_capability",
    "models_for_category",
]
