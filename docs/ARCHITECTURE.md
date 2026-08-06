# Architecture

## Public surface

The MCP server exposes one tool: `vision.inspect`. The host never selects a provider directly. The router validates local image access, stages normalized copies, chooses configured role adapters, validates model output, reduces evidence to a hard token budget, and optionally stores a signed cache entry.

## Default execution path

The release default is:

`MCP host -> vision.inspect -> private image staging -> primary/codex_cli -> local Codex CLI -> gpt-5.6-luna through saved ChatGPT authentication -> validated compact result`

The package does not implement ChatGPT authentication. It delegates authentication to the locally installed Codex CLI, forces `forced_login_method="chatgpt"`, explicitly selects `gpt-5.6-luna`, and strips API billing variables from the child environment.

The Codex child runs from the request's private directory with:

- `--sandbox read-only`
- `--ask-for-approval never`
- `--ephemeral`
- `--ignore-user-config`
- `--output-schema <package schema>`
- `--output-last-message <private result file>`

`--ignore-user-config` keeps operator-specific Codex configuration, hooks, and provider overrides out of this invocation while authentication still uses the Codex credential location. Inline configuration then pins ChatGPT authentication for the run.

## Role adapters

`primary`, `verifier`, and `fallback` are capability roles, not provider names. Every role supports:

- `codex_cli`: a bounded local Codex subprocess using saved authentication;
- `responses_api`: an OpenAI-compatible Responses endpoint with exact endpoint and model checks.

Only the Luna-backed `primary` role is enabled by default. Verifier and fallback roles are disabled until the operator configures them.

## Routing

- `normal`: primary; crop/tile retry when evidence is semantically insufficient; verifier on unresolved insufficiency, injection suspicion, or model mismatch.
- `critical`: primary plus an independent verifier when available; disagreement becomes `partial` with explicit uncertainty.
- `cheap`: primary first, then verifier or fallback only when required.
- Operational primary failure: verifier first, fallback second.

A role is routable only when enabled, has a valid transport/model contract, and satisfies its optional deterministic probe gate. The default Luna primary does not require a stored probe so a correctly logged-in installation works immediately; operators can enable `require_probe` after running `visual-evidence-gateway-probe`.

## Data flow

`request -> path authorization -> metadata/decode checks -> private PNG staging -> staged-byte hash -> signed-cache lookup -> role routing -> schema/model/injection gates -> bounded reduction -> signed-cache store -> compact MCP result`

The cache key uses exact normalized bytes submitted to the backend plus result-affecting configuration. A cache hit still repeats local authorization and staging, preventing a source-file check/use mismatch.

A backend receives only the staged images, exact visual question, mode-specific prompt contract, and—when reconciliation is required—a compact prior summary. It does not receive arbitrary repository context from the MCP host.
