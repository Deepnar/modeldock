"""Unit tests for the generic HTTP downloader, focused on resume semantics."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import pytest

from modeldock.adapters.downloaders.http import HttpDownloader
from modeldock.common.errors import DownloadError
from modeldock.domain.model import Category, ModelSpec


class _SpecWithUrl(ModelSpec):
    """ModelSpec carrying the download URL the HTTP downloader expects."""

    download_url: str = ""


def _spec(url: str = "https://example.invalid/model.gguf") -> _SpecWithUrl:
    return _SpecWithUrl(name="demo", category=Category.CHAT, download_url=url)


class _FakeResponse:
    def __init__(self, status_code: int, body: bytes) -> None:
        self.status_code = status_code
        self._body = body
        self.headers: Dict[str, str] = {"Content-Length": str(len(body))}
        self.closed = False

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def iter_bytes(self, chunk_size: int) -> Iterator[bytes]:
        for start in range(0, len(self._body), chunk_size):
            yield self._body[start : start + chunk_size]

    def close(self) -> None:
        self.closed = True

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc: Any) -> None:
        return None


class _FakeClient:
    """Serves a queued list of responses and records the Range headers seen."""

    def __init__(self, responses: List[_FakeResponse]) -> None:
        self._responses = list(responses)
        self.ranges: List[Optional[str]] = []

    def stream(self, method: str, url: str, headers: Optional[Dict[str, str]] = None) -> Any:
        self.ranges.append((headers or {}).get("Range"))
        return self._responses.pop(0)

    def __enter__(self) -> _FakeClient:
        return self

    def __exit__(self, *exc: Any) -> None:
        return None


@pytest.fixture()
def patch_client(monkeypatch: pytest.MonkeyPatch):
    def _install(responses: List[_FakeResponse]) -> _FakeClient:
        client = _FakeClient(responses)
        monkeypatch.setattr(
            "modeldock.adapters.downloaders.http.create_client", lambda *a, **k: client
        )
        return client

    return _install


def test_download_fresh_writes_whole_body(tmp_path: Path, patch_client: Any) -> None:
    client = patch_client([_FakeResponse(200, b"abcdef")])
    dest = tmp_path / "model.gguf"

    HttpDownloader(chunk_size=2).download(_spec(), dest)

    assert dest.read_bytes() == b"abcdef"
    assert client.ranges == [None]  # no Range header without a partial file


def test_download_resumes_when_server_honors_range(tmp_path: Path, patch_client: Any) -> None:
    client = patch_client([_FakeResponse(206, b"def")])
    dest = tmp_path / "model.gguf"
    dest.write_bytes(b"abc")

    HttpDownloader(chunk_size=2).download(_spec(), dest)

    assert client.ranges == ["bytes=3-"]
    assert dest.read_bytes() == b"abcdef"


def test_download_restarts_when_server_ignores_range(tmp_path: Path, patch_client: Any) -> None:
    """A 200 reply carries the whole body; appending it would corrupt the file."""
    patch_client([_FakeResponse(200, b"abcdef")])
    dest = tmp_path / "model.gguf"
    dest.write_bytes(b"abc")

    HttpDownloader(chunk_size=2).download(_spec(), dest)

    assert dest.read_bytes() == b"abcdef"  # not b"abcabcdef"


def test_download_restarts_on_range_not_satisfiable(tmp_path: Path, patch_client: Any) -> None:
    """A stale partial file (HTTP 416) is discarded and re-fetched, not an error."""
    client = patch_client([_FakeResponse(416, b""), _FakeResponse(200, b"abcdef")])
    dest = tmp_path / "model.gguf"
    dest.write_bytes(b"abcdefghij")  # longer than the resource

    HttpDownloader(chunk_size=2).download(_spec(), dest)

    assert client.ranges == ["bytes=10-", None]
    assert dest.read_bytes() == b"abcdef"


def test_download_without_url_raises(tmp_path: Path) -> None:
    with pytest.raises(DownloadError):
        HttpDownloader().download(_spec(url=""), tmp_path / "model.gguf")
