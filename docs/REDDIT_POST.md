# Reddit post (r/MCP)

Suggested title:

> I built a read-only MCP server that returns ~1/10 the visual text of native image attachment

Body:

I run most of my coding work in text-first agents. Screenshots still come up. Native attachment works, but the model's narration of the image ends up in the main conversation, and on a long task that is a lot of tokens.

So I built a local MCP server that does the image step on the side. vision.inspect(paths, query) copies the image into a private directory, calls a pinned model through the local Codex CLI (ChatGPT login, no stored API keys), validates the response, and returns a compact evidence packet.

Same-machine comparison against native attachment, six synthetic fixtures:

- Tasks completed: 6/6 both
- All expected fields: 4/6 native vs 6/6 VisionSieve
- Median visual text in host context: 602 chars vs 62 chars
- Median end-to-end time: 16.6 s vs 20.2 s

Slower at the median. The point is context management, not speed, and six fixtures on one machine is not a general accuracy claim.

Most of the work went into the security model: path allowlist, no symlinks or reparse points, read-only backend process with shell, browser, and subagent tools disabled, no silent fallback to an API-billed model. Details are in the README.

Install (requires Codex + ChatGPT login):

```powershell
irm https://raw.githubusercontent.com/scy7796/visionsieve-mcp/main/install.ps1 | iex
```

```bash
curl -fsSL https://raw.githubusercontent.com/scy7796/visionsieve-mcp/main/install.sh | sh
```

Repo: https://github.com/scy7796/visionsieve-mcp
