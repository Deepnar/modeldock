"""Unit tests for the downloader dispatch helper."""

from __future__ import annotations

import pytest

from modeldock.adapters.downloaders.factory import needs_http_download
from modeldock.domain.model import Category, ModelSpec, ModelVariant, RuntimeBackend


def test_true_when_default_variant_has_url() -> None:
    spec = ModelSpec(
        name="demo",
        category=Category.CHAT,
        default_tag="latest",
        variants=[ModelVariant(tag="latest", download_url="https://example.com/model.gguf")],
    )
    assert needs_http_download(spec) is True


def test_false_when_no_variants() -> None:
    spec = ModelSpec(name="demo", category=Category.CHAT)
    assert needs_http_download(spec) is False


def test_false_when_default_variant_has_no_url() -> None:
    spec = ModelSpec(
        name="demo",
        category=Category.CHAT,
        default_tag="latest",
        variants=[ModelVariant(tag="latest")],
    )
    assert needs_http_download(spec) is False


def test_false_when_default_tag_absent_from_variants() -> None:
    """Only the *default* variant is checked; a URL on a non-default tag doesn't count."""
    spec = ModelSpec(
        name="demo",
        category=Category.CHAT,
        default_tag="8b",
        variants=[
            ModelVariant(tag="latest", download_url="https://example.com/model.gguf"),
        ],
    )
    assert needs_http_download(spec) is False


def test_false_when_url_is_empty_string() -> None:
    spec = ModelSpec(
        name="demo",
        category=Category.CHAT,
        default_tag="latest",
        variants=[ModelVariant(tag="latest", download_url="")],
    )
    assert needs_http_download(spec) is False


def test_true_for_llamacpp_hinted_spec_with_url() -> None:
    spec = ModelSpec(
        name="llama3.2",
        category=Category.CHAT,
        default_tag="3b-gguf",
        backend_hints=[RuntimeBackend.LLAMACPP],
        variants=[
            ModelVariant(
                tag="3b-gguf",
                download_url="https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF/resolve/main/Llama-3.2-3B-Instruct-Q4_K_M.gguf",
            )
        ],
    )
    assert needs_http_download(spec) is True
