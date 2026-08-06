# Release notes — Visual Evidence Gateway v0.5.0

Visual Evidence Gateway is a local, read-only MCP server for text-first agents. It exposes one tool, `vision.inspect`, and uses the local Codex CLI with explicit `gpt-5.6-luna` and ChatGPT authentication by default.

The default configuration stores no API key, does not enable verifier or fallback backends, and fails instead of silently changing the model or billing path.

## Changes since `vision-bridge-mcp` v0.4.1

- Renamed the project to `visual-evidence-gateway` because the previous name collided with an existing project.
- Added model-identity verification for the Codex CLI backend.
- Removed API-key, base-URL, organization, project, Anthropic, and Gemini variables from ChatGPT-mode child processes.
- Masked local paths in error and refusal output.
- Fixed Windows junction/reparse handling.
- Made installer SHA-256 verification mandatory and added rollback on setup failure.
- Added release gates for strict JSON Schema, cache hits without backend calls, fresh-cache runs, and path-security negatives.
- Fixed Windows wheel installation and PyInstaller dependency issues in CI.

## Validation summary

Windows 11 x64 received the full live validation run:

- ChatGPT-authenticated `gpt-5.6-luna` probes;
- six image fixture types;
- path and file-type security negatives;
- cache and Schema checks;
- official MCP SDK client interoperability over stdio;
- installer simulation;
- a standalone PyInstaller binary completing a live probe.

macOS and Linux installers were covered by POSIX integration tests and CI. GitHub Actions built Linux x86_64/arm64, macOS x86_64/arm64, and Windows x86_64 artifacts.

## Known boundaries

- Codex Desktop has not yet been manually verified as the MCP host after restart.
- npm Codex CLI 0.146.1 on the validation Windows machine could not complete stdio MCP tool calls; protocol interoperability was tested with the official MCP SDK client.
- Windows ARM64 has no prebuilt binary.
- Release binaries are not code-signed.
- Luna access and latency vary by account, region, workspace, and service load.
- ModLens was not run because the external Antigravity CLI login was not configured.

## Install

Windows PowerShell:

```powershell
irm https://raw.githubusercontent.com/scy7796/visual-evidence-gateway/main/install.ps1 | iex
```

macOS / Linux:

```bash
curl -fsSL https://raw.githubusercontent.com/scy7796/visual-evidence-gateway/main/install.sh | sh
```

Prerequisite: the official Codex CLI (`npm install -g @openai/codex`) signed in with ChatGPT.
