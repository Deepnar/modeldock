# llama.cpp Integration

ModelDock talks to llama.cpp through `llama-server`'s OpenAI-compatible local
API. Most of ModelDock works identically across backends; this page documents
where llama.cpp differs and why.

## Quick start

```python
import modeldock as md

mgr = md.Manager(backend="llamacpp")

mgr.installed()          # the single model llama-server currently has loaded
mgr.runtime_status()     # availability + device (always "unknown" here)
```

```bash
modeldock installed --backend llamacpp
```

## Backend-specific quirks

### One model per process

`llama-server` is started with a single `-m <model.gguf>` flag and serves
exactly that model for the lifetime of the process — there is no daemon
managing a catalog of models the way Ollama does, and no local server API to
download, swap, or unload one the way LM Studio has. `list_installed()`
therefore returns at most one `ModelRef`: whatever `llama-server` reports at
`/v1/models`.

### Category/capability suggestions query the Hugging Face Hub live

llama.cpp has no catalog of its own — it loads a GGUF file directly, and can
fetch one straight from a Hugging Face repo via `--hf-repo`/`--hf-file`. The
shared catalog's names come from `ollama.com/library` and are not valid
`--hf-repo` coordinates, so `suggest_category()`/`suggest_capability()`
resolve through the same live Hugging Face GGUF listing LM Studio uses
(`adapters/registry/huggingface_catalog.py`), cached for 24 hours:

```python
mgr.suggest_category("coding")     # -> [ModelRef, ...] naming real HF repos
```

Unlike LM Studio, there is no curated fallback list here — when the Hub is
unreachable and no cache exists yet, suggestions are an empty list rather
than a guess. `install_category()` still cannot actually download anything
(see below), but the repo names it reports in its `DownloadError` are now
real, pastable `--hf-repo` coordinates instead of Ollama tags that mean
nothing to `llama-server`.

General discovery gets the same treatment: with `catalog_source` left at its
default (`"auto"`), `mgr.list()`/`mgr.search()`/`mgr.recommend()` merge the
live Hugging Face catalog with the general Ollama-named one, so results
include real `--hf-repo` coordinates rather than only Ollama tags. Set
`catalog_source="bundled"` or `"ollama"` for a single, explicit source with
no live Hugging Face lookup.

### GGUF model path resolution

`llama-server` typically reports the *filesystem path* it was launched with
as the model `id` in `/v1/models` — e.g. `/models/llama-3-8b-instruct.Q4_K_M.gguf`
or, on Windows, `C:\models\llama-3-8b-instruct.Q4_K_M.gguf` — rather than a
bare alias. `LlamaCppRuntime` accounts for this in two ways:

- **Parsing**: path-shaped ids are wrapped as a `ModelRef` directly instead of
  going through the generic `name:tag` parser, so a Windows drive letter's
  colon is never mistaken for a tag separator.
- **Matching**: `is_installed()` (and therefore `run()`, `pull()`'s
  already-installed check, and `get_model_client()`) first tries an exact
  match, then falls back to comparing the bare filename with its `.gguf`
  extension stripped. This means you can refer to a loaded model by its
  filename alone, with or without the extension:

```python
mgr.run("llama-3-8b-instruct.Q4_K_M", prompt="hi")       # matches
mgr.run("llama-3-8b-instruct.Q4_K_M.gguf", prompt="hi")  # also matches
```

even though `llama-server` is actually reporting the full path it was
started with (`/models/llama-3-8b-instruct.Q4_K_M.gguf`).

### `install()` fails with an actionable message

Because there is no network API to fetch a model into a running server,
`install()`/`pull()` never succeeds — it raises `DownloadError` explaining
that you must stop the server and restart it against the GGUF file you want
(`llama-server -m <model.gguf>`, or `--hf-repo`/`--hf-file` to have
llama.cpp's own downloader fetch it from Hugging Face first). This is a
property of llama.cpp's server, not a ModelDock limitation.

`remove()` fails the same way — there is nothing to delete over the API. Stop
the server (and delete the GGUF file on disk) if you want to free the space.

### The server must be running

With `llama-server` stopped, `installed()` returns an empty list and
`is_available()` is `False` rather than raising, so discovery commands
degrade instead of crashing.

See [Configuration](../user-guide/configuration.md) for how the server URL is
resolved and how to point ModelDock at a non-default host. llama.cpp has no
vendor-standard host environment variable (unlike Ollama's `OLLAMA_HOST`), so
`MODELDOCK_LLAMACPP_HOST` / `LLAMACPP_HOST` are ModelDock's own convention;
the default is `http://localhost:8080`, `llama-server`'s default port.

### Device reporting

`runtime_status().device` always reports `unknown`. GPU offload (`-ngl`) is a
llama.cpp startup/compile-time concern, not something the server reports back
over its HTTP API, so there is nothing to infer GPU versus CPU placement from.

### `run()` works like any other backend

Once a model is loaded, `run()`/`modeldock run` streams chat completions from
`/v1/chat/completions` exactly as it does for Ollama and LM Studio.
