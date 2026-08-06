# Visual Evidence Gateway v0.5.0

Visual Evidence Gateway is a local, read-only MCP server for text agents. It exposes `vision.inspect` and uses the local Codex CLI with explicit `gpt-5.6-luna` and ChatGPT authentication by default.

The default configuration stores no API key. Verifier and fallback backends are off. If the configured model or authentication route is unavailable, the request fails.

## Changes from v0.4.1

The project was renamed from `vision-bridge-mcp` because another project already used that name.

This release also:

- checks the model identity reported by the Codex CLI transcript;
- removes API-key, base-URL, organization, project, Anthropic, Gemini, and Codex API-key variables from ChatGPT-mode child processes;
- masks local paths in errors and refusals;
- rejects Windows junction and reparse paths without crashing;
- requires installer SHA-256 verification and rolls back the binary when setup fails;
- adds release checks for strict JSON Schema, cache hits without backend calls, fresh-cache runs, and path-security negatives;
- fixes Windows wheel installation and a missing PyInstaller dependency in CI.

## Validation

The live Windows 11 x64 validation covered ChatGPT authentication, ten real Luna probes, six image fixture types, path-security negatives, cache behavior, strict backend Schema, the standalone binary, and installer rollback.

The same-machine image comparison produced these results:

| Metric | Native Codex attachment | Gateway |
|---|---:|---:|
| Tasks completed | 6/6 | 6/6 |
| Expected fields fully present | 4/6 | 6/6 |
| Median end-to-end time | 16.6 s | 20.2 s |
| Median returned length | 602 characters | 62 characters |

These six synthetic fixtures do not establish general accuracy or speed. The gateway was slower on the validation machine.

Automated checks reported 197 passed tests and 9 platform-gated skips. Ruff, compileall, source audit, wheel and sdist builds, twine checks, clean installs, and source-ZIP retesting passed.

MCP protocol interoperability was tested over stdio with the official MCP SDK client. Codex Desktop has not been manually verified as the host. The validation Windows machine also reproduced a Codex CLI 0.146.1 stdio MCP call failure against a trivial server.

## Release assets

The Release contains binaries for Windows x86_64, Linux x86_64, Linux ARM64, macOS x86_64, and macOS ARM64, along with the wheel, sdist, source archive, and SHA-256 manifest.

Windows ARM64 has no prebuilt binary. Release binaries are not code-signed.

## Install

Prerequisite: Codex CLI signed in with ChatGPT.

Windows PowerShell:

```powershell
irm https://raw.githubusercontent.com/scy7796/visual-evidence-gateway/main/install.ps1 | iex
```

macOS or Linux:

```bash
curl -fsSL https://raw.githubusercontent.com/scy7796/visual-evidence-gateway/main/install.sh | sh
```

See [`FINAL_RELEASE_DECISION.md`](FINAL_RELEASE_DECISION.md) for the complete validation record and current boundaries.
