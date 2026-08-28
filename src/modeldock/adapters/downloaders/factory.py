"""Downloader dispatch — select the right downloader for a given ModelSpec."""

from __future__ import annotations

from modeldock.domain.model import ModelSpec


def needs_http_download(spec: ModelSpec) -> bool:
    """Return True when the spec's default variant carries a direct download URL.

    When True, callers should use ``HttpDownloader.download(spec, dest)`` rather
    than delegating to the runtime's native pull mechanism.
    """
    variant = spec.default_variant()
    return variant is not None and bool(variant.download_url)


__all__ = ["needs_http_download"]
