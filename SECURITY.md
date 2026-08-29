# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x (pre-release) | Yes |
| < 0.1.0 | No |

ModelDock is in early (pre-1.0) development. The latest published version
receives security fixes.

## Reporting a Vulnerability

If you discover a security vulnerability within ModelDock, please report it
privately. **Do NOT report security vulnerabilities through public GitHub
issues.**

Send an email to **opensource@openagenthq.com** with:

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)
- Your contact information

### Response Timeline

- **Acknowledgment**: Within 48 hours
- **Initial Assessment**: Within 1 week
- **Fix Released**: Within 30 days (for critical issues)

### What to Expect

1. We acknowledge receipt of your report.
2. We confirm the vulnerability and determine its impact.
3. We develop and test a fix.
4. We release the fix and update the changelog.
5. We publicly disclose the vulnerability after the fix is released.

## Security Best Practices

### For Users

- Keep ModelDock and its dependencies up to date (`pip install -U modeldock`).
- Use environment variables for any secrets; never hardcode them.
- Download models only from trusted runtimes/registries.
- Review the dynamic catalog source (`ollama.com`) and any bundled registry sources.

### For Contributors

- Follow secure coding practices; validate input at boundaries.
- Never commit secrets or `.env` files (see `.gitignore`).
- Raise typed `ModelDockError` subclasses — never swallow errors silently.
- Run `bandit -r src` as part of local checks.
- Treat output from adapters as untrusted; see [Prompt-Injection & Untrusted Model Output](#prompt-injection--untrusted-model-output) below.

## Prompt-Injection & Untrusted Model Output

### Threat Model

ModelDock runtime adapters (Ollama, LM Studio, llama.cpp, etc.) relay data
from external processes and HTTP APIs. **All data returned by a model or
runtime API is untrusted by definition.** It may contain:

- Prompt-injection payloads designed to mislead downstream tooling.
- Malformed or adversarial strings that exploit parsers.
- Content crafted to escape the intended output context (HTML, shell, SQL).

### Rules

1. **Never execute model output.** Do not pass adapter responses to `exec()`,
   `eval()`, `subprocess`, `os.system()`, or any code-execution primitive.
2. **Never treat model output as trusted instructions.** If your application
   uses ModelDock within an agent or tool pipeline, model output must be
   validated and sandboxed before it influences control flow.
3. **Parse, don't interpret.** Adapter output should be parsed into typed
   domain objects (`ModelRef`, `PullResult`, `RunResult`) — not consumed as
   free-form text that drives logic.

### Guidance for Users

- Treat any text returned by a model as **untrusted user input**.
- Sanitise model output before displaying it in HTML, terminal, or log
  contexts to prevent injection (e.g., terminal escape-sequence attacks).
- Do not copy-paste model output into a shell without reviewing it.

### Guidance for Contributors

- Validate and sanitise all data at the adapter boundary before constructing
  domain objects.
- Never pass raw adapter responses to shell commands or string-interpolated
  queries.
- Add explicit `# Security: untrusted input` comments at trust boundaries in
  adapter code.
- See `src/modeldock/adapters/runtimes/base.py` for the canonical trust-
  boundary documentation.

### Guidance for Integrators

If you embed ModelDock in a larger agent, copilot, or automation pipeline:

- Apply output-escaping appropriate to your downstream context (HTML, SQL,
  shell, etc.).
- Do not grant model output the authority to invoke tools, modify files, or
  make network requests without an explicit human-in-the-loop approval step.
- Assume every string originating from an adapter response could be adversarial.

## Contact

For security-related questions or concerns, contact:
- **Email**: opensource@openagenthq.com

## Acknowledgments

We thank the researchers who responsibly disclose vulnerabilities to keep
ModelDock and its users safe.
