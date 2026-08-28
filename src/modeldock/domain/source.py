"""Model-source provenance value objects.

A *source* is where a model's metadata comes from (ollama.com, the Hugging
Face Hub, the bundled fallback, ...). ``RegistryPort`` implementations *are*
ModelDock's model sources; this module gives them a small, pure vocabulary for
describing themselves so the SDK/CLI can surface provenance to users
("source: Ollama Official") and enumerate active sources (``modeldock
sources``). See Architecture.md §9.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel

from modeldock.domain.model import RuntimeBackend


class SourceTrust(str, Enum):
    """How much a source's provenance can be trusted.

    Mirrors the distinction in Architecture.md §Security: an official
    runtime/vendor catalog, a well-known verified hub, an arbitrary community
    feed, the bundled emergency fallback, or a user-supplied custom source.
    """

    OFFICIAL = "official"
    VERIFIED = "verified"
    COMMUNITY = "community"
    BUNDLED = "bundled"
    CUSTOM = "custom"


#: Canonical, human-facing source labels. Adapters stamp these onto every
#: ``ModelSpec`` they emit (``spec.source``) so discovery results carry
#: provenance without the caller needing to know which adapter produced them.
OLLAMA_OFFICIAL = "Ollama Official"
HUGGING_FACE = "Hugging Face"
BUNDLED = "Bundled (offline fallback)"
REMOTE = "Remote registry"


class SourceInfo(BaseModel):
    """A description of one active model source, for observability.

    Pure data — no I/O. Built by each registry's ``describe()`` and surfaced
    by ``modeldock sources`` so users can see where discovered models come
    from and whether a source is currently populated.
    """

    name: str
    trust: SourceTrust
    live: bool
    backend: Optional[RuntimeBackend] = None
    model_count: int = 0
    cache_path: Optional[str] = None
    available: bool = True


__all__ = [
    "SourceTrust",
    "SourceInfo",
    "OLLAMA_OFFICIAL",
    "HUGGING_FACE",
    "BUNDLED",
    "REMOTE",
]
