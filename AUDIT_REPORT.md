# Visual Evidence Gateway v0.5.0 — focused release audit

## Decision

The installation design is materially simpler than v0.4.0 and is suitable for a release candidate. It is not yet a final public release until GitHub Actions builds the platform binaries and a real Codex/ChatGPT account passes the Luna validation gate.

## Main change

End users no longer install a Python package. The repository publishes one `visual-evidence-gateway` executable per supported OS/architecture. That executable exposes four subcommands: `setup`, `serve`, `healthcheck`, and `probe`. The installer downloads the matching binary, checks SHA-256, and invokes setup.

## Positive findings

- Removed Python, venv, pip and package-manager PATH complexity from the normal install path.
- Removed automatic installation of Codex from the project installer. Missing Codex now fails with an official installation instruction rather than executing a second remote installer implicitly.
- Standalone execution registers the exact absolute executable path with `serve`, avoiding PATH-dependent MCP startup failures.
- Existing configuration remains outside the package and contains no credentials.
- ChatGPT subscription authentication, explicit Luna model selection, API-billing environment stripping, read-only sandboxing, structured-output checks, and failure-closed behavior remain unchanged.
- POSIX installer has an end-to-end local integration test, not only static string assertions.

## Residual risks

- GitHub Releases and the repository's release permissions are the installer trust boundary. SHA-256 detects corruption but does not protect against a compromised publisher account.
- macOS binaries are not code-signed or notarized by this repository configuration. Gatekeeper behavior must be documented or signing added before broad distribution.
- Windows binaries are not Authenticode-signed. SmartScreen warnings are possible.
- PyInstaller collection of the MCP SDK must be verified in the actual GitHub Actions run.
- The repository and package name still require a separate collision/branding decision.

## Release condition

Do not advertise “one-click verified Luna vision” until all platform build jobs pass and at least one clean user machine completes `visual-evidence-gateway setup` with a successful randomized pixel probe and a host-level `vision.inspect` call.
