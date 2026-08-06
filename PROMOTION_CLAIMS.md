# Public claims and launch guidance

Use only claims supported by the 2026-08-06 validation run.

## Safe claims

- Visual Evidence Gateway lets text-first agents call a read-only `vision.inspect` MCP tool while keeping the main planning and coding task in DeepSeek, OpenCode, Pi, or another host agent.
- The default backend uses the local Codex CLI with explicit `gpt-5.6-luna` and ChatGPT authentication.
- The default route removes API-billing and alternate-provider environment variables from the child process and fails instead of silently switching models or billing paths.
- The gateway authorizes image paths, rejects links and reparse points, stages bounded private copies, validates backend output, and returns compact image-indexed evidence.
- Cache hits repeat path and file-stability checks but make zero backend calls for identical requests.
- The installers verify SHA-256, roll back on setup failure, register the MCP server by absolute path, and can run a real image probe.
- On the tested six synthetic fixtures, both native Codex attachment and the gateway completed 6/6 tasks. Exact expected-token coverage was 4/6 native and 6/6 gateway; the gateway was slower but returned much shorter output.

Always attach the boundary to the benchmark: it is a small synthetic fixture set on one machine, not a general leaderboard.

## Claims to avoid

Do not claim that the project is:

- the first or only way to add vision to text models;
- universally more accurate than Codex native vision, ModLens, or other visual MCP tools;
- faster in every scenario;
- free or unlimited;
- completely sandboxed or risk-free;
- guaranteed to use subscription quota for every account;
- already verified through Codex Desktop as the host.

The live host-level boundary is important: protocol interoperability passed through the official MCP SDK client, while Codex Desktop still needs a manual post-restart test.

## Recommended positioning

Use this description:

> Visual Evidence Gateway is a read-only MCP server for text-first agents. It sends focused image questions to Luna through the user's local Codex login, then returns compact, validated evidence instead of a full visual trace.

A slightly more technical version:

> Keep DeepSeek or OpenCode as the main agent and use Luna only for image evidence. The gateway adds local path controls, model pinning, crop/tile retries, structured output checks, prompt-injection screening, compact responses, and fail-closed routing.

## Launch sequence

1. Publish the repository and Release.
2. Manually verify one real `vision.inspect` call from Codex Desktop after restart.
3. Add that result, host version, and screenshot to the README.
4. Make a small technical launch post in the communities where DeepSeek/OpenCode/Codex users already discuss tool integrations.
5. Collect installation failures before making broader performance or accuracy claims.

Do not lead with the synthetic 6/6 versus 4/6 comparison. Lead with the architecture and one-command installation; place benchmark data lower in the post with its limits.
