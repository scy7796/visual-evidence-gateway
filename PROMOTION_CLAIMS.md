# What the validation supports

Public descriptions should stay within the evidence collected on 2026-08-06.

## Supported statements

Visual Evidence Gateway lets a text agent call a read-only `vision.inspect` MCP tool while the main planning and coding task stays in DeepSeek, OpenCode, Pi, or another host agent.

The default backend uses the local Codex CLI with explicit `gpt-5.6-luna` and ChatGPT authentication. ChatGPT-mode child processes do not inherit API-billing or alternate-provider variables. The request fails if the configured Luna route is unavailable.

The gateway authorizes image paths, rejects links and reparse points, stages bounded private copies, validates backend output, and returns compact image-indexed evidence. A cache hit repeats path and file-stability checks but makes no backend call for an identical request.

The installers check SHA-256, roll back the binary when setup fails, register the MCP server by absolute path, and can run a real image probe.

On the six synthetic fixtures used in the same-machine comparison, both native Codex attachment and the gateway completed 6/6 tasks. Expected fields were fully present in 4/6 native results and 6/6 gateway results. The gateway was slower and returned less text.

Whenever these numbers appear in public material, include the sample boundary. Six synthetic fixtures on one machine are not a general benchmark.

## Statements the evidence does not support

Do not describe the project as the first or only visual bridge. Do not claim that it is generally more accurate or faster than native vision, ModLens, or other MCP servers. Do not promise fixed latency, a specific token reduction, unlimited use, zero cost, complete sandboxing, or zero security risk.

Do not claim a completed Codex Desktop host test. The automated MCP check used the official MCP SDK client over stdio. Codex Desktop still needs a manual call after restart.

## Recommended description

Use a plain description such as:

> Visual Evidence Gateway is a local, read-only MCP server for text agents. It calls Luna through the user's Codex ChatGPT login, limits which images can be read, checks the backend result, and returns a short set of task-specific visual evidence.

For a launch post, use [`docs/LAUNCH_POST.zh-CN.md`](docs/LAUNCH_POST.zh-CN.md). Add the actual host version and a successful call screenshot before publishing it.
