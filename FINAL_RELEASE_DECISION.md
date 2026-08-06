# Final release decision

**Decision: PASS, with one documented host-integration boundary**

Date: 2026-08-06  
Version: `0.5.0`  
Distribution: `visual-evidence-gateway`

## Scope of the decision

The release is approved for:

- the gateway core and its security contracts;
- the ChatGPT-authenticated Codex CLI path to explicit `gpt-5.6-luna`;
- release artifacts and installers;
- protocol-level MCP interoperability over stdio;
- the documented Windows validation environment.

The decision does **not** claim that Codex Desktop has been manually verified as the MCP host. That remains an open compatibility check.

## Live subscription path

The validation machine reported:

- `codex-cli 0.146.1`;
- `codex login status` → `Logged in using ChatGPT`;
- an empty `OPENAI_API_KEY` in the active Codex auth file;
- successful randomized probes with transcript model identity `gpt-5.6-luna`.

The gateway explicitly pins the model, forces ChatGPT authentication, disables CLI default-model selection, and removes API-key, base-URL, organization, project, Anthropic, Gemini, and Codex API-key variables from the child environment. Verifier and fallback backends are disabled by default.

## Pre-release validation

Both of the following commands passed all release gates:

```bash
python pre_release_validation/run_validation.py --runs 5 --host-mcp
python pre_release_validation/run_validation.py --runs 5 --host-mcp --benchmark
```

| Gate | Result |
|---|---|
| Compile, tests, and release audit | PASS |
| ChatGPT authentication | PASS |
| Randomized Luna probes | 10/10 across both runs |
| OCR, UI, chart, comparison, long-image, and injection fixtures | 6/6 |
| Unauthorized path and file-type negatives | PASS |
| Cache hit without another backend call | PASS |
| Strict backend JSON Schema | PASS |
| Official MCP SDK client over stdio | PASS |

The row above is intentionally described as **MCP SDK stdio interoperability**, not “Codex host-level call.”

## Same-machine comparison

The six synthetic fixtures were run through Codex native image attachment and this gateway.

| Metric | Codex native attachment | Gateway |
|---|---:|---:|
| Completed cases | 6/6 | 6/6 |
| All expected tokens present | 4/6 | 6/6 |
| Median end-to-end time | 16.6 s | 20.2 s |
| Median returned length | 602 characters | 62 characters |
| Injection-compliance hits | 0 | 0 |

The gateway was slower on this machine but returned shorter, task-focused evidence. These six fixtures do not establish general accuracy or speed superiority.

ModLens was not run because its external Antigravity CLI login was not configured on the validation machine.

## Installer and build results

- Windows installer simulation: checksum verification, setup arguments, PATH update, idempotence, tamper rejection, rollback, and missing-manifest failure all passed.
- The real standalone Windows binary completed a live Luna probe.
- `pytest`: 197 passed, 9 platform-gated skips.
- `ruff`, `compileall`, source audit, wheel/sdist build, `twine check`, artifact verification, clean installation, and source-ZIP retest passed.
- CI produced the documented platform artifacts and the v0.5.0 Release.

## Issues fixed before release

The final pass corrected model pinning and identity checks, environment-variable leakage, local-path disclosure in errors, Windows junction handling, prompt-injection false positives, comparison-fixture logic, probe parsing, installer checksum and rollback behavior, validation-cache handling, and two CI packaging defects.

## Known limitations

- On the validation Windows machine, npm Codex CLI 0.146.1 could not complete stdio MCP tool calls, including against a trivial test server. Automated MCP interoperability was therefore tested with the official MCP SDK client.
- Codex Desktop must still be restarted and tested manually as the host.
- Windows ARM64 has no prebuilt binary.
- Release binaries are not code-signed.
- macOS/Linux installers were covered by CI and POSIX integration tests, not by the live Windows account-validation machine.
- Luna access and latency vary by account, region, workspace, and service load.

The detailed machine-readable evidence is stored under `pre_release_validation/results/`.
