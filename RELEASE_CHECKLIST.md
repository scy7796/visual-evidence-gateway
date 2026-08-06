# Release checklist

## Naming and source hygiene

- Confirm the public name is **Visual Evidence Gateway** and identifiers are `visual-evidence-gateway` (distribution/CLI/MCP server), `visual_evidence_gateway` (import package), `visual-evidence-gateway-mcp` (server entry point), and `VISUAL_EVIDENCE_GATEWAY_` (environment variables).
- Keep the historical former name only in the changelog migration note.
- Keep `examples/config.yaml` synthetic; never insert credentials, account identifiers, quota state, private endpoints, or private infrastructure.
- Confirm the public default remains `codex_cli` + `gpt-5.6-luna` + `auth_mode: chatgpt`, with verifier/fallback disabled.
- Confirm API billing variables cannot enter a ChatGPT-authenticated child.
- Run source tests, compilation, and `python scripts/audit_release.py`.
- Review generated docs and reports for personal paths and stale version/test counts.

## One-command setup

- Run `sh -n install.sh` on Linux/macOS.
- Run `install.ps1` in Windows PowerShell CI.
- Verify both scripts use an isolated per-user virtual environment and do not mutate system Python.
- Verify Codex installation can be disabled and otherwise uses the official installer.
- Verify `visual-evidence-gateway-setup` does not overwrite existing configuration without an explicit force flag.
- Verify ChatGPT login, `codex mcp add` registration, connectivity check, and randomized-pixel probe all gate success.
- Verify repeat execution is idempotent and does not create duplicate MCP registrations.

## Compatibility and protocol

- Run Python 3.10–3.13 on Linux and selected Windows versions.
- Run `ruff check .`.
- Exercise `vision.inspect` with the official MCP 2.x in-memory client or MCP Inspector.
- Verify the server exposes exactly one public tool: `vision.inspect`.

## Subscription-backed Luna acceptance

- Install Codex CLI `0.146.0` or newer stable release.
- Run `codex login status` and confirm ChatGPT authentication.
- Run `visual-evidence-gateway-healthcheck --check-connectivity --json`; require `ready_for_requests: true`.
- Run `visual-evidence-gateway-probe --backend primary --json`; require a successful schema-valid pixel result.
- Verify failure does not activate a Responses API backend unless the operator explicitly configured and enabled one.

## Artifacts and GitHub

- Delete old `build/`, stale `dist/`, `*.egg-info`, caches, and virtual environments.
- Build exactly one sdist and one wheel.
- Run `python -m twine check dist/*` and `python scripts/verify_artifacts.py`.
- Install the wheel into a clean environment; verify version, resources, console entry points, and healthcheck semantics.
- Extract the sdist and rerun tests, compilation, and source audit.
- Extract the GitHub ZIP and rerun tests, compilation, source audit, and installer checks.
- Verify the GitHub ZIP contains `.github` metadata but no build products, cache, credentials, or runtime state.
- Publish SHA-256 checksums, tag `v0.5.0`, attach wheel/sdist/checksums to the release, and enable private security advisories before announcement.

## Performance and comparison

- [x] README explicitly compares Codex native image input, direct Luna API use, generic vision MCP wrappers, OCR, and the default DeepSeek/OpenCode + Luna split.
- [x] Local bridge overhead is reproducible with `PYTHONPATH=src python scripts/benchmark_local.py`.
- [x] Simulated local timing is not represented as live Luna latency.
- [x] `visual-evidence-gateway-probe` reports real end-to-end `elapsed_ms` on the operator machine.

## Operator-side real-world release gate

- Run `python pre_release_validation/run_validation.py --runs 5 --host-mcp` on a machine with Codex CLI and ChatGPT login.
- Require at least three consecutive randomized Luna pixel probes; five are recommended for latency reporting.
- Require all six known-answer fixtures and the negative security suite to pass.
- Require a real host-level MCP `vision.inspect` call, not only direct Python imports.
- Save `validation-result.json`, `REAL_WORLD_TEST_REPORT.md`, and command logs after reviewing them for secrets/private paths.
- Compare Visual Evidence Gateway and native Luna image input on the same machine/account/images without assuming Visual Evidence Gateway is more accurate.
- Do not promote live latency, cross-platform installation, cross-host compatibility, crop/tile gains, token savings, or relative accuracy until the corresponding report fields are complete.
- A missing or failed P0 result blocks the public tag/release even when local unit tests pass.
