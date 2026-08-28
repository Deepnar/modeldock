"""CachedCatalogRegistry — shared fetch → cache → index pipeline.

Every live catalog source follows the same shape: try the network, fall back
to a TTL'd disk cache, index whatever was found into ``ModelSpec`` entries,
and answer ``RegistryPort`` queries against that index. Previously this
pipeline was implemented once inline inside ``OllamaLibraryRegistry``; it is
factored out here so the next live source (Hugging Face, LM Studio, ...)
only has to implement "how do I reach my source," not caching or indexing.
See Architecture.md §9.
"""

from __future__ import annotations

import abc
from pathlib import Path
from typing import Any, Dict, List, Optional

from modeldock.common.errors import ModelNotFoundError
from modeldock.common.logging import get_logger
from modeldock.domain.model import (
    Capability,
    Category,
    ModelAlias,
    ModelRef,
    ModelSpec,
    RuntimeBackend,
)
from modeldock.domain.source import SourceInfo, SourceTrust


class CachedCatalogRegistry(abc.ABC):
    """Base for registries backed by one live, cached online catalog source.

    Subclasses implement :meth:`_fetch_from_network` (reach the source, parse
    it into raw dicts) and :meth:`_to_spec` (raw dict → ``ModelSpec``). This
    base owns the network → cache → index pipeline and the ``RegistryPort``
    query methods, so those never need to be reimplemented per source.
    """

    def __init__(
        self,
        cache_dir: Path,
        cache_filename: str,
        logger_name: str,
        *,
        source_name: str,
        source_trust: SourceTrust,
        source_backend: Optional[RuntimeBackend] = None,
    ) -> None:
        self._logger = get_logger(logger_name)
        self._cache_path = cache_dir / cache_filename
        self._source_name = source_name
        self._source_trust = source_trust
        self._source_backend = source_backend
        self._specs: Dict[str, ModelSpec] = {}
        self._by_alias: Dict[str, str] = {}
        self._load()

    # --- fetch → cache → index pipeline ------------------------------------

    def _load(self) -> None:
        """Try the network first, then the disk cache, then give up empty."""
        models = self._fetch_from_network()
        if models is None:
            models = self._load_cache()
        if models is None:
            self._logger.warning(
                "No network and no cache; catalog will be empty. "
                "Run with network once to populate the cache."
            )
            return
        self._build_index(models)

    def refresh(self) -> int:
        """Force a live re-fetch, bypassing the cache TTL; return model count.

        Backs ``modeldock sources refresh``. A failed fetch leaves the current
        index untouched rather than emptying it, so a refresh can never make
        discovery worse than it already was.
        """
        models = self._fetch_from_network()
        if models is None:
            self._logger.info("Refresh found no network source; keeping existing index")
            return len(self._specs)
        self._specs.clear()
        self._by_alias.clear()
        self._build_index(models)
        return len(self._specs)

    def _build_index(self, models: List[Dict[str, Any]]) -> None:
        for raw in models:
            spec = self._to_spec(raw)
            # Stamp provenance once, centrally, so every source gets it without
            # each ``_to_spec`` re-implementing it.
            if spec.source is None:
                spec.source = self._source_name
            self._specs[spec.name] = spec
            for alias in spec.aliases:
                self._by_alias[alias.lower()] = spec.name
            self._by_alias[spec.name.lower()] = spec.name

    @abc.abstractmethod
    def _fetch_from_network(self) -> Optional[List[Dict[str, Any]]]:
        """Fetch and parse raw model entries from the live source.

        Returns ``None`` on any failure (caller falls back to cache).
        """

    @abc.abstractmethod
    def _load_cache(self) -> Optional[List[Dict[str, Any]]]:
        """Load raw model entries from the on-disk cache, or ``None`` if unusable."""

    @abc.abstractmethod
    def _to_spec(self, raw: Dict[str, Any]) -> ModelSpec:
        """Convert one raw model entry into a ``ModelSpec``."""

    # --- RegistryPort -------------------------------------------------------

    def search(self, query: str) -> List[ModelSpec]:
        """Return specs whose name/alias/capability/category match ``query``."""
        return [s for s in self._specs.values() if ModelAlias.matches_query(s, query)]

    def get(self, ref: ModelRef) -> ModelSpec:
        """Return the canonical spec for ``ref`` (raises if unknown)."""
        name = self._by_alias.get(ref.name.lower())
        if name is None:
            raise ModelNotFoundError(ref.name)
        return self._specs[name]

    def resolve(self, ref: ModelRef) -> ModelSpec:
        """Resolve a friendly/alias ``ref`` to its canonical spec.

        Same resolution as :meth:`get`; named separately to make the
        source-interface intent explicit (alias → canonical identity).
        """
        return self.get(ref)

    def versions(self, ref: ModelRef) -> List[str]:
        """Return known version tags for ``ref`` (empty when unknown)."""
        try:
            return self.get(ref).version_tags()
        except ModelNotFoundError:
            return []

    def describe(self) -> List[SourceInfo]:
        """Describe this source for observability (``modeldock sources``)."""
        return [
            SourceInfo(
                name=self._source_name,
                trust=self._source_trust,
                live=True,
                backend=self._source_backend,
                model_count=len(self._specs),
                cache_path=str(self._cache_path),
                available=bool(self._specs),
            )
        ]

    def by_category(self, category: Category) -> List[ModelSpec]:
        """Return all specs in a category."""
        return [s for s in self._specs.values() if s.category == category]

    def recommend(self, task: str) -> List[ModelSpec]:
        """Return specs recommended for a task (capability/category hint)."""
        q = (task or "").strip().lower()
        if not q:
            return list(self._specs.values())
        matched = [s for s in self._specs.values() if ModelAlias.matches_query(s, q)]
        if matched:
            return matched
        # Fall back to capability-based recommendation.
        try:
            cap = Capability.from_value(q)
            return [s for s in self._specs.values() if cap in s.capabilities]
        except ValueError:
            return []

    def list_all(self) -> List[ModelSpec]:
        """Return every known spec."""
        return list(self._specs.values())


__all__ = ["CachedCatalogRegistry"]
