# Visual Evidence Gateway

Visual Evidence Gateway is a local MCP server that lets text-first agents inspect local images without moving the whole task to a multimodal agent.

It exposes one tool:

```text
vision.inspect(paths, query, mode="auto", rigor="normal")
```

The public default calls `gpt-5.6-luna` through the local Codex CLI and requires ChatGPT authentication. The project stores no account credentials or API keys. If Luna is unavailable, the request fails instead of silently switching to API billing or another model.

This is a community project, not an official OpenAI product. Model availability depends on the account, region, workspace, and client version.

[Chinese README](../README.md) · [Architecture](ARCHITECTURE.md) · [Security model](SECURITY_MODEL.md) · [Release validation](../FINAL_RELEASE_DECISION.md)

## Install

Prerequisite: Codex CLI signed in with ChatGPT.

```bash
npm install -g @openai/codex
codex
```

Windows PowerShell:

```powershell
irm https://raw.githubusercontent.com/scy7796/visual-evidence-gateway/main/install.ps1 | iex
```

macOS / Linux:

```bash
curl -fsSL https://raw.githubusercontent.com/scy7796/visual-evidence-gateway/main/install.sh | sh
```

The installer downloads the matching standalone binary, verifies its SHA-256 checksum, registers the MCP server by absolute path, checks the ChatGPT login, and runs a real image probe. The gateway itself does not require Python, pip, a virtual environment, or a Node runtime.

Skip the live probe during installation:

```bash
curl -fsSL https://raw.githubusercontent.com/scy7796/visual-evidence-gateway/main/install.sh | sh -s -- --skip-probe
```

Diagnostics:

```bash
visual-evidence-gateway healthcheck --check-connectivity --json
visual-evidence-gateway probe --backend primary --json
codex mcp list
```

Restart the MCP host after installation so it can discover the new server.

## When to use it

Visual Evidence Gateway is useful when:

- DeepSeek, OpenCode, Pi, or another text-first agent remains the main planner;
- images appear in only a few steps of a longer task;
- the agent needs to read terminal screenshots, UI states, charts, diagrams, or before/after images;
- the host should receive only task-relevant evidence rather than full OCR and long visual traces;
- local path access and backend identity need explicit controls.

Native image attachment is usually simpler when Codex is already the main agent and a person only needs to inspect one or two images. OCR is usually faster for clean text. Computer-use tools are required when the task must click, type, or control a browser.

## Native attachment vs. the gateway

| Approach | Best fit | Main difference |
|---|---|---|
| Native Codex attachment | One-off inspection with Codex as the main agent | Shortest path and simplest workflow |
| OCR | Clean text and low latency | Does not understand layout, color, charts, or UI state |
| Generic vision API/MCP | Quick access to an arbitrary vision model | Path controls, model binding, and output validation vary by implementation |
| Visual Evidence Gateway | A text agent remains in control and occasionally needs image evidence | Read-only paths, explicit model binding, crop/tile retries, structured evidence, compact output, and fail-closed routing |

A same-machine six-fixture comparison on 2026-08-06 produced:

- task completion: 6/6 for both native attachment and the gateway;
- exact expected-token coverage: 4/6 native, 6/6 gateway;
- median end-to-end time: 16.6 s native, 20.2 s gateway;
- median returned length: 602 characters native, 62 characters gateway.

These results apply only to the tested synthetic fixtures and machine. They do not establish universal accuracy or speed superiority.

## How it works

```text
text-first host agent
    │ vision.inspect
    ▼
path authorization and stable read
    ▼
image limits, normalization, private staging
    ▼
Codex CLI + gpt-5.6-luna
    ▼
JSON Schema, model identity, and semantic checks
    ▼
optional crop/tile retry
    ▼
compact answer, location evidence, uncertainty
```

The host submits one to four authorized image paths and a focused question. By default, the response contains a short answer, image-indexed evidence, a small amount of relevant text, uncertainty, and limited validation metadata. Full OCR, raw provider responses, and local cache paths are not returned or stored by default.

## Default security posture

- The current working directory is the only default allow root.
- Credential, configuration, and cache directories are denied.
- Symlinks, junctions, reparse points, UNC/verbatim paths, and NTFS alternate data streams are rejected.
- Images are decoded under byte, dimension, and pixel limits, then copied to a private per-request directory.
- Codex child runs use a read-only sandbox.
- Shell execution, subagents, hooks, remote plugins, automatic dependency installation, and web search are disabled.
- Backend output must pass JSON Schema, image-index, status, and model-identity checks.
- API-key, base-URL, organization, and project billing variables are removed from ChatGPT-mode child processes.
- Verifier and fallback backends are disabled by default.

These controls reduce risk but do not provide complete isolation. Use a dedicated system user, container, or virtual machine for highly sensitive images.

## Cache

Default configuration:

```yaml
cache:
  store_raw: false
  store_full_text: false
  expose_local_refs: false
```

Cache hits still repeat path authorization and stable image reads. Their main benefit is avoiding a repeated remote model call, not eliminating local work.

Validation-machine numbers excluding network and Luna inference:

| Path | Runs | Median | P95 | Backend calls |
|---|---:|---:|---:|---:|
| Uncached local pipeline | 80 | 92.4 ms | 146.6 ms | 1 stub call |
| Cache hit | 300 | 67.2 ms | 82.8 ms | 0 |

Ten live Luna probes on the validation machine ranged from 18.1 to 31.9 seconds, with medians around 21–25 seconds. Those figures are not performance guarantees.

## Tool contract

```text
vision.inspect(
  paths: list[str],
  query: str,
  mode: "auto" | "ui" | "text" | "chart" | "diagram" | "compare" | "general",
  rigor: "normal" | "critical" | "cheap"
)
```

- `paths`: one to four absolute image paths under `allowed_roots`;
- `query`: the specific question that depends on image content;
- `mode`: task type;
- `normal`: primary backend with evidence-driven crop/tile retry;
- `critical`: optional independent verifier, with disagreements returned as partial results;
- `cheap`: primary-first execution with configured alternatives only when needed.

## Validation status

Version 0.5.0 validated:

- ChatGPT authentication and explicit `gpt-5.6-luna` routing;
- ten live randomized image probes;
- OCR, UI, chart, comparison, long-image, and image-prompt-injection fixtures;
- unauthorized path, non-image, symlink, and junction negatives;
- zero backend calls on cache hits;
- strict JSON Schema validation;
- protocol-level stdio interoperability through the official MCP SDK client;
- Windows installer simulation, a live standalone-binary probe, and multi-platform CI builds.

Important boundary: Codex Desktop has not yet been manually verified as the host after restart. The npm Codex CLI 0.146.1 on the validation Windows machine could not complete stdio MCP tool calls, so the automated protocol test used the official MCP SDK client. Protocol interoperability is therefore verified; Codex Desktop host integration remains unverified.

## Known limitations

- Codex Desktop host-level use still requires a manual check.
- Windows ARM64 has no prebuilt binary.
- Release binaries are not code-signed; installers rely on HTTPS and the SHA-256 manifest.
- macOS/Linux installers are covered by CI and POSIX integration tests, while the live account validation machine was Windows.
- Luna entitlement and latency are controlled by the upstream service.
- The default backend requires network access.

## Development

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install -e ".[dev]"
ruff check .
pytest
python -m compileall -q src tests scripts
python scripts/audit_release.py
```

Real-world release validation:

```bash
python pre_release_validation/run_validation.py --runs 5 --host-mcp
```

## Project

- Version: 0.5.0
- License: MIT
- Transport: local stdio MCP
- Default backend: Codex CLI + `gpt-5.6-luna` + ChatGPT authentication
- Status: community-maintained, not an official OpenAI product
