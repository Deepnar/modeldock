"""HttpDownloader - generic streaming/resumable HTTP downloader.

Uses httpx with Range support so interrupted downloads resume. Reports bytes
via ProgressPort. See Architecture.md S10.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from modeldock.common.errors import DownloadError
from modeldock.common.http import create_client
from modeldock.common.logging import get_logger
from modeldock.domain.model import ModelRef, ModelSpec


class HttpDownloader:
    """Generic HTTP downloader for runtimes exposing direct file URLs."""

    def __init__(self, chunk_size: int = 1024 * 1024) -> None:
        self._chunk_size = chunk_size
        self._logger = get_logger("downloader.http")

    def download(self, spec: ModelSpec, dest: Path, progress: Any = None) -> Path:
        url = self._url_for(spec)
        dest.parent.mkdir(parents=True, exist_ok=True)
        existing = dest.stat().st_size if dest.exists() else 0
        headers = {"Range": f"bytes={existing}-"} if existing else {}
        header_name = "Content" + "-" + "Length"
        try:
            with create_client() as client, client.stream("GET", url, headers=headers) as resp:
                if existing and resp.status_code == 416:
                    # The partial file is stale (longer than the resource, or
                    # the resource changed). Start over rather than failing.
                    self._logger.debug(
                        "Stale partial file for %s (HTTP 416); restarting download", spec.name
                    )
                    resp.close()
                    dest.unlink(missing_ok=True)
                    return self.download(spec, dest, progress)
                resp.raise_for_status()
                # Only append when the server actually honored the Range
                # request (206). A server that ignores it answers 200 with the
                # whole body, and appending that to the partial file silently
                # produces a corrupt artifact of size existing + full.
                resumed = existing > 0 and resp.status_code == 206
                if existing and not resumed:
                    self._logger.debug(
                        "Range not honored for %s (HTTP %s); restarting download",
                        spec.name,
                        resp.status_code,
                    )
                    existing = 0
                total = int(resp.headers.get(header_name, 0)) + existing
                if progress is not None:
                    progress.start(total=total, desc=f"Download {spec.name}")
                mode = "ab" if resumed else "wb"
                with dest.open(mode) as fh:
                    for chunk in resp.iter_bytes(self._chunk_size):
                        fh.write(chunk)
                        if progress is not None:
                            progress.update(len(chunk))
                if progress is not None:
                    progress.finish(desc=f"Downloaded {spec.name}")
        except Exception as exc:
            raise DownloadError(spec.name, reason=str(exc)) from exc
        return dest

    def pull(self, ref: ModelRef, progress: Any = None) -> Any:
        raise DownloadError(
            ref.name, reason="HttpDownloader requires a spec + dest, use download()."
        )

    @staticmethod
    def _url_for(spec: ModelSpec) -> str:
        """Resolve the download URL from the default model variant."""
        variant = next(
            (variant for variant in spec.variants if variant.tag == spec.default_tag),
            None,
        )

        if variant is None or not variant.download_url:
            raise DownloadError(
                spec.name,
                reason=f"No download_url for variant '{spec.default_tag}'.",
            )

        return variant.download_url


__all__ = ["HttpDownloader"]
