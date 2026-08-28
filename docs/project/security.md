# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x (pre-release) | Yes |
| < 0.1.0 | No |

---

## Reporting a Vulnerability

If you discover a security vulnerability, report it privately. **Do NOT report through public GitHub issues.**

Send an email to **opensource@openagenthq.com** with:

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)
- Your contact information

### Response Timeline

| Step | Timeline |
|------|----------|
| Acknowledgment | Within 48 hours |
| Initial Assessment | Within 1 week |
| Fix Released | Within 30 days (critical issues) |

---

## Security Best Practices

### For Users

- Keep ModelDock up to date (`pip install -U modeldock`)
- Use environment variables for secrets; never hardcode
- Download models only from trusted runtimes/registries
- Check a model's provenance before installing — `search`/`info` show the
  `Source` it came from, and `modeldock sources` lists every active source with
  its trust level (`official` / `verified` / `community` / `bundled` /
  `custom`). ModelDock never hides where an artifact originates.

### For Contributors

- Follow secure coding practices
- Never commit secrets or `.env` files
- Raise typed `ModelDockError` subclasses — never swallow silently
- Run `bandit -r src` as part of local checks

---

## Contact

- **Email**: opensource@openagenthq.com
