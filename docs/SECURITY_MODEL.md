# Security model

## Protected assets

Files outside configured roots, credentials, ChatGPT/Codex account material, provider authorization data, private images, cache contents, local machine paths, and the integrity of evidence returned to the MCP host.

## Trust boundaries

Image bytes and text embedded in images are untrusted evidence. Backend output remains untrusted until schema validation, model binding, semantic checks, and prompt-injection gates pass. The local Codex executable, its authentication store, Pillow, the operating system, and any explicitly configured Responses gateway are operator-controlled dependencies.

## Subscription-authentication controls

The public primary backend is pinned to `gpt-5.6-luna` over the local Codex CLI.

- `forced_login_method="chatgpt"` prevents automatic selection of API-key authentication.
- API billing variables are absent from the child environment and cannot be added through `pass_env` while `auth_mode: chatgpt` is active.
- `--ignore-user-config` reduces exposure to user-level provider overrides and hooks while retaining authentication through the configured Codex home.
- Mandatory `-c` overrides disable shell execution, shell snapshots, subagents, hooks, remote plugins, automatic skill/MCP dependency installation, and web search.
- Codex history persistence, feedback submission, analytics, prompt telemetry, and metrics/trace exporters are disabled for the child invocation.
- The model is passed explicitly with `--model`; CLI default-model selection is disabled.
- `visual-evidence-gateway-healthcheck --check-connectivity` requires an executable, the configured minimum version, and a `codex login status` response consistent with ChatGPT authentication.
- Failure to confirm the subscription route is fail-closed. The adapter does not retry through the Responses API.

These controls prove the requested local invocation contract and prevent silent fallback to API-key billing or another configured backend. They cannot independently attest the upstream model implementation: the current `codex exec` result channel does not expose a cryptographically verifiable resolved-model identity. Entitlement and successful execution therefore remain external account properties checked operationally by the connectivity check and deterministic probe.

## Image and path controls

- Default allow root is only the MCP host working directory.
- Configuration/cache and common credential directories are denied.
- UNC paths, alternate data streams, verbatim paths, symlinks, junctions, and reparse points are rejected.
- Authorization occurs before MIME sniffing or decoding and is repeated immediately before a stable regular-file open.
- Images are normalized to private PNGs and bounded by source bytes, decoded pixels, side length, per-image staged bytes, and total staged bytes.
- Each request receives a private random staging directory. Cleanup is restricted to that namespace.

## Backend and output controls

- Codex children have bounded stdout/stderr, a hard timeout, process-tree termination, a private working directory, read-only sandbox selection, no approvals, and recursion guards.
- The final result file must be a stable, direct, bounded regular file; link/reparse and replacement races fail closed.
- Responses endpoints are literal loopback origins by default. Remote use requires HTTPS and an exact hostname allowlist. Redirects and embedded URL credentials are rejected.
- Backend output must match the strict JSON Schema and runtime limits. Failed status, undeclared fields, invalid image indices, non-finite confidence, and malformed types are rejected.
- Configured model identity is trusted over model self-report. Responses gateways must return a resolved model identifier unless explicitly relaxed.
- Claims that instructions embedded in an image were executed invalidate the result.

## Cache and disclosure controls

- Cache summaries are HMAC-signed and namespaced by exact image bytes and result-affecting configuration.
- Raw provider payloads, full OCR text, and local filesystem references are independent opt-ins, all disabled by default.
- Optional raw retention is recursively secret-masked.
- Configuration and health files are bounded and reject filesystem indirection.

## Residual risks

`read-only` limits writes but does not by itself prevent a same-user Codex process or a compromised CLI from reading files that the host OS and sandbox permit. The adapter disables the normal shell, web, plugin, hook, and subagent surfaces, but this is defense in depth rather than an OS confidentiality boundary. A model may still make perception errors that deterministic checks cannot detect. Managed/system Codex policy may still affect execution. A compromised local executable, operating system, configured gateway, or credential store defeats this package's assumptions.

For highly sensitive images, run the MCP server and Codex CLI under a dedicated OS account or container with only the required image directory mounted. Do not expose this server directly to an untrusted network or multi-tenant host without separate authentication, process isolation, rate limiting, and audit controls.
