# Changelog

## 1.0.0 - 2026-08-06

- Renamed the public product to **VisionSieve MCP**, emphasizing its high-signal, minimal-context visual handoff.
- Changed the Python distribution to `visionsieve-mcp`, the primary CLI to `visionsieve`, the MCP registration to `visionsieve`, and the public configuration variable to `VISIONSIEVE_CONFIG`.
- Added the `visionsieve_mcp` package as the v1 entry layer while retaining the hardened `visual_evidence_gateway` core and old console commands as compatibility aliases for 0.5 upgrades.
- Added migration-aware setup that removes the old `visual-evidence-gateway` MCP registration, registers `visionsieve`, and accepts either the new or legacy configuration variable.
- Renamed standalone binaries and the checksum manifest to `visionsieve-*`.
- Extended the release workflow to publish five platform binaries, wheel, sdist, source ZIP, and SHA-256 manifest.
- Reworked the README around the measured result: 62 versus 602 median returned characters, with 6/6 versus 4/6 expected-field coverage in the six-fixture same-machine comparison. The documentation explicitly distinguishes returned characters from token counts and records the 3.6-second median latency cost.

## 0.5.0 - 2026-08-06

- Renamed the project to **Visual Evidence Gateway**: distribution `visual-evidence-gateway`, import package `visual_evidence_gateway`, CLI/MCP registration name `visual-evidence-gateway`, and `VISUAL_EVIDENCE_GATEWAY_*` environment variables. The previous `vision-bridge-mcp` name collided with an existing same-purpose project on GitHub and npm; a short migration note is included in the README and no second public brand is retained.
- Added transport-level model identity verification for the Codex CLI path: the `codex exec` transcript header is compared against the configured model, so model alias/substitution is detected instead of assumed.
- Extended the ChatGPT-mode child-process environment blocklist to `OPENAI_BASE_URL`, `ANTHROPIC_API_KEY`, and `GEMINI_API_KEY` in addition to the existing API-key/org/project variables.
- Added local absolute-path masking to refusal reasons and backend error strings so machine paths cannot leak into MCP responses.
- Hardened the one-command installers: SHA-256 verification is now mandatory (missing or malformed checksums abort), setup failures roll back the downloaded binary, and Windows ARM64 fails with an explicit message until a prebuilt binary is published.
- Fixed the Windows CI wheel reinstall step; added `jsonschema` to the dev extras.
- Extended the pre-release validation kit with strict JSON-Schema validation of persisted backend payloads, a cache-hit no-backend-call check, and a junction/reparse-point negative test (all P0).
- Fixed `{project_root}` resolution for `health_file`, aligned documented uninstall paths with the installer, updated the security supported-line, and corrected stale test-count documentation.

## 0.4.1 - Simplified installation

- Added one standalone `visual-evidence-gateway` executable with `setup`, `serve`, `healthcheck`, and `probe` subcommands.
- Replaced the Python/venv/pip bootstrap in end-user installers with release-binary downloads and SHA-256 verification.
- Stopped auto-installing Codex from a third-party script path; users install the official CLI explicitly, while setup handles ChatGPT login and MCP registration.
- Added cross-platform release-binary build automation.

## 0.4.0 - 2026-08-04

- Renamed the project from Visual Router MCP to the clearer, provider-neutral **Vision Bridge MCP**.
- Renamed the distribution, Python package, MCP server name, environment variables, cache/config directories, console commands, examples, tests, and release checks.
- Added an idempotent one-command installer for Windows and macOS/Linux using a private virtual environment.
- Added `visual-evidence-gateway-setup`, which writes credential-free defaults, verifies ChatGPT subscription login, registers the server with `codex mcp add`, runs connectivity checks, and executes a real randomized pixel probe.
- Rewrote the public documentation around the actual product boundary, architecture advantages, comparison with Codex native image input, direct Luna API access, OCR, thin vision wrappers, and computer-use agents.
- Documented the DeepSeek/OpenCode main-agent + Luna visual-specialist split and the bounded reasons for choosing Luna as the default.
- Added a reproducible local-overhead benchmark and live probe `elapsed_ms` reporting, without presenting simulated timing as real Luna latency.
- Added explicit non-official/entitlement-dependent language and preserved fail-closed behavior when Luna is unavailable.
- Kept the 0.3 security hardening: minimal context, path isolation, schema validation, prompt-injection gates, signed cache summaries, read-only Codex execution, and no silent API billing fallback.
- Added a pre-release real-world validation kit with a Codex execution brief, P0/P1/P2 release gates, generated OCR/UI/chart/compare/long-image/injection fixtures, live Luna latency capture, negative path tests, optional host-level MCP invocation, and machine-readable/report outputs.
- Split public claims into locally verified, operator-verified, and unsupported categories; clarified that cache value is avoiding a remote backend call rather than materially reducing the ~70 ms local safety pipeline.

## 0.3.0 - 2026-08-04

- Made the public primary backend subscription-first: local Codex CLI, explicit `gpt-5.6-luna`, and forced ChatGPT authentication.
- Added generic `codex_cli` transport support for `primary`, `verifier`, and `fallback` instead of limiting the CLI adapter to the verifier role.
- Added minimum CLI-version checks and bounded `codex login status` diagnostics.
- Removed API key, organization, and project billing variables from ChatGPT-authenticated child processes and rejected attempts to re-add them through `pass_env`.
- Added `--ephemeral` and `--ignore-user-config` to the default CLI invocation, retained a private working directory, read-only sandbox, no approvals, schema-constrained output, timeout, output caps, and process-tree termination.
- Added mandatory per-call Codex overrides that apply configured reasoning effort and disable shell execution, shell snapshots, subagents, hooks, remote plugins, automatic skill/MCP dependency installation, web search, history persistence, feedback, analytics, prompt telemetry, and metrics/trace exporters.
- Kept verifier and fallback roles disabled by default; optional Responses API routing remains available.
- Added Luna-specific regression tests for defaults, dispatch, command construction, environment sanitization, version gating, configuration validation, and healthcheck fail-closed behavior.
- Updated examples, English and Chinese documentation, architecture, security model, release reports, artifact checks, and package version to 0.3.0.

## 0.2.0 - 2026-08-04

- Repackaged the private prototype as an installable MCP project using the official Python SDK 2.x server surface.
- Replaced personalized backend names with `primary`, `verifier`, and `fallback` roles.
- Moved runtime configuration, cache, credentials, and health state outside the package.
- Removed personal paths, account state, private endpoints, and machine-specific defaults.
- Restricted default image access to the current working directory and added configuration/cache and common credential roots to the deny list.
- Reordered path authorization before content reads, added pre-open reauthorization and stable-file checks, and keyed cache entries from staged PNG bytes.
- Made raw payload retention, full OCR retention, and local filesystem references independent opt-ins, all disabled by default.
- Added exact model identity, endpoint allowlisting, redirect rejection, bounded responses, recursive secret masking, signed caches, private staging, and recursion guards.
- Aligned prompt examples with the strict result schema and hardened provider/output file reads against indirection and check/use races.
- Added GitHub CI, release/archive audits, security documentation, examples, and packaging metadata.
