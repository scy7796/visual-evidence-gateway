# Visual Evidence Gateway

Visual Evidence Gateway gives text-first AI agents a local, read-only, minimal-context way to inspect images through one MCP tool: `vision.inspect`.

It is not just a thin vision API wrapper. It authorizes local paths, stages bounded image copies in a private request directory, calls a configured vision backend, retries with crops or tiles when evidence is insufficient, validates the result against a JSON Schema, checks model identity and image prompt injection indicators, and returns only compact evidence to the host agent.

The public default invokes the local Codex CLI with the explicit model identifier `gpt-5.6-luna` and forces ChatGPT authentication. The repository contains no account, credential, API key, workspace ID, or private endpoint. Availability is entitlement-dependent and is verified by a real pixel probe after installation. The project is community-maintained and is not an official OpenAI product.

## One-command setup

Windows PowerShell:

```powershell
irm https://raw.githubusercontent.com/scy7796/visual-evidence-gateway/main/install.ps1 | iex
```

macOS/Linux:

```bash
curl -fsSL https://raw.githubusercontent.com/scy7796/visual-evidence-gateway/main/install.sh | sh
```

The installer downloads a standalone executable matching your OS and CPU, verifies its SHA-256 checksum against the release manifest, registers the MCP server with `codex mcp add` using absolute paths, and then runs a real randomized image probe that reports end-to-end `elapsed_ms`. It does not require Python, pip, a virtual environment, pipx, or uv for the gateway itself, and it never installs Codex for you; the only prerequisite is the official Codex CLI signed in with ChatGPT. If setup fails, the downloaded binary is rolled back so no half-installed state remains.

Review remote scripts before piping them to a shell. The clone-and-run alternative is documented in the main Chinese README.

## Why it is stronger for its target use case

Visual Evidence Gateway is designed for local static-image inspection by agents that should remain text-first most of the time.

- Unlike pasting screenshots into the main chat, it keeps full images, OCR and retry traces out of the long-lived host context.
- Unlike OCR-only tools, it preserves layout, color, charts, arrows, UI state and cross-image comparison.
- Unlike basic single-provider wrappers, it enforces a structured result contract, model binding, semantic validation and prompt-injection checks.
- Unlike broad computer-use agents, it exposes no mouse, keyboard, shell or browser control; the tool is read-only.
- Unlike API-key-first integrations, the default path reuses the user's existing ChatGPT/Codex subscription login and strips API billing variables from the child process.

This does not imply universal accuracy superiority. OCR-only tools may be faster for clean text, direct multimodal chat may be simpler for one-off use, and computer-use systems are required when the task must click or type.

## Native Codex vision vs. the default bridge

Codex and current OpenAI models already accept image input. Native attachment is the simplest option when Codex is the main agent and a human wants to inspect one screenshot. Visual Evidence Gateway targets a different architecture: DeepSeek, OpenCode, or another text-first agent remains the planner and coder, while Luna is invoked only as a narrow visual specialist through MCP.

That separation keeps the main agent's long context intact, returns compact evidence instead of a full visual trace, and adds project-specific controls that direct image attachment does not by itself provide: local path authorization, private staging, crop/tile retry, schema and semantic gates, prompt-injection checks, signed minimal caching, and fail-closed backend binding.

The default uses Luna because OpenAI positions `gpt-5.6-luna` for efficient, high-volume workloads and the model supports image input and structured outputs. It is a role-fit decision, not a claim that Luna has universally higher single-image accuracy than every flagship model. Operators can configure a stronger independent verifier for critical tasks.

Official references:

- https://developers.openai.com/api/docs/models/gpt-5.6-luna
- https://developers.openai.com/api/docs/guides/latest-model
- https://help.openai.com/en/articles/11369540

## Performance measurements

The public numbers separate local bridge overhead from live Luna latency. On the Linux construction environment (CPython 3.13.5, five visible CPUs), a 1920x1080, 109,361-byte PNG produced:

- uncached local pipeline: 70.8 ms median, 74.5 ms p95 across 80 iterations;
- cache hit: 68.7 ms median, 72.4 ms p95 across 300 iterations, with zero backend calls.

The cache path still re-authorizes and stably reads the image before trusting cached evidence. This is intentional; the cache removes the remote model call rather than bypassing local security checks. Reproduce the local benchmark with:

```bash
PYTHONPATH=src python scripts/benchmark_local.py
```

A live probe reports end-to-end `elapsed_ms`, including Codex startup, network, upload, queueing, and Luna inference:

```bash
visual-evidence-gateway probe --backend primary --json
```

## Default security and privacy posture

- The current working directory is the only default allow root.
- Credential, configuration and cache directories are denied.
- Symlinks, junctions, reparse points, UNC/verbatim paths and alternate data streams are rejected.
- Images are decoded under byte, pixel and dimension limits, then normalized into a private per-request directory.
- Raw provider responses, full OCR text and local cache paths are not retained or returned by default.
- Codex child runs are read-only and disable shell execution, subagents, hooks, remote plugins, automatic dependency installation and web search.
- Backend output must pass JSON Schema and semantic checks before it can become evidence.
- Subscription or model failure is explicit; the default does not silently switch to API billing.

## Tool

```text
vision.inspect(paths, query, mode="auto", rigor="normal")
```

Modes: `auto`, `ui`, `text`, `chart`, `diagram`, `compare`, `general`.

Rigor:

- `normal`: primary backend with evidence-driven crop/tile retry.
- `critical`: optional independent verifier; disagreements become partial results.
- `cheap`: primary first, then configured alternatives only when needed.

## Manual setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install -e .
codex login
visual-evidence-gateway setup
```

Diagnostics:

```bash
visual-evidence-gateway healthcheck --check-connectivity --json
visual-evidence-gateway probe --backend primary --json
codex mcp list
```

Official Codex references:

- https://developers.openai.com/codex/auth
- https://developers.openai.com/codex/mcp
- https://github.com/openai/codex

See the main README, architecture document and security model for full details.

## Pre-release real-world validation

Run `python pre_release_validation/run_validation.py --runs 5 --host-mcp` before a public release. Local tests validate code contracts; they do not prove account entitlement, subscription routing, live Luna latency, host-level MCP discovery, or cross-platform installation. See `pre_release_validation/README.md` and `claims-matrix.md`.
