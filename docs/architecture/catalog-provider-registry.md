# Catalog Provider Registry

How ModelDock resolves a runtime backend to its own live model catalog — and
how a third-party package plugs in a new one.

---

## The Problem It Solves

ModelDock's general catalog is scraped from `ollama.com/library`, so its
names are Ollama tags (`llama3`, `qwen2.5-coder`). Backends that address
models a different way — LM Studio and llama.cpp both use Hugging Face
coordinates (`publisher/repo`) — can't be served by that catalog directly.
Without a mechanism for "this backend has its own online catalog," discovery
(`md.search()`, `md.list()`, `md.recommend()`) would either miss those
backends entirely or hand back names the active runtime can't install.

`CatalogProviderRegistry` (`adapters/registry/catalog_registry.py`) is the
piece that answers *"does this backend have a live catalog, and if so, how
do I build one?"* — for both backends ModelDock ships and ones it's never
heard of.

---

## The Contract

A catalog provider is any callable matching this shape:

```python
Callable[[Path], RegistryPort]
```

Give it a cache directory, get back a `RegistryPort` — something with
`search`, `get`, `by_category`, `recommend`, and `list_all`. That's the same
interface every other registry in ModelDock already implements (see
[Port Interfaces](ports.md)), so nothing downstream needs to know or care
whether a given catalog is Ollama's scraper, the bundled JSON, or a
third-party plugin.

In practice this callable is usually one of two things:

- A plain function: `def build_catalog(cache_dir: Path) -> RegistryPort: ...`
- A class whose constructor takes only `cache_dir`

---

## Built-in Providers

```python
_BUILTIN: Dict[RuntimeBackend, Callable[[Path], RegistryPort]] = {
    RuntimeBackend.LM_STUDIO: lambda cache_dir: HuggingFaceCatalogProvider(
        cache_dir, RuntimeBackend.LM_STUDIO
    ),
    RuntimeBackend.LLAMACPP: lambda cache_dir: HuggingFaceCatalogProvider(
        cache_dir, RuntimeBackend.LLAMACPP
    ),
}
```

Both point at `HuggingFaceCatalogProvider` (`adapters/registry/huggingface_catalog.py`),
which queries the Hugging Face Hub API (`filter=gguf`) live and caches the
result for 24 hours. LM Studio and llama.cpp share one on-disk cache file —
they're both GGUF consumers, so one fetch serves both, just tagged with a
different `RuntimeBackend` in the resulting `ModelSpec.backend_hints`.

`HuggingFaceCatalogProvider` itself is built on `CachedCatalogRegistry`
(`adapters/registry/base.py`), the shared fetch → cache → index →
`RegistryPort` pipeline every live catalog source in ModelDock uses —
including `OllamaLibraryRegistry`. A new provider only has to implement
*fetching and parsing*; caching, indexing, and the `RegistryPort` methods
come for free.

Backends with no catalog of their own — Ollama, which already names models
the shared catalog understands — simply have no entry here.

---

## Entry-Point Plugin Discovery

This mirrors `RuntimeRegistry`'s existing `modeldock.runtimes` mechanism
exactly (see [Runtime Adapters](runtime-adapters.md)) — same shape, same
group-naming convention, different group name:

```toml
[project.entry-points."modeldock.catalog_providers"]
vllm = "modeldock_vllm.catalog:build_catalog"
```

The entry point's **name** must match a `RuntimeBackend` value (`vllm`,
`jan`, `gpt4all`, or a future one); the entry point's **target** is the
`(cache_dir) -> RegistryPort` callable described above.

```python
# modeldock_vllm/catalog.py
from pathlib import Path
from modeldock.ports.registry import RegistryPort

def build_catalog(cache_dir: Path) -> RegistryPort:
    return VllmLiveCatalog(cache_dir)
```

At construction, `CatalogProviderRegistry` scans
`importlib.metadata.entry_points(group="modeldock.catalog_providers")`:

```python
class CatalogProviderRegistry:
    def __init__(self) -> None:
        _register_builtins()
        self._entry_points: Dict[RuntimeBackend, Callable[[Path], RegistryPort]] = {}
        self._discover_entry_points()

    def get(self, backend: RuntimeBackend, cache_dir: Path) -> Optional[RegistryPort]:
        factory = self._entry_points.get(backend) or _BUILTIN.get(backend)
        if factory is None:
            return None
        try:
            return factory(cache_dir)
        except Exception:
            return None  # broken/unreachable catalog degrades to "none", not a crash
```

**Entry points take priority over built-ins** — a `pip install
modeldock-lmstudio-catalog` package registering the `lmstudio` name would
*replace* the shipped Hugging Face provider, not conflict with it.

Two failure modes are handled without ever raising past `get()`:

- A malformed plugin (bad entry point name, `.load()` throws) is logged and
  skipped during discovery — one broken plugin never breaks catalog
  resolution for every other backend.
- A plugin that loads fine but fails when *called* (network down, bad
  config) degrades to `None` for that one `get()` call, exactly like a
  missing catalog.

---

## Resolution Flow

```
ModelManager.__init__
  └─ _resolve_registry(cfg)                     # catalog_source == "auto"
       ├─ _resolve_auto_registry(cfg)            # live Ollama, falls back to bundled
       └─ _resolve_backend_catalog(cfg)
            └─ CatalogProviderRegistry().get(self._backend, cfg.cache_dir)
                 ├─ entry-point plugin, if registered for this backend
                 ├─ else a built-in (Hugging Face for LM Studio/llama.cpp)
                 └─ else None (backend has no catalog of its own)
       └─ merge via CompositeRegistry([backend_catalog, base])   # only if backend_catalog is not None
```

`CompositeRegistry` (`adapters/registry/composite.py`) is what makes the
merge additive rather than a replacement: `search`/`list_all`/`by_category`/
`recommend` union every source's results (earlier source wins on a name
collision), and `get()` returns the first source that resolves the
reference. So a plugin's models sit *alongside* the general catalog, not
instead of it.

`catalog_source="ollama"` and `"bundled"` remain explicit single-source
opt-outs — no `CatalogProviderRegistry` lookup, no extra network call,
unchanged regardless of which plugins are installed.

---

## Adding a New Catalog Provider

1. Implement a `RegistryPort` — `search`, `get`, `by_category`, `recommend`,
   `list_all`. Extend `CachedCatalogRegistry` if you want the shared
   fetch/cache/index pipeline for free (recommended for anything hitting a
   live source).
2. Expose a `(cache_dir: Path) -> RegistryPort` factory — a function, or
   just the class itself if its constructor takes only `cache_dir`.
3. Register it:
   ```toml
   [project.entry-points."modeldock.catalog_providers"]
   <backend-name> = "your_package.catalog:build_catalog"
   ```
4. Nothing else. No core edits — `ModelManager` picks it up automatically
   the next time it resolves a registry for that backend.

See `adapters/registry/huggingface_catalog.py` for a complete real example,
and [Adding New Runtimes](../contributing/new-runtime.md) for how this fits
alongside registering the runtime adapter itself.

---

## Why a Separate Registry from `RuntimeRegistry`?

`RuntimeRegistry` resolves a backend to *how to run/manage models*
(`RuntimePort`: pull, remove, list installed, run). `CatalogProviderRegistry`
resolves a backend to *where to discover models* (`RegistryPort`: search,
list, recommend). A backend can have one without the other — Ollama has a
runtime and no catalog provider of its own (it uses the general catalog
directly); a hypothetical catalog-only integration could register a live
source without shipping a full runtime adapter. Keeping them separate keeps
each registry's entry-point group unambiguous about what kind of plugin it
expects.

---

## Next Steps

- [Design Overview](overview.md) — the general catalog design
- [Runtime Adapters](runtime-adapters.md) — the parallel `modeldock.runtimes` mechanism
- [Port Interfaces](ports.md) — the `RegistryPort` contract
- [Adding New Runtimes](../contributing/new-runtime.md) — contributor guide, Step 6
