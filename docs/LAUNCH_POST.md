# Launch post (Show HN)

Suggested title:

> Show HN: VisionSieve, an MCP server that cuts visual context ~10x

I run most of my coding work in a text-first agent. Screenshots still break that workflow. Attaching an image natively works, but the model's description of it lands in the main conversation, and on a long task that text adds up.

VisionSieve is a local MCP server that does the image step outside the main context. You give it one to four image paths and a question. It copies the images into a private directory, sends a focused prompt to a pinned model through the local Codex CLI, checks the response against a schema, and returns a short evidence packet with the answer, image-indexed evidence, relevant text, and uncertainty.

I compared it with native Codex attachment on the same machine, six synthetic image tasks:

| Result | Native | VisionSieve |
|---|---:|---:|
| Tasks completed | 6/6 | 6/6 |
| All expected fields present | 4/6 | 6/6 |
| Median visual text returned to the host | 602 chars | 62 chars |
| Median end-to-end time | 16.6 s | 20.2 s |

Slower at the median, about 1/10 the text. Six fixtures on one machine; this is not a general benchmark.

Native attachment is still the simpler choice when Codex is already the main agent and the task involves one image. The sieve is for workflows where the main agent stays text-first (DeepSeek, OpenCode, Pi, or Codex on a long task) and only needs visual evidence for part of it.

Most of the work went into the security model. VisionSieve reads only paths inside an allowlist, rejects symlinks and reparse points, skips credential and config directories, and stages a private copy of each image. The backend child process is read-only, with shell, browser, subagent, and web tools disabled. Output is checked for model identity and schema compliance, and text inside the image is treated as content to inspect, not as instructions. The pinned Luna route is the only default. When it is unavailable, the call fails instead of switching to an API-billed model.

Install with an existing Codex CLI and ChatGPT login:

```powershell
irm https://raw.githubusercontent.com/scy7796/visionsieve-mcp/main/install.ps1 | iex
```

```bash
curl -fsSL https://raw.githubusercontent.com/scy7796/visionsieve-mcp/main/install.sh | sh
```

Repo: https://github.com/scy7796/visionsieve-mcp

Limits: no Windows ARM64 binary, release binaries not code-signed, Luna depends on the account and service conditions, network required. No mouse, keyboard, browser, video, or live-screen control. Not for medical imaging, industrial inspection, or precision measurement. Community project, not an official OpenAI product.
