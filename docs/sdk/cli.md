# CLI Reference

All ModelDock CLI commands.

---

## Entry Point

```bash
modeldock
python -m modeldock
```

---

## Commands

### Load

```bash
modeldock load <model> [--backend ollama] [--tag 8b]
```

Auto-install if missing, then return a ready client.

---

### Install

```bash
modeldock install <model>...
```

Explicit download of one or more models.

---

### Install Category

```bash
modeldock install-category <category>
```

Bulk install recommended models for a category (e.g., `coding`, `vision`).

---

### List

```bash
modeldock list
```

Browse the catalog.

---

### Installed

```bash
modeldock installed
```

Models present locally.

---

### Search

```bash
modeldock search <query>
```

Search by name, capability, or category across the live sources for the active
backend. Each result shows a **Source** column (e.g. `Ollama Official`,
`Hugging Face`) so you can see where a model comes from — you never need to
know which source holds it.

---

### Info

```bash
modeldock info <model>
```

Sizes, capabilities, variants, and the **Source** the metadata came from.

---

### Sources

```bash
modeldock sources           # list active model sources + status
modeldock sources refresh   # force live sources to re-fetch (bypass cache TTL)
```

`sources` reports every model source feeding discovery — its trust level
(`official` / `verified` / `community` / `bundled` / `custom`), whether it is
`live` or `static`, the backend it serves, and its current model count.
`sources refresh` forces each live source to re-fetch immediately instead of
waiting for its 24-hour discovery-cache TTL.

Example:

```text
                          Model Sources
+---------------------------------------------------------------+
| Source          | Trust    | Kind | Backend | Models | Status |
|-----------------+----------+------+---------+--------+--------|
| Ollama Official | official | live | ollama  |    238 | ready  |
+---------------------------------------------------------------+
```

---

### Recommend

```bash
modeldock recommend [--task coding]
```

Guided pick for a task.

---

### Update

```bash
modeldock update <model>...
```

Pull newer tag (destructive: removes then re-downloads).

---

### Remove

```bash
modeldock remove <model>...
```

Uninstall a model.

---

### Cache

```bash
modeldock cache status
modeldock cache clean
modeldock cache path
```

Manage the **artifact** cache (downloaded files). This is distinct from the
**discovery** cache that `sources refresh` reloads — see
[Discover Models](../user-guide/discover.md).

---

### Config

```bash
modeldock config show
modeldock config set <key> <value>
```

View or change configuration.

---

## Global Flags

| Flag | Description |
|------|-------------|
| `--backend` | Runtime backend |
| `--config-path` | Custom config file path |
| `--log-level` | `DEBUG`/`INFO`/`WARNING`/`ERROR` |
| `--no-progress` | Disable progress bars |
| `--yes` | Skip confirmation prompts |
| `--version` | Show version |
| `--help` | Show help |

---

## Next Steps

- [Python API](python-api.md) — SDK reference
- [Configuration](../user-guide/configuration.md) — config options
