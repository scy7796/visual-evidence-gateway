# Installation simplification review — v0.5.0

## Previous public path

The v0.4.0 installer looked like one command, but internally required Python 3.10+, created a private virtual environment, upgraded pip, installed the package, optionally installed Codex, registered MCP, and then ran health and pixel checks. The number of hidden dependency and PATH failure points was too high for a small vision plug-in.

## v0.5.0 public path

The normal installer now requires only an existing Codex CLI installation. It:

1. detects OS and CPU architecture;
2. downloads one matching standalone executable from GitHub Releases;
3. verifies the release SHA-256 manifest when available;
4. runs `visual-evidence-gateway setup`, which confirms ChatGPT login, writes credential-free defaults, registers `visual-evidence-gateway serve` through `codex mcp add`, checks connectivity, and runs one real Luna pixel probe.

The user does not need Python, a virtual environment, pip, pipx, uv, or a Node package for Visual Evidence Gateway itself. Node is only one official way to install Codex.

## User commands

Windows:

```powershell
irm https://raw.githubusercontent.com/scy7796/visual-evidence-gateway/main/install.ps1 | iex
```

macOS/Linux:

```bash
curl -fsSL https://raw.githubusercontent.com/scy7796/visual-evidence-gateway/main/install.sh | sh
```

Fast registration without consuming a Luna probe:

```bash
curl -fsSL https://raw.githubusercontent.com/scy7796/visual-evidence-gateway/main/install.sh | sh -s -- --skip-probe
```

## Reliability and security decisions

- The installer no longer installs Codex implicitly. If Codex is missing, it stops and shows the official installation command.
- MCP registration uses an absolute executable path, so the server does not depend on the user's PATH after installation.
- The single binary registers itself with the `serve` subcommand; there are no separate runtime scripts to locate.
- Installer tests exercise a local fake Release, checksum verification, binary placement, and setup invocation end to end.
- The installer does not read, copy, or package Codex credentials.
- Real Luna readiness remains separate from file installation. A skipped or failed probe cannot be presented as a verified visual connection.

## Remaining release gate

The cross-platform executables must still be built by GitHub Actions and smoke-tested on Windows x64, Linux x64/arm64, and macOS Intel/arm64. A real user machine must also complete ChatGPT login, the randomized Luna probe, and host-level MCP discovery before the release is marked final.
