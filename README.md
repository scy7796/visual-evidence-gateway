# VisionSieve MCP

[![CI](https://github.com/scy7796/visual-evidence-gateway/actions/workflows/ci.yml/badge.svg)](https://github.com/scy7796/visual-evidence-gateway/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/scy7796/visual-evidence-gateway)](https://github.com/scy7796/visual-evidence-gateway/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

High-signal image evidence for text-first agents.

Keep DeepSeek, OpenCode, Pi, or another text-first agent in charge. When the task depends on pixels, VisionSieve sends one focused image question to Luna and returns a small, checked evidence packet.

**About 1/10 the visual text in the host context.**  
**6/6 expected fields versus 4/6 for native attachment in our six-fixture comparison.**

```text
vision.inspect(
  paths=["./terminal.png"],
  query="What exception is shown, and where does the stack trace first enter project code?"
)
```

The default route reuses the local Codex ChatGPT login and pins `gpt-5.6-luna`. If that route is unavailable, the call fails. It does not silently switch models or move onto an API-billed route.

## The comparison

The same six synthetic image tasks were sent through native Codex image attachment and VisionSieve on one machine.

| Result | Native Codex attachment | VisionSieve |
|---|---:|---:|
| Tasks completed | 6/6 | 6/6 |
| All expected fields present | 4/6 | 6/6 |
| Median visual text returned to the host | 602 characters | 62 characters, about 1/10 |
| Median end-to-end time | 16.6 s | 20.2 s |

VisionSieve took 3.6 seconds longer at the median and sent about 90% less visual text into the host context. It kept every expected field in this fixture set. This is a small same-machine comparison, not a general accuracy or speed leaderboard. The prompts, outputs, and limits are in [`comparison.md`](pre_release_validation/results/comparison/comparison.md).

## Install

First install Codex and sign in with ChatGPT:

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

The installer downloads the standalone binary for the current platform, verifies its SHA-256 hash, checks the Codex login, registers the `visionsieve` MCP server, and runs one image probe. Python, pip, and a virtual environment are not required.

Skip the image probe during setup:

```bash
curl -fsSL https://raw.githubusercontent.com/scy7796/visual-evidence-gateway/main/install.sh | sh -s -- --skip-probe
```

```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/scy7796/visual-evidence-gateway/main/install.ps1))) -SkipProbe
```

Restart the MCP host after installation.

To avoid piping a remote script into a shell, download the binary and `visionsieve-SHA256SUMS.txt` from [Releases](https://github.com/scy7796/visual-evidence-gateway/releases), verify the hash, and run:

```bash
./visionsieve setup
```

## Why use a sieve instead of attaching the image directly?

Direct attachment gives the multimodal model the image and usually lets it decide how much visual narration to return. That is convenient for isolated image questions. It is less convenient inside a long coding or research task, where a large OCR dump or broad visual description becomes part of the main agent's context.

VisionSieve keeps the handoff narrow:

```text
main agent keeps the task history
            |
            | focused image question
            v
        vision.inspect
            |
            | approved image bytes only
            v
      gpt-5.6-luna
            |
            | checked compact evidence
            v
main agent continues the original task
```

The host sends one to four approved image paths and a specific question. VisionSieve returns a short answer, image-indexed evidence, relevant text, and uncertainty. Full OCR output and backend traces stay out of the host conversation by default.

Native attachment is still simpler when Codex is already the main agent and the task only involves one image. OCR is usually faster for clean text when layout and visual relationships do not matter.

## What happens to an image

1. VisionSieve authorizes the path and performs a stable file read.
2. It copies bounded image bytes into a private request directory.
3. Codex invokes the pinned Luna model in a read-only child process.
4. The result is checked for model identity, schema compliance, evidence references, and task redirection from text inside the image.
5. Weak evidence can trigger a bounded crop or tile retry.
6. Only the compact result is returned to the host.

The backend never receives an arbitrary host path. It receives the private request copy.

## File and model controls

The current working directory is the default allow root. VisionSieve rejects credential and configuration directories, symbolic links, Windows junctions and reparse points, UNC and verbatim paths, NTFS alternate data streams, unsupported files, and images outside the configured byte and pixel limits.

The Codex child process runs read-only. Shell access, subagents, hooks, remote plugins, automatic dependency installation, and web search are disabled. ChatGPT mode removes API-key and alternate-endpoint variables from the child environment.

Text inside an image is treated as content to inspect, not as an instruction to the host. These controls reduce the available attack surface, but they are not a complete isolation boundary. Use a separate user account, container, or virtual machine for highly sensitive images.

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

`normal` uses the primary backend and permits evidence-driven crop or tile retries. `critical` can use an independently configured verifier. `cheap` stays on the primary route unless another path has been explicitly configured.

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

See [`examples/config.yaml`](examples/config.yaml) for the complete configuration surface. Remote endpoints, API keys, verifier models, and fallback models require explicit operator configuration.

## Commands

```text
visionsieve setup
visionsieve serve
visionsieve healthcheck
visionsieve probe
```

Manual registration:

```bash
codex mcp add visionsieve -- visionsieve serve
```

Registration with a specific configuration file:

```bash
codex mcp add visionsieve \
  --env VISIONSIEVE_CONFIG=/absolute/path/to/config.yaml \
  -- visionsieve serve
```

Diagnostics:

```bash
visionsieve healthcheck --check-connectivity --json
visionsieve probe --backend primary --json
codex mcp list
```

## Cache behavior

The default cache stores compact evidence, not raw backend responses, full OCR text, or local cache paths. A cache hit repeats path authorization and image-byte checks, then skips the backend call only when the image, question, and relevant settings are unchanged.

## Upgrading from Visual Evidence Gateway 0.5

Version 1.0 changes the public distribution, executable, and MCP registration to VisionSieve:

```text
Python distribution: visionsieve-mcp
CLI:                 visionsieve
MCP registration:    visionsieve
config variable:     VISIONSIEVE_CONFIG
```

Running `visionsieve setup` removes the old `visual-evidence-gateway` MCP registration before adding the new one. The old Python import package and old console commands remain available in 1.0 as compatibility aliases; new integrations should use the VisionSieve names.

The v1 default config directory is:

- Windows: `%APPDATA%\visionsieve`
- macOS: `~/Library/Application Support/visionsieve`
- Linux: `~/.config/visionsieve`

Existing 0.5 configuration can be passed explicitly:

```bash
visionsieve setup --config /path/to/old/config.yaml
```

## Known limits

- Codex Desktop may need a full restart before it discovers the server.
- Windows ARM64 has no prebuilt binary.
- Release binaries are not code-signed.
- Luna access and latency depend on the account and current service conditions.
- The default backend needs a network connection.
- VisionSieve does not provide mouse, keyboard, browser, video, or live-screen control.
- It is not intended for medical imaging, industrial inspection, or precision measurement.

VisionSieve MCP is a community project, not an official OpenAI product.

## Uninstall

```bash
codex mcp remove visionsieve
```

Remove the installed `visionsieve` binary and its configuration directory. Users upgrading from 0.5 may also remove the old `visual-evidence-gateway` binary and configuration directory after confirming the v1 setup works.

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
python -m build
python scripts/verify_artifacts.py
```

## License

MIT

If VisionSieve earns a place in your workflow, a Star helps the next person find it.
