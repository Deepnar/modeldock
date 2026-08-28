# Production Readiness — Tier 1 Blockers

These are hard blockers that must be resolved before ModelDock can be considered
production-ready. Each causes data corruption, silent failures, or breaks user
environments. Fix in order.

---

## Task 1 — `ModelManager.install` transaction safety
**Issue:** #88  
**Label:** bug  
**File(s):** `src/modeldock/core/manager.py`, `src/modeldock/core/cache.py`

### Problem
A failed `verify()` after a download leaves a corrupted or partial entry in the
cache. The next `install` call may see it as installed and skip the download,
or it may surface confusing errors at runtime.

### Acceptance criteria
- [ ] Install is all-or-nothing: if verify fails, the cache entry is rolled back
- [ ] No partial/corrupt entries can survive a failed install
- [ ] Tests covering the rollback path with a fake downloader

---

## Task 2 — Cache: atomic writes to avoid corruption
**Issue:** #62  
**Label:** bug  
**File(s):** `src/modeldock/adapters/cache/filesystem.py`

### Problem
Downloads write directly to the final cache path. An interrupted download
(Ctrl-C, network drop, OOM kill) leaves a partial file that looks valid to
the cache layer but is corrupt.

### Acceptance criteria
- [ ] Write to a `.tmp` file, then atomically rename to the final path on success
- [ ] A partial `.tmp` file is cleaned up on next access or startup
- [ ] Tests that simulate interruption mid-write

---

## Task 3 — Downloader: checksum verification
**Issue:** #68  
**Label:** bug  
**File(s):** `src/modeldock/adapters/downloaders/http.py`, `src/modeldock/common/errors.py`

### Problem
No SHA-256 verification is performed after a download. Corrupt or tampered
weights are silently accepted and only fail later with confusing runtime errors.

### Acceptance criteria
- [ ] Verify SHA-256 digest from catalog metadata after every download
- [ ] Raise `DownloadError` with a retry suggestion on mismatch
- [ ] Tests with a mock server returning a bad digest

---

## Task 4 — `update` should preserve user config
**Issue:** #92  
**Label:** bug  
**File(s):** `src/modeldock/core/manager.py`, `src/modeldock/common/config.py`

### Problem
`update` removes then re-downloads a model, but may silently wipe any user
configuration associated with that model in the process — a data loss bug.

### Acceptance criteria
- [ ] User config is read and re-applied after the re-download
- [ ] Only model weights are refreshed; settings survive the update cycle
- [ ] Test asserting that settings are intact after `update`

---

## Task 5 — Never call `basicConfig` at import time
**Issue:** #107  
**Label:** bug  
**File(s):** `src/modeldock/common/logging.py`, all modules under `src/modeldock/`

### Problem
Calling `logging.basicConfig()` at import time hijacks the root logger of any
application that embeds ModelDock. This silently breaks user logging
configuration and violates the library contract.

### Acceptance criteria
- [ ] Audit every module for import-time `basicConfig` calls and remove them
- [ ] Logging is configured only when the CLI entry point or an explicit
  `configure()` call is made
- [ ] A test that imports `modeldock` and asserts the root logger has no
  handlers added by the package

---

## Task 6 — Consistent non-zero exit codes in CLI
**Issue:** #46  
**Label:** bug  
**File(s):** `src/modeldock/cli/commands/`, `src/modeldock/cli/app.py`

### Problem
Several CLI commands exit with code `0` on failure (model not found,
pull failed, verify failed). Scripts and CI pipelines cannot detect these
failures, silently treating them as success.

### Acceptance criteria
- [ ] `model-not-found` → exit 1
- [ ] `pull-failed` → exit 1
- [ ] `verify-failed` → exit 1
- [ ] All commands audited; no failure path exits 0
- [ ] CliRunner tests asserting the correct exit code for each failure case

---

## Task 7 — Fix or remove `HttpDownloader`
**Issue:** #185  
**Label:** bug  
**File(s):** `src/modeldock/adapters/downloaders/http.py`, `src/modeldock/domain/model.py`

### Problem
`HttpDownloader._url_for` reads `spec.download_url`, but `ModelSpec` has no
such field. Pydantic v2 silently drops unknown kwargs, so the attribute never
exists and every call raises `DownloadError("No download_url in spec.")`.
The adapter is vestigial — nothing in the codebase constructs it.

### Acceptance criteria
- [ ] **Option A:** Add `download_url` (per `ModelVariant`) to the domain model
  and wire `HttpDownloader` to read it correctly
- [ ] **Option B:** Remove `HttpDownloader` until a runtime actually needs
  direct-URL downloads, and add a note in `Architecture.md`
- [ ] Either way, `_url_for` must not depend on a field that cannot exist
- [ ] Tests covering whichever path is chosen

---

## Progress

| # | Task | Status |
|---|------|--------|
| 1 | Install transaction safety (#88) | `[ ] Not started` |
| 2 | Atomic cache writes (#62) | `[ ] Not started` |
| 3 | Checksum verification (#68) | `[ ] Not started` |
| 4 | `update` preserves config (#92) | `[ ] Not started` |
| 5 | No `basicConfig` at import (#107) | `[ ] Not started` |
| 6 | Consistent exit codes (#46) | `[ ] Not started` |
| 7 | Fix or remove `HttpDownloader` (#185) | `[ ] Not started` |
