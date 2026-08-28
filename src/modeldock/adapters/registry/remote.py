"""RemoteRegistry — optional refresh of the catalog from a URL.

Falls back to ``BundledRegistry`` when the remote is unreachable. See
Architecture.md §9/§14.
"""

from __future__ import annotations

from typing import List, Optional

from modeldock.adapters.registry.bundled import BundledRegistry
from modeldock.common.errors import ModelNotFoundError
from modeldock.common.http import create_client
from modeldock.common.logging import get_logger
from modeldock.domain.model import Category, ModelRef, ModelSpec
from modeldock.domain.source import REMOTE, SourceInfo, SourceTrust


class RemoteRegistry:
    """Registry that fetches catalog entries from a remote URL."""

    def __init__(self, url: str, fallback: Optional[BundledRegistry] = None) -> None:
        self._url = url
        self._fallback = fallback or BundledRegistry()
        self._logger = get_logger("registry.remote")
        self._specs: List[ModelSpec] = []
        self._refresh()

    def _refresh(self) -> None:
        try:
            with create_client() as client:
                resp = client.get(self._url, timeout=10.0)
                resp.raise_for_status()
                data = resp.json()
            self._specs = []
            for raw in data.get("models", []):
                spec = BundledRegistry._to_spec(raw)
                if spec.source is None:
                    spec.source = REMOTE
                self._specs.append(spec)
        except Exception as exc:
            self._logger.warning("Remote registry unavailable (%s); using bundled", exc)
            self._specs = self._fallback.list_all()

    def search(self, query: str) -> List[ModelSpec]:
        return self._fallback.search(query)

    def get(self, ref: ModelRef) -> ModelSpec:
        for spec in self._specs:
            if spec.name == ref.name:
                return spec
        try:
            return self._fallback.get(ref)
        except ModelNotFoundError:
            raise ModelNotFoundError(ref.name) from None

    def resolve(self, ref: ModelRef) -> ModelSpec:
        """Resolve a friendly/alias ``ref`` to its canonical spec."""
        return self.get(ref)

    def versions(self, ref: ModelRef) -> List[str]:
        """Return known version tags for ``ref`` (empty when unknown)."""
        try:
            return self.get(ref).version_tags()
        except ModelNotFoundError:
            return []

    def describe(self) -> List[SourceInfo]:
        """Describe the remote source (user-supplied; treated as custom trust)."""
        return [
            SourceInfo(
                name=REMOTE,
                trust=SourceTrust.CUSTOM,
                live=True,
                backend=None,
                model_count=len(self._specs),
                cache_path=self._url,
                available=bool(self._specs),
            )
        ]

    def by_category(self, category: Category) -> List[ModelSpec]:
        return [s for s in self._specs if s.category == category] or self._fallback.by_category(
            category
        )

    def recommend(self, task: str) -> List[ModelSpec]:
        return self._fallback.recommend(task)

    def list_all(self) -> List[ModelSpec]:
        return self._specs or self._fallback.list_all()


__all__ = ["RemoteRegistry"]
