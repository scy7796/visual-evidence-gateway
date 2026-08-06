# Launch post (Show HN)

Suggested title:

> Show HN: VisionSieve, an MCP server that cuts visual context ~10x

Most of my coding work runs in a text-first agent. Screenshots still break that workflow. Native image attachment works, but the model's description of the image lands in the main conversation, and on a long task that text adds up.

VisionSieve is a local MCP server that does the image step outside the main context. You give it one to four image paths and a question. It copies the images into a private directory, sends a focused prompt to a pinned model through the local Codex CLI, checks the response against a schema, and returns a short evidence packet: answer, image-indexed evidence, relevant text, uncertainty.

Same-machine comparison, six synthetic image tasks, native Codex attachment vs VisionSieve:

| Result | Native | VisionSieve |
|---|---:|---:|
| Tasks completed | 6/6 | 6/6 |
| All expected fields present | 4/6 | 6/6 |
| Median visual text returned to the host | 602 chars | 62 chars |
| Median end-to-end time | 16.6 s | 20.2 s |

Slower at the median, about 1/10 the text. Six fixtures on one machine, not a general benchmark.

When native attachment is still the better choice: Codex is already the main agent and the task involves one image. The sieve is for workflows where the main agent stays text-first (DeepSeek, OpenCode, Pi, or Codex on a long task) and only needs visual evidence for part of it.

Security is where I spent most of the time: path allowlist, no symlinks or reparse points, no credential directories, private staged copy of the image, backend child process read-only with shell, browser, subagent, and web tools disabled, model identity and response schema checked, text inside the image treated as content rather than instructions. The pinned Luna route is the only default. If it is unavailable, the call fails instead of silently switching to an API-billed model.

Install with an existing Codex CLI and ChatGPT login:

Windows:

```powershell
irm https://raw.githubusercontent.com/scy7796/visionsieve-mcp/main/install.ps1 | iex
```

macOS or Linux:

```bash
curl -fsSL https://raw.githubusercontent.com/scy7796/visionsieve-mcp/main/install.sh | sh
```

Repo: https://github.com/scy7796/visionsieve-mcp

Limits: no Windows ARM64 binary, release binaries not code-signed, Luna access depends on the account and service conditions, network required, no mouse, keyboard, browser, video, or live-screen control. Not for medical imaging, industrial inspection, or precision measurement. Community project, not an official OpenAI product.
