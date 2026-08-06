# Visual Evidence Gateway

[![CI](https://github.com/scy7796/visual-evidence-gateway/actions/workflows/ci.yml/badge.svg)](https://github.com/scy7796/visual-evidence-gateway/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/scy7796/visual-evidence-gateway)](https://github.com/scy7796/visual-evidence-gateway/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Keep DeepSeek, OpenCode, Pi, or another text-first agent in charge of the task. When it hits a screenshot, send only the image question to Luna through one read-only MCP tool.

```text
vision.inspect(
  paths=["./terminal.png"],
  query="What exception is shown, and where does the stack trace first enter project code?"
)
```

The default route reuses your Codex ChatGPT login and pins `gpt-5.6-luna`. The gateway reads approved image files, makes private copies for the request, checks the returned schema and model identity, then sends compact evidence back to the host agent.

If Luna is unavailable, the call fails. It does not silently switch to another model or an API-billed route.

## Six fixtures: 6/6 expected fields, 62-character median reply

The same six synthetic image tasks were sent through native Codex image attachment and Visual Evidence Gateway.

| Result | Native Codex attachment | Visual Evidence Gateway |
|---|---:|---:|
| Tasks completed | 6/6 | 6/6 |
| All expected fields present | 4/6 | 6/6 |
| Median returned text | 602 characters | 62 characters |
| Median end-to-end time | 16.6 s | 20.2 s |

On these fixtures, the gateway returned about one tenth as much text without dropping an expected field. It was slower. This is a six-case same-machine comparison, not a general accuracy claim. The prompts, outputs, and limits are recorded in [`comparison.md`](pre_release_validation/results/comparison/comparison.md).

## Quick install

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

The installer downloads the executable for your platform, checks the published SHA-256 hash, registers the MCP server with an absolute path, checks the Codex login, and runs a small image request. The gateway itself does not need Python, pip, a virtual environment, or a separate Node runtime.

To install without making the image request:

```bash
curl -fsSL https://raw.githubusercontent.com/scy7796/visual-evidence-gateway/main/install.sh | sh -s -- --skip-probe
```

Windows:

```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/scy7796/visual-evidence-gateway/main/install.ps1))) -SkipProbe
```

Restart the MCP host after setup so it can discover the server.

You can also download the binary and checksum file from [Releases](https://github.com/scy7796/visual-evidence-gateway/releases), verify the hash yourself, and run:

```bash
./visual-evidence-gateway setup
```

## Where it helps

This project is for long tasks where a text-first agent handles planning and code but occasionally needs to read a terminal screenshot, inspect a UI state, understand a chart, follow a diagram, or compare two images.

The host sends a focused question instead of its entire conversation. The reply contains a short answer, image-indexed evidence, relevant text, and any uncertainty. Full OCR output and backend traces stay out of the host conversation by default.

Native image attachment is simpler when Codex is already the main agent and you only need to inspect one image. OCR is usually faster for clean text when layout and visual relationships do not matter. This server does not control a mouse, keyboard, browser, video stream, or live desktop.

## What happens to an image

```text
text-first agent
    |
    | vision.inspect
    v
path authorization and stable file read
    v
bounded copy in a private request directory
    v
Codex CLI with gpt-5.6-luna
    v
model identity, schema, and semantic checks
    v
optional crop or tile retry
    v
compact evidence returned to the host
```

The gateway reads only approved image files. It copies them into a private request directory before calling the backend, so the backend never receives an arbitrary path from the host.

If the first answer does not contain enough evidence, the router can retry with a crop or a set of tiles. The final response must match the result schema and can only refer to images that were included in the request.

## File and model controls

The current working directory is the default allow root. The gateway rejects credential and configuration directories, symbolic links, Windows junctions and reparse points, UNC and verbatim paths, NTFS alternate data streams, unsupported files, and images outside the configured size and pixel limits.

The Codex child process runs read-only. Shell access, subagents, hooks, remote plugins, automatic dependency installation, and web search are disabled. ChatGPT mode removes API-key and alternate-endpoint variables from the child environment.

Text inside an image is treated as content to inspect. The gateway checks the backend response for execution claims and other signs that the image tried to redirect the task.

These controls narrow the available attack surface, but they are not a complete isolation boundary. Use a separate user account, container, or virtual machine for highly sensitive images.

## Cache behavior

The default cache keeps compact evidence. It does not keep raw backend responses, full OCR text, or local cache paths:

```yaml
cache:
  store_raw: false
  store_full_text: false
  expose_local_refs: false
```

A cache hit still repeats path authorization, stable file reading, and image-byte checks. It skips another backend call only when the image, question, and relevant settings are unchanged.

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

`query` should ask for the fact that must be confirmed from the image. Keep project history and unrelated task context in the host conversation.

`mode` selects the visual task. In `auto` mode, the router uses the image count and the query to choose a path.

`normal` uses the primary backend and allows crop or tile retries when the evidence is weak. `critical` can use an independently configured verifier. `cheap` stays on the primary route unless the operator has configured another path.

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

See [`examples/config.yaml`](examples/config.yaml) for a complete example. Remote endpoints, API keys, verifier models, and fallback models require explicit configuration.

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

Diagnostics:

```bash
visual-evidence-gateway healthcheck --check-connectivity --json
visual-evidence-gateway probe --backend primary --json
codex mcp list
```

## Known limits

- Codex Desktop may need a full restart before it discovers the server.
- Windows ARM64 does not have a prebuilt binary.
- Release binaries are not code-signed. The installers rely on HTTPS and the published SHA-256 manifest.
- Luna access and latency depend on the account and current service conditions.
- The default backend needs a network connection.
- This project is not intended for medical imaging, industrial inspection, or precision measurement.

This is a community project, not an official OpenAI product.

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

## License

MIT

If this fits your workflow, a Star helps other people find it.