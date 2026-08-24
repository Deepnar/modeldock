"""CompositeRegistry — merges multiple live catalog sources into one.

Different runtimes are addressable through different online catalogs: Ollama
scrapes ollama.com, while LM Studio and llama.cpp query the Hugging Face Hub.
Picking exactly one source for general discovery (``search``/``list``/
``recommend``) means the result may not even be installable through whichever
backend is active. ``CompositeRegistry`` instead queries every configured
source and merges the results, so discovery surfaces models the active
backend can actually install, alongside the general shared catalog. See
Architecture.md §9.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from modeldock.common.errors import ModelNotFoundError
from modeldock.domain.model import Category, ModelRef, ModelSpec
from modeldock.ports.registry import RegistryPort


class CompositeRegistry:
    """Merges an ordered list of ``RegistryPort`` sources into one.

    Earlier sources take priority: when two sources describe a model under
    the same name, the first source's entry wins. ``get()`` returns the
    first source that resolves the reference, raising only when none do.
    """

    def __init__(self, sources: Sequence[RegistryPort]) -> None:
        if not sources:
            raise ValueError("CompositeRegistry requires at least one source")
        self._sources: List[RegistryPort] = list(sources)

    @staticmethod
    def _merge(groups: Sequence[List[ModelSpec]]) -> List[ModelSpec]:
        seen: Dict[str, ModelSpec] = {}
        merged: List[ModelSpec] = []
        for group in groups:
            for spec in group:
                if spec.name in seen:
                    continue
                seen[spec.name] = spec
                merged.append(spec)
        return merged

    # --- RegistryPort -------------------------------------------------------

    def search(self, query: str) -> List[ModelSpec]:
        """Return specs whose name/alias/capability/category match ``query``."""
        return self._merge([source.search(query) for source in self._sources])

    def get(self, ref: ModelRef) -> ModelSpec:
        """Return the canonical spec for ``ref`` from the first source that has it."""
        last_error: Optional[ModelNotFoundError] = None
        for source in self._sources:
            try:
                return source.get(ref)
            except ModelNotFoundError as exc:
                last_error = exc
        raise last_error or ModelNotFoundError(ref.name)

    def by_category(self, category: Category) -> List[ModelSpec]:
        """Return all specs in a category, merged across sources."""
        return self._merge([source.by_category(category) for source in self._sources])

    def recommend(self, task: str) -> List[ModelSpec]:
        """Return specs recommended for a task, merged across sources."""
        return self._merge([source.recommend(task) for source in self._sources])

    def list_all(self) -> List[ModelSpec]:
        """Return every known spec, merged across sources."""
        return self._merge([source.list_all() for source in self._sources])


__all__ = ["CompositeRegistry"]
