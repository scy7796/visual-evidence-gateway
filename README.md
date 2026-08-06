# Visual Evidence Gateway

Visual Evidence Gateway is a local MCP server for agents that need to inspect images without handing the rest of the task to a multimodal model.

It exposes one tool:

```text
vision.inspect(paths, query, mode="auto", rigor="normal")
```

The default backend calls `gpt-5.6-luna` through the local Codex CLI and requires a ChatGPT login. The gateway does not store account credentials or API keys. If Luna is unavailable, the request fails instead of switching to another model or an API-billed route.

This is a community project, not an official OpenAI product. Model access depends on the account, region, workspace, and client version.

[Architecture](docs/ARCHITECTURE.md) · [Security model](docs/SECURITY_MODEL.md) · [Releases](https://github.com/scy7796/visual-evidence-gateway/releases)

## Install

Install the Codex CLI and sign in with ChatGPT:

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

The installer downloads the executable for the current platform, checks its SHA-256 hash, registers the MCP server with an absolute path, checks the Codex login, and runs an image probe.

The gateway itself does not need Python, pip, a virtual environment, or a Node runtime. The installer does not install Codex or change the current login method.

To install without running the image probe:

```bash
curl -fsSL https://raw.githubusercontent.com/scy7796/visual-evidence-gateway/main/install.sh | sh -s -- --skip-probe
```

Windows:

```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/scy7796/visual-evidence-gateway/main/install.ps1))) -SkipProbe
```

After installation, restart the MCP host so it can discover the server.

To avoid piping a remote script into a shell, download the binary and checksum file from [Releases](https://github.com/scy7796/visual-evidence-gateway/releases), verify the hash, and run:

```bash
./visual-evidence-gateway setup
```

## When it fits

Visual Evidence Gateway is useful when a text-first agent handles the main task and only needs image evidence at a few points. Typical inputs include terminal screenshots, interface states, charts, diagrams, and before-and-after comparisons.

The host sends one to four approved image paths and a focused question. The gateway returns a short answer, image-indexed evidence, relevant text, and any uncertainty. Full OCR output and backend traces stay out of the main conversation by default.

Direct image attachment is simpler when Codex is already the main agent and a person only needs to inspect one or two images. OCR is usually better for clean text when layout and visual relationships do not matter. This project also does not provide mouse, keyboard, browser, video, or live screen control.

## How a request runs

```text
text-first agent
    |
    | vision.inspect
    v
path checks and stable file read
    v
bounded image copy in a private request directory
    v
Codex CLI with gpt-5.6-luna
    v
schema, model identity, and semantic checks
    v
optional crop or tile retry
    v
compact evidence returned to the host
```

The gateway reads only approved image files. It copies each image into a private request directory before calling the backend, which avoids giving the backend an arbitrary local path.

If the first result does not contain enough evidence, the router can retry with a crop or a set of tiles. The final response must match the result schema and refer only to images that were part of the request.

## File and model controls

The default configuration allows images from the current working directory. It rejects credential and configuration directories, symbolic links, Windows junctions and reparse points, UNC and verbatim paths, NTFS alternate data streams, unsupported files, and images outside the configured size and pixel limits.

The Codex child process runs read-only. Shell access, subagents, hooks, remote plugins, automatic dependency installation, and web search are disabled. ChatGPT mode removes API-key and alternate-endpoint variables from the child environment.

Image text is treated as content to inspect, not as an instruction to the host. The gateway checks the backend result for execution claims and other signs that text inside the image affected the task.

These controls reduce the available attack surface, but they do not turn the process into a complete isolation boundary. Use a separate user account, container, or virtual machine for highly sensitive images.

## Cache behavior

By default, the cache does not store raw backend responses, full OCR text, or local cache paths:

```yaml
cache:
  store_raw: false
  store_full_text: false
  expose_local_refs: false
```

A cache hit still repeats path authorization, stable file reading, and image-byte checks. It avoids another backend call only when the image, question, and relevant settings are unchanged.

## Tool reference

```text
vision.inspect(
  paths: list[str],
  query: str,
  mode: "auto" | "ui" | "text" | "chart" | "diagram" | "compare" | "general",
  rigor: "normal" | "critical" | "cheap"
)
```

`paths` accepts one to four absolute image paths inside `allowed_roots`.

`query` should contain the specific fact that must be confirmed from the image. Project history and unrelated task context should stay in the host conversation.

`mode` selects the type of visual task. In `auto` mode, the router uses the number of images and the query to choose a path.

`normal` uses the primary backend and allows evidence-driven crop or tile retries. `critical` can use an independently configured verifier. `cheap` stays on the primary route unless the operator has explicitly configured another path.

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

See [`examples/config.yaml`](examples/config.yaml) for a complete example. Remote endpoints, API keys, verifier models, and fallback models require explicit operator configuration.

## Commands

```text
visual-evidence-gateway setup
visual-evidence-gateway serve
visual-evidence-gateway healthcheck
visual-evidence-gateway probe
```

Manual MCP registration:

```bash
codex mcp add visual-evidence-gateway -- visual-evidence-gateway serve
```

Registration with a specific configuration file:

```bash
codex mcp add visual-evidence-gateway \
  --env VISUAL_EVIDENCE_GATEWAY_CONFIG=/absolute/path/to/config.yaml \
  -- visual-evidence-gateway serve
```

Useful diagnostics:

```bash
visual-evidence-gateway healthcheck --check-connectivity --json
visual-evidence-gateway probe --backend primary --json
codex mcp list
```

## Known limits

- Codex Desktop host discovery still depends on the installed client and may require a full restart.
- Windows ARM64 does not have a prebuilt binary.
- Release binaries are not code-signed. The installers rely on HTTPS and the published SHA-256 manifest.
- Luna access and latency depend on the account and current service conditions.
- The default backend needs a network connection.
- This project is not intended for medical imaging, industrial inspection, or precision measurement.

## Upgrade and uninstall

Run the installer again to upgrade.

Remove the MCP registration with:

```bash
codex mcp remove visual-evidence-gateway
```

Then remove the installation and configuration directories:

- Windows: `%LOCALAPPDATA%\VisualEvidenceGateway\bin` and `%APPDATA%\visual-evidence-gateway`
- macOS: `~/Library/Application Support/visual-evidence-gateway`
- Linux: `~/.local/share/visual-evidence-gateway` and `~/.config/visual-evidence-gateway`

## Development

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

## Migration from the old name

Version 0.5.0 renamed the project from `vision-bridge-mcp` to `visual-evidence-gateway` because the old name was already used by another project.

Old installation directories and MCP registrations are not removed automatically. Remove the previous registration when it is no longer needed:

```bash
codex mcp remove vision-bridge
```

Environment variables beginning with `VISION_BRIDGE_` are no longer read. The current prefix is `VISUAL_EVIDENCE_GATEWAY_`.

## License

MIT

If the gateway solves a problem in your workflow, a Star helps other people find it.