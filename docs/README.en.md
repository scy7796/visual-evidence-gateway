# Visual Evidence Gateway

Visual Evidence Gateway is a local MCP server. Text agents such as DeepSeek, OpenCode, and Pi can call it when a task depends on an image, while the main planning and coding work stays in the original agent.

The server exposes one tool:

```text
vision.inspect(paths, query, mode="auto", rigor="normal")
```

The default backend calls `gpt-5.6-luna` through the local Codex CLI and requires Codex to use ChatGPT authentication. The project stores no account credentials, tokens, or API keys. If Luna is unavailable, the request fails instead of switching to API billing or another model.

This is a community project, not an official OpenAI product. Luna availability depends on the account, region, workspace, and client version.

[Chinese README](../README.md) · [Architecture](ARCHITECTURE.md) · [Security model](SECURITY_MODEL.md) · [Release validation](../FINAL_RELEASE_DECISION.md)

## Install

Install Codex CLI and sign in with ChatGPT:

```bash
npm install -g @openai/codex
codex
```

Windows PowerShell:

```powershell
irm https://raw.githubusercontent.com/scy7796/visual-evidence-gateway/main/install.ps1 | iex
```

macOS or Linux:

```bash
curl -fsSL https://raw.githubusercontent.com/scy7796/visual-evidence-gateway/main/install.sh | sh
```

The installer downloads the standalone executable for the current platform, checks its SHA-256 against the Release manifest, registers the MCP server with an absolute path, checks ChatGPT authentication, and runs a real image probe. The gateway itself does not need Python, pip, a virtual environment, or Node. The installer does not install Codex or change the login method.

To install and register the server without running the Luna probe:

```bash
curl -fsSL https://raw.githubusercontent.com/scy7796/visual-evidence-gateway/main/install.sh | sh -s -- --skip-probe
```

Windows:

```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/scy7796/visual-evidence-gateway/main/install.ps1))) -SkipProbe
```

Run the checks later with:

```bash
visual-evidence-gateway healthcheck --check-connectivity --json
visual-evidence-gateway probe --backend primary --json
codex mcp list
```

Restart Codex, the IDE extension, or another MCP host after installation so it can discover the tool.

If you do not want to pipe a remote script into a shell, download the binary and checksum from [Releases](https://github.com/scy7796/visual-evidence-gateway/releases), then run:

```bash
./visual-evidence-gateway setup
```

## When it fits

This project fits long tasks where images appear only in a few steps. The main agent handles planning and code, then calls `vision.inspect` for a terminal screenshot, UI, chart, diagram, or before-and-after comparison. The host receives a short answer, location evidence, and uncertainty instead of full OCR or a long visual narrative.

Use an existing tool directly when:

- Codex is already the main agent and a person only needs to inspect one or two images;
- source code, logs, CSV data, or the DOM already contain the answer;
- the task needs mouse, keyboard, browser, or live-screen control;
- the task must run fully offline;
- the image belongs to a medical, industrial, or precision-measurement workflow.

## Compared with direct image attachment

Native Codex image attachment has the shortest path and works well for one-off inspection. Visual Evidence Gateway is meant for workflows where a text agent keeps control of the main task and asks for visual evidence through a fixed tool contract.

| Approach | Best fit | Main difference |
|---|---|---|
| Native Codex attachment | Codex is the main agent and a person inspects one image | Simple path; the visual result stays in the current Codex session |
| OCR | Clean text where speed matters most | Does not understand layout, color, graphics, or UI state |
| General vision API or MCP | Fast access to any vision model | Path limits, model binding, and output checks depend on the implementation |
| Visual Evidence Gateway | A text agent stays in control and occasionally needs an image | Adds path authorization, model pinning, crop retries, structured evidence, and fail-closed behavior |

A same-machine test on 2026-08-06 used six synthetic image types:

| Metric | Native Codex attachment | Gateway |
|---|---:|---:|
| Tasks completed | 6/6 | 6/6 |
| Expected fields fully present | 4/6 | 6/6 |
| Median end-to-end time | 16.6 s | 20.2 s |
| Median returned length | 602 characters | 62 characters |

The gateway was slower in this test and returned less text. Six synthetic fixtures do not represent every real image and do not establish general accuracy. The full record is under [`pre_release_validation/results/comparison/`](../pre_release_validation/results/comparison/).

## Request flow

```text
text agent
    │ vision.inspect
    ▼
path authorization and stable read
    ▼
image limits, normalization, private staging
    ▼
Codex CLI + gpt-5.6-luna
    ▼
schema, model identity, and semantic checks
    ▼
optional crop or tile retry
    ▼
short answer, location evidence, uncertainty
```

The host sends one to four authorized image paths and a specific question. The default response contains a short answer, image-indexed evidence, only the text relevant to the question, uncertainty, and the metadata needed to understand backend and validation status.

Full OCR, raw backend output, and local cache paths do not enter the host conversation or persist by default.

## File, model, and data boundaries

The default configuration only reads images under the MCP process working directory. It rejects credential, configuration, and cache directories. It also rejects symlinks, junctions, reparse points, UNC or verbatim paths, and NTFS alternate data streams. File size, image dimensions, pixel count, and decoding are bounded. An accepted image is copied into a private directory for the current request.

The Codex child process uses a read-only sandbox. Shell access, subagents, hooks, remote plugins, automatic dependency installation, and web search are disabled. The gateway checks JSON Schema, image indexes, status values, and model identity before returning evidence. In ChatGPT mode, the child process does not inherit API keys, base URLs, organization IDs, or project billing variables. Verifier and fallback backends are disabled by default.

These controls reduce arbitrary file access, prompt-injection escalation, silent model changes, and long-term retention of visual data. They are not a full isolation boundary. Use a separate system account, container, or virtual machine for highly sensitive images, and authorize the smallest practical directory. See [`SECURITY_MODEL.md`](SECURITY_MODEL.md).

## Instructions inside images

Screenshots and documents may contain text such as "ignore the rules," "run this command," or "read the secret." The gateway treats those strings as image content and checks risky semantics in both the prompt and the returned result. The vision backend has no shell, browser, plugin, or write access.

This does not prove that a vision model can never be influenced by image text. It limits what the model can do after such influence and adds another check before the result reaches the host agent.

## Cache and latency

The default cache stores no raw backend response, full OCR, or local cache path:

```yaml
cache:
  store_raw: false
  store_full_text: false
  expose_local_refs: false
```

The cache key includes the staged image bytes, the question, and relevant configuration, and entries use an HMAC signature. A cache hit still repeats path authorization and checks whether the source file changed. That leaves some local overhead, but the remote model is not called again.

The local pipeline measurements below exclude network and Luna inference:

| Path | Runs | Median | P95 | Backend calls |
|---|---:|---:|---:|---:|
| Cache miss | 80 | 92.4 ms | 146.6 ms | 1 stub call |
| Cache hit | 300 | 67.2 ms | 82.8 ms | 0 |

Ten live validation probes took 18.1 to 31.9 seconds, with a median around 21 to 25 seconds. Account, region, network, and service load affect this number. The installed `probe` command reports `elapsed_ms` for the current machine.

## Tool arguments

```text
vision.inspect(
  paths: list[str],
  query: str,
  mode: "auto" | "ui" | "text" | "chart" | "diagram" | "compare" | "general",
  rigor: "normal" | "critical" | "cheap"
)
```

`paths` accepts one to four absolute image paths under `allowed_roots`. `query` should describe only what must be confirmed from the image. `mode` selects the task type, while `auto` uses the image count and question.

`normal` uses the primary backend and can crop or tile when evidence is weak. `critical` can enable an independent verifier and returns a partial result when the backends disagree. `cheap` uses the primary backend first and only follows configured alternatives.

## Default configuration

```yaml
backends:
  primary:
    enabled: true
    via: codex_cli
    command: codex
    model: "gpt-5.6-luna"
    auth_mode: chatgpt
    min_cli_version: "0.146.0"
    reasoning_effort: medium
    extra_args: [--ephemeral, --ignore-user-config]
    allow_cli_default_model: false
  verifier:
    enabled: false
  fallback:
    enabled: false

allowed_roots:
  - "{cwd}"

cache:
  store_raw: false
  store_full_text: false
  expose_local_refs: false
```

See [`../examples/config.yaml`](../examples/config.yaml) for the full example. Remote endpoints, API keys, and extra models require explicit operator configuration.

## Commands

```text
visual-evidence-gateway setup
visual-evidence-gateway serve
visual-evidence-gateway healthcheck
visual-evidence-gateway probe
```

Manual registration:

```bash
codex mcp add visual-evidence-gateway -- visual-evidence-gateway serve
```

Registration with a specific configuration file:

```bash
codex mcp add visual-evidence-gateway \
  --env VISUAL_EVIDENCE_GATEWAY_CONFIG=/absolute/path/to/config.yaml \
  -- visual-evidence-gateway serve
```

## Validation scope for v0.5.0

Validation covered ChatGPT authentication, explicit `gpt-5.6-luna` calls, ten live pixel probes, six image types, path-security negatives, cache behavior, strict JSON Schema, stdio protocol calls through the official MCP SDK, the Windows installer, and multiplatform CI builds.

Codex Desktop has not been manually tested as the MCP host. npm Codex CLI 0.146.1 on the validation Windows machine could not complete stdio MCP tool calls, so the protocol test used the official MCP SDK client. This proves MCP protocol interoperability for the server. It does not prove a completed Codex Desktop call. See [`../FINAL_RELEASE_DECISION.md`](../FINAL_RELEASE_DECISION.md).

Current limitations:

- Windows ARM64 has no prebuilt binary;
- release binaries are not code-signed and rely on HTTPS plus the SHA-256 manifest;
- macOS and Linux installers are covered by CI and POSIX integration tests, while the live account validation machine used Windows;
- Luna entitlement and latency depend on upstream account and service state;
- the default backend requires a network connection.

## Troubleshooting

Check that Codex is available:

```bash
codex --version
```

If ChatGPT authentication is not confirmed:

```bash
codex logout
codex login
codex login status
```

The default subscription route does not accept API-key authentication.

If Luna is unavailable or the probe fails, the current account, workspace, region, client version, or service entitlement may not expose the model. The project does not switch to API billing. Wait for access or select another image-capable backend in a private configuration.

If MCP is registered but the tool is missing:

```bash
codex mcp list
```

Confirm that `visual-evidence-gateway` is present, then restart the host completely.

If an image is rejected, copy it into the current project directory. Do not add the whole home directory to `allowed_roots`.

## Upgrade and uninstall

Run the platform installer again to upgrade.

Remove the MCP registration:

```bash
codex mcp remove visual-evidence-gateway
```

Then delete the installation and configuration directories:

- Windows: `%LOCALAPPDATA%\VisualEvidenceGateway\bin` and `%APPDATA%\visual-evidence-gateway`;
- macOS: `~/Library/Application Support/visual-evidence-gateway`;
- Linux: `~/.local/share/visual-evidence-gateway` and `~/.config/visual-evidence-gateway`.

## Develop from source

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -e ".[dev]"
ruff check .
pytest
python -m compileall -q src tests scripts
python scripts/audit_release.py
```

Run live pre-release validation with:

```bash
python pre_release_validation/run_validation.py --runs 5 --host-mcp
```

## Name migration

Version 0.5.0 renamed the project from `vision-bridge-mcp` to `visual-evidence-gateway` because another project already used the old name. The old installation directories and MCP registration are not removed automatically. Remove the old registration after confirming that it is no longer needed:

```bash
codex mcp remove vision-bridge
```

Old `VISION_BRIDGE_*` environment variables no longer work. The current prefix is `VISUAL_EVIDENCE_GATEWAY_*`.

## Project information

- Version: 0.5.0
- License: MIT
- Default transport: local stdio MCP
- Default backend: Codex CLI, `gpt-5.6-luna`, ChatGPT authentication
- Maintained as a community project

If the gateway solves a problem in your workflow, a Star helps other people who run text agents find it.
