# Examples

Usage examples for **ModelDock** (`modeldock`), the lightweight Python-first
model manager for local LLMs.

## `modeldock-getting-started.ipynb`

A beginner-friendly, runnable Jupyter notebook that shows how to use the
ModelDock SDK to manage and talk directly to three local backends:

- **Ollama** — `ollama.Client` (Ollama SDK)
- **LM Studio** — `openai.OpenAI` (OpenAI-compatible server at `:1234`)
- **llama.cpp** — `openai.OpenAI` (OpenAI-compatible server at `:8080`)

### What it covers

1. The core mental model: ModelDock *manages* models and returns the runtime's
   **native client** — it does not run inference itself.
2. How ModelDock connects to each backend (HTTP to the local server, returns the
   right client type).
3. Discovery: `search` / `list` / `categories` / `installed` / `info` / `resolve`.
4. Raw per-backend inference (chat + streaming) for Ollama, LM Studio, llama.cpp.
5. A small `ModelDockChat` helper that hides the `ollama` vs `openai` difference
   so your own code is backend-agnostic.
6. Lifecycle ops: `install` / `update` / `remove` / `verify` / `cache`.

### Run it

```bash
pip install "modeldock[ollama]" openai jupyter
jupyter lab example/modeldock-getting-started.ipynb
# or
jupyter nbconvert --to notebook --execute example/modeldock-getting-started.ipynb
```

### Before you start

Edit the **`CONFIG`** cell at the top to set the model name (and host, if
non-default) for each backend you have installed. Every backend section is
**guarded**: if a backend's server isn't running, the cell prints setup
instructions instead of erroring — so you can open the notebook anywhere and run
only the parts you have.

| Backend | Start the server | Model name format |
|---|---|---|
| Ollama | `ollama serve` (or the desktop app) | tag, e.g. `llama3` |
| LM Studio | LM Studio → Local Server → Start | HF coordinate, e.g. `lmstudio-community/Qwen2.5-Coder-7B-Instruct-GGUF` |
| llama.cpp | `llama-server -m model.gguf --port 8080` | the loaded GGUF filename |

> Note: in v0.2.0, Ollama, LM Studio, and llama.cpp are all implemented. The
> `openai` SDK is **not** a ModelDock dependency but is required by the LM
> Studio and llama.cpp adapters.
