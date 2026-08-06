# VisionSieve MCP v1.0.0

VisionSieve gives text-first agents a narrow visual handoff: one focused image question goes to Luna, and compact checked evidence comes back to the host.

The default route uses the local Codex CLI, a ChatGPT login, and explicit `gpt-5.6-luna`. Verifier and fallback routes remain off unless the operator configures them. If the expected model or login route is unavailable, the request fails instead of switching to another model or an API-billed path.

## New public identity

Version 1.0 introduces the VisionSieve name across the public interface:

- Python distribution: `visionsieve-mcp`
- CLI: `visionsieve`
- MCP registration: `visionsieve`
- configuration variable: `VISIONSIEVE_CONFIG`
- standalone binaries and checksum manifest: `visionsieve-*`

The MCP tool remains `vision.inspect`.

The hardened runtime core stays compatible with 0.5 installations. Old `visual-evidence-gateway` console commands and the `visual_evidence_gateway` Python package remain available in 1.0 as migration aliases. Running `visionsieve setup` removes the old MCP registration before adding the new one.

## Same-machine comparison

Six synthetic image tasks were run through native Codex image attachment and VisionSieve with the same questions.

| Metric | Native Codex attachment | VisionSieve |
|---|---:|---:|
| Tasks completed | 6/6 | 6/6 |
| Expected fields fully present | 4/6 | 6/6 |
| Median visual text returned to the host | 602 characters | 62 characters |
| Median end-to-end time | 16.6 s | 20.2 s |

On this fixture set, VisionSieve returned about one tenth as much visual text and kept every expected field. It was 3.6 seconds slower at the median. These six synthetic cases do not establish general accuracy, context-token, or speed results.

## Installation

Prerequisite: Codex CLI signed in with ChatGPT.

Windows PowerShell:

```powershell
irm https://raw.githubusercontent.com/scy7796/visual-evidence-gateway/main/install.ps1 | iex
```

macOS or Linux:

```bash
curl -fsSL https://raw.githubusercontent.com/scy7796/visual-evidence-gateway/main/install.sh | sh
```

The installer downloads a platform binary, requires a matching entry in `visionsieve-SHA256SUMS.txt`, registers the MCP server with an absolute command path, checks the ChatGPT login, and runs a small image probe. Setup failure rolls the new binary back.

## Release assets

The release workflow builds:

- Windows x86_64
- Linux x86_64 and ARM64
- macOS x86_64 and ARM64
- wheel and sdist
- source ZIP
- SHA-256 manifest

Windows ARM64 has no prebuilt binary. Release binaries are not code-signed.

## Boundaries

MCP protocol interoperability was validated over stdio with the official MCP SDK client in the 0.5 release process. Codex Desktop host discovery can vary by client version and may require a complete restart. Luna availability and latency depend on the account, region, workspace, and service conditions.

VisionSieve MCP is a community project, not an official OpenAI product.
