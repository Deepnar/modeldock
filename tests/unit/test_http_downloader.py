"""Unit tests for the generic HTTP downloader, focused on resume semantics."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import hashlib

import pytest

from modeldock.adapters.downloaders.http import HttpDownloader
from modeldock.common.errors import DownloadError
from modeldock.domain.model import Category, ModelSpec, ModelVariant


def _spec(url: str = "https://example.com/model.gguf", sha256: Optional[str] = None) -> ModelSpec:
    return ModelSpec(
        name="demo",
        category=Category.CHAT,
        variants=[
            ModelVariant(
                tag="latest",
                download_url=url,
                sha256=sha256,
            )
        ],
        default_tag="latest",
    )


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
    (tmp_path / "model.gguf.tmp").write_bytes(b"abc")

    HttpDownloader(chunk_size=2).download(_spec(), dest)

    assert client.ranges == ["bytes=3-"]
    assert dest.read_bytes() == b"abcdef"


def test_download_restarts_when_server_ignores_range(tmp_path: Path, patch_client: Any) -> None:
    """A 200 reply carries the whole body; appending it would corrupt the file."""
    patch_client([_FakeResponse(200, b"abcdef")])
    dest = tmp_path / "model.gguf"
    (tmp_path / "model.gguf.tmp").write_bytes(b"abc")

    HttpDownloader(chunk_size=2).download(_spec(), dest)

    assert dest.read_bytes() == b"abcdef"  # not b"abcabcdef"


def test_download_restarts_on_range_not_satisfiable(tmp_path: Path, patch_client: Any) -> None:
    """A stale partial file (HTTP 416) is discarded and re-fetched, not an error."""
    client = patch_client([_FakeResponse(416, b""), _FakeResponse(200, b"abcdef")])
    dest = tmp_path / "model.gguf"
    (tmp_path / "model.gguf.tmp").write_bytes(b"abcdefghij")  # longer than the resource

    HttpDownloader(chunk_size=2).download(_spec(), dest)

    assert client.ranges == ["bytes=10-", None]
    assert dest.read_bytes() == b"abcdef"


def test_download_without_url_raises(tmp_path: Path) -> None:
    with pytest.raises(DownloadError):
        HttpDownloader().download(_spec(url=""), tmp_path / "model.gguf")


def test_uses_download_url_from_default_variant(tmp_path) -> None:
    spec = ModelSpec(
        name="demo",
        category=Category.CHAT,
        default_tag="70b",
        variants=[
            ModelVariant(
                tag="8b",
                download_url="https://example.com/model-8b.gguf",
            ),
            ModelVariant(
                tag="70b",
                download_url="https://example.com/model-70b.gguf",
            ),
        ],
    )

    assert HttpDownloader._url_for(spec) == "https://example.com/model-70b.gguf"


def test_missing_variant_download_url_raises() -> None:
    spec = ModelSpec(
        name="demo",
        category=Category.CHAT,
        default_tag="latest",
        variants=[
            ModelVariant(tag="latest"),
        ],
    )

    with pytest.raises(DownloadError, match="No download_url"):
        HttpDownloader._url_for(spec)


def test_tmp_file_absent_after_successful_download(tmp_path: Path, patch_client: Any) -> None:
    """The .tmp staging file must be gone after a successful download."""
    patch_client([_FakeResponse(200, b"abcdef")])
    dest = tmp_path / "model.gguf"

    HttpDownloader(chunk_size=2).download(_spec(), dest)

    assert dest.read_bytes() == b"abcdef"
    assert not (tmp_path / "model.gguf.tmp").exists()


def test_tmp_file_cleaned_up_on_interrupted_download(tmp_path: Path, patch_client: Any) -> None:
    """An exception mid-stream must delete the .tmp file and not create dest."""

    class _BrokenResponse(_FakeResponse):
        def iter_bytes(self, chunk_size: int) -> Iterator[bytes]:
            yield b"abc"
            raise OSError("simulated network failure")

    patch_client([_BrokenResponse(200, b"abcdef")])
    dest = tmp_path / "model.gguf"

    with pytest.raises(DownloadError):
        HttpDownloader(chunk_size=2).download(_spec(), dest)

    assert not dest.exists()
    assert not (tmp_path / "model.gguf.tmp").exists()


def test_resume_reads_tmp_file_size(tmp_path: Path, patch_client: Any) -> None:
    """A pre-existing .tmp file causes a Range header for its byte count."""
    client = patch_client([_FakeResponse(206, b"world")])
    dest = tmp_path / "model.gguf"
    (tmp_path / "model.gguf.tmp").write_bytes(b"hello")

    HttpDownloader(chunk_size=16).download(_spec(), dest)

    assert client.ranges == ["bytes=5-"]
    assert dest.read_bytes() == b"helloworld"


# --- Checksum verification tests ---


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_checksum_passes_when_correct(tmp_path: Path, patch_client: Any) -> None:
    """Download succeeds when the file digest matches the spec."""
    body = b"abcdef"
    patch_client([_FakeResponse(200, body)])
    dest = tmp_path / "model.gguf"

    HttpDownloader(chunk_size=2).download(_spec(sha256=_sha256(body)), dest)

    assert dest.read_bytes() == body


def test_checksum_raises_on_mismatch(tmp_path: Path, patch_client: Any) -> None:
    """A digest mismatch raises DownloadError and leaves no files behind."""
    patch_client([_FakeResponse(200, b"abcdef")])
    dest = tmp_path / "model.gguf"

    with pytest.raises(DownloadError, match="SHA-256 mismatch"):
        HttpDownloader(chunk_size=2).download(_spec(sha256="deadbeef" * 8), dest)

    assert not dest.exists()
    assert not (tmp_path / "model.gguf.tmp").exists()


def test_checksum_skipped_when_absent(tmp_path: Path, patch_client: Any) -> None:
    """No sha256 in spec → verification is skipped; download succeeds."""
    body = b"abcdef"
    patch_client([_FakeResponse(200, body)])
    dest = tmp_path / "model.gguf"

    HttpDownloader(chunk_size=2).download(_spec(sha256=None), dest)

    assert dest.read_bytes() == body
