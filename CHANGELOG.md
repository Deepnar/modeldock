# Changelog

All notable changes to ModelDock will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

`llama.cpp`: support GGUF model path resolution. `llama-server` reports the
filesystem path it was launched with as the model id on `/v1/models` (e.g.
`/models/llama-3-8b.Q4_K_M.gguf`, or a Windows path with a drive letter), not
a bare alias. `LlamaCppRuntime` now parses these ids without corrupting
Windows drive-letter colons, and `is_installed()`/`run()`/`pull()` match a
user-supplied filename (with or without the `.gguf` extension) against the
full path llama-server reports, instead of requiring an exact string match.

### Fixed

- `LlamaCppRuntime.list_installed()` no longer mis-parses a Windows GGUF path
  (`C:\models\model.gguf`) by splitting on the drive letter's colon
- `LlamaCppRuntime.is_installed()` now matches a bare GGUF filename (with or
  without extension) against the full path llama-server reports, so
  `run()`/`pull()`/`get_model_client()` no longer falsely report a loaded
  model as not installed

---

Registry internals refactor — no behavior change. Groundwork for adding new
live catalog sources (e.g. Hugging Face for LM Studio/llama.cpp) without
duplicating caching/indexing logic per source.

### Added

- `CachedCatalogRegistry` (`adapters/registry/base.py`) — shared fetch →
  cache → index pipeline and `RegistryPort` implementation for live catalog
  sources
- `common/catalog_cache.py` — generic TTL'd JSON disk cache (extracted from
  `ollama_library.py`)
- `CatalogProvider` port (`ports/catalog_provider.py`) — the fetch/parse
  contract future live catalog sources implement

### Changed

- `OllamaLibraryRegistry` now builds on `CachedCatalogRegistry` instead of
  duplicating the fetch/cache/index/`RegistryPort` logic inline; scraping,
  auto-detection, and caching behavior are unchanged

---

Live GGUF catalog: LM Studio and llama.cpp category/capability suggestions now
come from the Hugging Face Hub instead of a hand-maintained static list (or,
for llama.cpp, nothing at all).

### Added

- `HuggingFaceCatalogProvider` (`adapters/registry/huggingface_catalog.py`) —
  live catalog built on `CachedCatalogRegistry` that queries the Hugging Face
  Hub API (`filter=gguf`) for GGUF-format models, cached 24h; LM Studio and
  llama.cpp share one on-disk cache since both address the same GGUF universe
- `LlamaCppRuntime.models_for_category`/`models_for_capability` — llama.cpp
  had no catalog of any kind before; category/capability installs previously
  fell back to the shared Ollama-tag catalog, whose names are not valid
  `--hf-repo` coordinates

### Changed

- `LMStudioRuntime.models_for_category`/`models_for_capability` now query the
  live Hugging Face catalog first, falling back to the existing curated
  `lmstudio_catalog.py` table only when the Hub is unreachable and no cache
  exists yet — suggestions still work fully offline, they just may be a
  shorter, point-in-time list instead of the live one
- `LMStudioRuntime`/`LlamaCppRuntime` accept an optional `cache_dir` argument
  (defaults to the standard ModelDock cache directory)

---

Composite catalog: general discovery (`search`/`list`/`recommend`) now spans
every source relevant to the active backend, not just Ollama's.

### Added

- `CompositeRegistry` (`adapters/registry/composite.py`) — merges an ordered
  list of `RegistryPort` sources; earlier sources win on a name collision,
  `get()` returns the first source that resolves the reference

### Changed

- `ModelManager._resolve_registry` under `catalog_source="auto"` (the
  default) now merges the active backend's own live catalog with the general
  one when it has one — LM Studio/llama.cpp get a `CompositeRegistry` of
  `[HuggingFaceCatalogProvider, <ollama-or-bundled>]`, so `md.search()`/
  `md.list()`/`md.recommend()` surface models that backend can actually
  install. Ollama (and any backend without its own catalog) is unaffected —
  no composite is built, exactly as before. `catalog_source="ollama"` /
  `"bundled"` remain explicit single-source opt-outs with no merge and no
  extra network calls, unchanged from before

---

Third-party catalog plugins: live catalog sources are now as pluggable as
runtimes, via the same entry-point mechanism.

### Added

- `CatalogProviderRegistry` (`adapters/registry/catalog_registry.py`) —
  resolves a `RuntimeBackend` to its own live catalog: built-ins (Hugging
  Face for LM Studio/llama.cpp) plus third-party plugins discovered via the
  `modeldock.catalog_providers` entry-point group, mirroring how
  `RuntimeRegistry` already discovers third-party `modeldock.runtimes`
  plugins. A plugin is a callable `(cache_dir: Path) -> RegistryPort`; entry
  points take priority over built-ins, so a plugin can also replace the
  shipped Hugging Face provider

### Changed

- `ModelManager._resolve_backend_catalog` now resolves through
  `CatalogProviderRegistry` instead of hardcoding
  `HuggingFaceCatalogProvider`/a fixed backend allowlist — behavior for LM
  Studio/llama.cpp is unchanged, but any backend with a registered catalog
  plugin (built-in or third-party) is now picked up automatically

## [0.1.3] - 2026-07-19

Dynamic catalog: replaced static `catalog.json` with live scraping of ollama.com.

### Added

- `OllamaLibraryRegistry` adapter — scrapes `ollama.com/library` for the full model list, auto-detects categories and capabilities, and caches locally for offline use
- `catalog_source` config setting (`"auto"` | `"ollama"` | `"bundled"`) to control which registry is used
- `MODELDOCK_CATALOG_SOURCE` environment variable support
- Local catalog cache (`<cache_dir>/catalog_cache.json`) with 24-hour TTL

### Changed

- `ModelManager` now defaults to `OllamaLibraryRegistry` (dynamic) instead of `BundledRegistry` (static)
- Auto-detection rules: model name patterns and HTML capability tags determine `Category` and `Capability`
- `Architecture.md` updated to reflect dynamic catalog design

### Removed

- Deleted `src/modeldock/data/catalog.json` — no longer needed
- Removed `[tool.setuptools.package-data]` from `pyproject.toml`

### Deprecated

- `BundledRegistry` is now a fallback only, used when `catalog_source="bundled"` or when the dynamic catalog fails and no cache exists

### Tests

- 32 new tests for `OllamaLibraryRegistry` (HTML scraping, auto-detection, cache, network fallback)
- BundledRegistry tests skipped when `catalog.json` is not present

### Contributors

- @himanshu231204

---

## [0.1.2] - 2026-07-19

Patch fix for `catalog.json` not being included in the installed package.

### Fixed

- **Catalog data missing** — added `[tool.setuptools.package-data]` to `pyproject.toml` so `catalog.json` is bundled in the wheel/sdist. Previously the file was silently excluded, causing `ModelNotFoundError: 'catalog.json not found in package data'` at runtime.

---

## [0.1.1] - 2026-07-19

Patch release hardening the Ollama runtime and SDK ahead of broader adoption.

### Added

- `modeldock.run()` SDK entry point for single-prompt completions and an interactive REPL against the active runtime (#159)
- `RuntimePort.status()` reporting runtime availability and execution device (CPU/GPU), surfaced via `ModelManager.runtime_status()` and the `load` CLI (#11)
- `CachePort.path()` / `FilesystemCache.path()` / `CacheService.path()` returning the real cache directory (#158)
- `ModelSpec.from_ref` / `ModelInfo.from_ref` fallbacks so `load`/`info`/`install` work for installed models not present in the bundled catalog (#158)
- `PullResult.already_present` flag; `BaseRuntime.pull()` is now idempotent and skips re-downloading already-installed models (#161)
- `ModelRef.is_cloud` to identify cloud/subscription models (tag contains `cloud`)

### Changed

- SDK functions (`load`, `install`, `install_category`, `update`, `remove`, `verify`, `run`) now route the `backend` argument to the selected runtime (#159)
- `info()` surfaces installed tags for locally-installed models (#159)
- `ModelManager.update()` now requires `confirm=True` (it removes then re-downloads) and rejects cloud models (#160)
- `CachePort.clean()` / `FilesystemCache.clean()` / `CacheService.clean()` are safe by default (only corrupt/partial entries removed) and accept `force=True` to wipe all (#160)

### Fixed

- `OllamaRuntime.remove()` no longer hangs on cloud/subscription models; it short-circuits with a clear `DownloadError` (#160)
- Catalog fallback for `load`/`info`/`install` when a model is installed but absent from the bundled catalog (#158)

### Documentation

- README marks Ollama as fully supported; added author credit (#161)
- New `docs/ollama-sdk.md` SDK guide for using ModelDock with Ollama

### Contributors

- @himanshu231204

---

## [0.1.0] - 2026-07-18

Initial pre-release. Documentation and package skeleton only; no implementation
code yet.

### Added

- Project documentation set: `PROJECT.MD`, `Architecture.md`, `AGENT.md`, `QUICKSTART.md`, `Development.md`, `CONTEXT.md`, `INSTRUCTIONS.md`, `RELEASE.md`
- Package skeleton (`src/modeldock/`) following Clean Architecture: `domain`, `ports`, `core`, `adapters`, `cli`, `common`, `data`
- `pyproject.toml` with runtime/dev dependencies, `ollama`/`dev` extras, console script, and `modeldock.runtimes` entry point
- Public SDK surface (`modeldock`) and Typer-based CLI (`modeldock`) with Ollama runtime adapter
- GitHub release workflow (`.github/workflows/release.yml`) using `uv`, with 3-way version consistency check and PyPI publish
- PR template (`.github/PULL_REQUEST_TEMPLATE.md`)
- Contributor community files: `README.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `SUPPORT.md`, issue templates, `CODEOWNERS`

### Changed

- Renamed `PROBLEM.MD` to `PROJECT.MD` (product intent doc)

---

## Versioning

This project follows [Semantic Versioning](https://semver.org/):

- **MAJOR**: Incompatible API changes
- **MINOR**: Backward-compatible new functionality
- **PATCH**: Backward-compatible bug fixes

## Links

[0.1.3]: https://github.com/OpenAgentHQ/modeldock/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/OpenAgentHQ/modeldock/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/OpenAgentHQ/modeldock/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/OpenAgentHQ/modeldock/releases/tag/v0.1.0
