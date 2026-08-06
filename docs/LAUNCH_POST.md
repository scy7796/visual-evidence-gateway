# Launch post

I use text-first agents for most coding work, but screenshots are still awkward. Switching the whole task to a multimodal agent works, though it also moves the planning, code, and long conversation to a different model.

Visual Evidence Gateway keeps the main task where it is. It adds one local MCP tool:

```text
vision.inspect(paths, query)
```

The host sends an approved image path and a focused question. The gateway checks the path, copies the image into a private request directory, calls `gpt-5.6-luna` through the local Codex CLI, and returns a short answer with image-indexed evidence.

The default route uses the existing ChatGPT login in Codex. It does not store API keys, and it does not switch to an API-billed model when Luna is unavailable.

I built the extra layer because a thin image wrapper was not enough for the workflow I wanted. The gateway limits readable paths, rejects links and common credential locations, runs the backend without shell or browser tools, checks the model identity and response schema, and can retry with crops or tiles when small details are hard to read.

Install it with an existing Codex CLI and ChatGPT login.

Windows:

```powershell
irm https://raw.githubusercontent.com/scy7796/visual-evidence-gateway/main/install.ps1 | iex
```

macOS or Linux:

```bash
curl -fsSL https://raw.githubusercontent.com/scy7796/visual-evidence-gateway/main/install.sh | sh
```

Repository:

https://github.com/scy7796/visual-evidence-gateway

Direct image attachment is still the simpler choice when Codex is already the main agent. This project is for workflows where a text-first agent stays in control and only needs visual evidence for a small part of the task.

Current limits are documented in the README. Windows ARM64 has no prebuilt binary, release binaries are not code-signed, and Luna access depends on the account and client.

If it is useful in your setup, a Star helps other people find it.