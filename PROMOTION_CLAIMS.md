# Promotion claims

Only claims with direct evidence from the 2026-08-06 validation run may be promoted.

## Claims supported by evidence

- Text-first agents (DeepSeek, OpenCode, Pi, …) can call a read-only `vision.inspect` MCP tool whose default backend is the local Codex CLI with explicit `gpt-5.6-luna` and forced ChatGPT subscription authentication (verified live: `Logged in using ChatGPT`, transcript header `model: gpt-5.6-luna`).
- The gateway strips API-billing/alternate-provider environment variables from child processes and fails closed when Luna is unavailable; verifier/fallback are off by default (code + tests + live probes).
- On the tested machine with six synthetic fixture types (OCR, UI, chart, compare, long image, prompt-injection), the gateway returned token-exact structured evidence for 6/6 cases while Codex native attachment returned 4/6 exact-token results in the same session (native text case omitted the code value; native ui case translated labels to Chinese).
- The gateway returns compact evidence (median ~62 chars vs ~602 chars native) with image-indexed locations and explicit uncertainty, under a hard token budget.
- Prompt-injection fixture: neither path complied with embedded instructions; the gateway additionally gates execution-claim language before delivery (unit tests cover adversarial variants).
- Cache hits serve identical requests with 0 backend calls while re-running path authorization and image stability checks.
- One-command installers verify SHA-256 (missing/tampered manifests abort), roll back on setup failure, register MCP by absolute path, and are idempotent (Windows simulated end-to-end; POSIX covered by CI/integration test).

## Claims NOT supported / must not be promoted

- No claim that visual accuracy is universally higher than official or other vision solutions (same-machine comparison shows the gateway is *slower* end-to-end than native attachment on this machine: median 20.2 s vs 16.6 s).
- No "world's first" or "only solution" claims.
- No "faster in all scenarios" claims.
- No "zero security risk" claims; no "completely sandboxed" claims beyond the documented read-only child process with disabled tools.
- No fixed latency promises (latency depends on account, region, and service load).
- No "free unlimited use" claims (ChatGPT subscription availability is entitlement-dependent).
- No claim that the Codex Desktop host was verified end-to-end through MCP: the npm CLI 0.146.1 stdio-MCP-call defect on Windows prevented a live CLI-host call; the host gate uses the official MCP SDK client, and desktop-host verification is a documented untested boundary.
