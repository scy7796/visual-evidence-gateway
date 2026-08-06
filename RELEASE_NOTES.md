# Release notes — Visual Evidence Gateway v0.5.0

## What this is

A local, read-only MCP server that lets text-first agents (DeepSeek, OpenCode, Pi, …) call one tool, `vision.inspect`, for controlled visual evidence. The default backend is the local Codex CLI with explicit `gpt-5.6-luna` and forced ChatGPT subscription authentication; no API key, no silent fallback, no verifier by default.

## Changes since vision-bridge-mcp v0.4.1

- **Renamed to Visual Evidence Gateway** (`visual-evidence-gateway` distribution, `visual_evidence_gateway` package, `visual-evidence-gateway` CLI/MCP name, `VISUAL_EVIDENCE_GATEWAY_*` env vars). The old `vision-bridge-mcp` name collided with an existing same-purpose project on GitHub/npm; migration notes are in the README.
- Transport-level model identity verification for the Codex CLI backend.
- Hardened ChatGPT-mode environment stripping (`OPENAI_BASE_URL`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY` now also blocked).
- Local-path masking in error/refusal output.
- Windows junction/reparse paths are rejected cleanly (crash fixed).
- Installers: mandatory SHA-256 verification, rollback on setup failure, explicit Windows ARM64 message.
- Pre-release validation kit: strict JSON-Schema gate, cache-hit no-backend-call gate, junction negative test, fresh-cache runs, official-MCP-client host gate.
- CI fixes: Windows wheel reinstall path, `typer` for the PyInstaller build.

## Verified platforms

- **Windows 11 x64**: full validation PASS (real Luna probes, six fixture types, security negatives, cache, schema, host MCP, installer simulation, PyInstaller single-file binary with real probe).
- **macOS/Linux**: installer integration test + CI matrix (python 3.10–3.13); binary builds run in GitHub Actions (linux x86_64/arm64, macOS x86_64/arm64, Windows x86_64).

## Not yet verified / boundaries

- Codex Desktop app host call through MCP (manual restart + call needed; npm CLI 0.146.1 on Windows cannot complete stdio MCP tool calls — see FINAL_RELEASE_DECISION.md).
- Windows ARM64 prebuilt binary (no GitHub-hosted runner).
- Binary signing (none; transport + SHA-256 only).
- Real-world latency on other accounts/regions (this machine: median ~21–25 s per visual call at validation time).
- ModLens comparison run (requires external Antigravity CLI login).

## Install

```powershell
irm https://raw.githubusercontent.com/scy7796/visual-evidence-gateway/main/install.ps1 | iex
```

```bash
curl -fsSL https://raw.githubusercontent.com/scy7796/visual-evidence-gateway/main/install.sh | sh
```

Prerequisite: official Codex CLI (`npm install -g @openai/codex`) signed in with ChatGPT.
