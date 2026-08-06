# Final release decision

**Decision: PASS**

Date: 2026-08-06 · Version: 0.5.0 · Distribution: `visual-evidence-gateway`

## Evidence

### 1. ChatGPT subscription chain (verified live)

- `codex --version` → `codex-cli 0.146.1` (npm official CLI; the Store/MSIX binary cannot be spawned from a shell on this machine).
- `codex login status` → `Logged in using ChatGPT` (exit 0); `~/.codex/auth.json` reports `auth_mode = chatgpt` and an empty `OPENAI_API_KEY` value.
- Real Luna probe through the same call shape the gateway uses (`--ignore-user-config`, `-c forced_login_method="chatgpt"`, `--model gpt-5.6-luna`, `--sandbox read-only`) returned the expected token; transcript header confirms `model: gpt-5.6-luna`, `provider: openai`, `approval: never`.
- Code-level guarantees verified in `src/visual_evidence_gateway/backends/codex_cli.py`: explicit `--model` pin, `forced_login_method="chatgpt"`, environment whitelist strips `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_ORG_ID`, `OPENAI_PROJECT_ID`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `CODEX_API_KEY` in chatgpt mode; verifier/fallback disabled by default; `allow_cli_default_model=false`; read-only sandbox; shell/subagent/hooks/web/auto-install disabled; recursion guard.

### 2. Pre-release validation (`pre_release_validation/results/validation-result.json`)

Both commands pass all eight P0 gates:

| Gate | `--runs 5 --host-mcp` | `--runs 5 --host-mcp --benchmark` |
|---|---|---|
| Local compile/test/audit | PASS | PASS |
| ChatGPT subscription authentication | PASS | PASS |
| Randomized Luna probes (5/5) | PASS | PASS |
| Core fixture suite (6/6) | PASS | PASS |
| Negative security suite | PASS | PASS |
| Cache hit does not repeat backend call | PASS | PASS |
| Strict JSON Schema on backend payloads | PASS | PASS |
| Codex MCP host-level call | PASS | PASS |
| Verdict | **PASS** | **PASS** |

Live Luna latency (10 real probes across the two runs): median ≈ 21.2–24.5 s, min ≈ 18.1 s, max ≈ 31.9 s on this machine/account/network. These are operator-machine numbers, not product promises.

Local orchestration benchmark (stub backend, excludes network/model): uncached median 92.4–109.7 ms (p95 121–147 ms); cache hit median 64.4–67.2 ms with **0 backend calls**.

### 3. Same-machine comparison (`pre_release_validation/results/comparison/comparison.md`)

Same six fixture images, same queries, all real calls (fresh cache):

| Metric | Codex native `--image` | This gateway |
|---|---|---|
| Completed cases | 6/6 | 6/6 |
| All expected tokens present | 4/6 (text omitted the code value; ui translated to Chinese) | 6/6 |
| Median end-to-end latency | 16.6 s | 20.2 s |
| Median returned length | 602 chars | 62 chars |
| Location evidence present | 2/6 | 3/6 |
| Uncertainty admitted | 1/6 | 1/6 |
| Injection-compliance hits | 0 | 0 |
| Extra API key needed | no (ChatGPT login) | no (reuses same login) |
| Shell/plugin/fs permissions | default codex toolset | none (shell/hooks/subagents/web disabled in child) |

ModLens (`@liustack/modlens`): not runnable on this machine without an external Antigravity CLI login (`Provider CLI not found: agy. Install it and sign in first.`); recorded as a credential boundary, not run.

### 4. Installer simulation (isolated temp dir, Windows)

`install.ps1` against a local HTTP release base with a stub `codex` and a fake one-file binary (`pre_release_validation/results/installer-simulation-windows.json`):

- download + SHA-256 verification + install: PASS
- `setup --skip-probe` argument passing: PASS
- user PATH update: PASS (restored after test)
- idempotent second run: PASS
- tampered binary rejected with SHA-256 error: PASS
- setup failure rolls back the binary: PASS
- missing checksum manifest fails closed: PASS

The real single-file binary (PyInstaller, same flags as CI) additionally ran a **real Luna probe successfully** on this machine (`probe passed`, `vision_verified: true`).

### 5. Automated tests and builds

- `pytest`: 197 passed, 9 skipped (skips are platform-gated, e.g. POSIX installer integration which runs in CI on ubuntu).
- `ruff check .`: clean. `compileall`: clean. `scripts/audit_release.py`: passed (also in the unpacked GitHub zip).
- `python -m build`: wheel + sdist built. `twine check`: PASSED. `scripts/verify_artifacts.py`: passed.
- Clean venv installs from wheel and from sdist: `visual-evidence-gateway --version` → `0.5.0`.
- GitHub source zip (`git archive`) unpacked and re-tested: 197 passed, audit passed.
- Release artifacts + SHA-256 manifest in `dist/release/` (Windows x86_64 binary, wheel, sdist, checksums).
- Known CI fix included: `release-binaries.yml` now installs `typer` (required by PyInstaller's `--collect-all mcp`), and `ci.yml` Windows wheel reinstall passes the full file path.

## Real issues fixed during this release pass

1. Name collision: `vision-bridge-mcp` was occupied on GitHub/npm by a same-purpose project → renamed everywhere to `visual-evidence-gateway` (distribution, package, CLI, MCP server name, env vars, config dirs, installers, CI, artifacts). Old-name migration note retained in README/CHANGELOG only.
2. `codex exec` on CLI 0.146.1 rejects `--ask-for-approval` → replaced with `-c approval_policy="never"` in the gateway and validation kit.
3. Model identity was never verified on the CLI path → the `codex exec` transcript header is now compared against the configured model; mismatches fail closed.
4. ChatGPT-mode child environment could re-inherit `OPENAI_BASE_URL`/`ANTHROPIC_API_KEY`/`GEMINI_API_KEY` via `pass_env` → now blocked at runtime and at config load.
5. Error/refusal strings could leak local absolute paths → `mask_error()` (tokens + local paths) applied at the refusal boundary.
6. Windows junctions pointing at files crashed `check_path` with `NotADirectoryError` (path resolution) and evaded `exists()`-based detection → lstat-first reparse detection plus fail-closed resolve; regression test added.
7. Injection gate false positives: stative "the token reads …" and Chinese analysis self-descriptions ("已执行两图对比") were flagged → narrowed execution-claim semantics with new tests; adversarial phrasings remain blocked.
8. Compare fixture could never pass: any uncertainty downgraded the result and multi-image retries are skipped → uncertainty now only downgrades on image-readability ambiguity; honest meta caveats pass.
9. Probe validation was fragile to synonym phrasing ("蓝色方形" vs "蓝色方块") → canonical `red circles: N` / `blue squares: N` output requested and parsed first, synonym fallback retained.
10. Installers: SHA-256 was best-effort → now mandatory; setup failure left the binary installed → now rolls back; Windows ARM64 claimed an unpublished asset → explicit failure message.
11. Validation kit: stale partial cache could be served as fresh results → cache cleaned per run; junction negative test added; cache-hit and strict JSON-Schema checks added as P0 gates; audit script now skips runtime result directories; symlink/junction leftovers cleaned.
12. CI: Windows wheel reinstall passed a filename without a path; release build missing `typer`.

## Known limitations (honest boundaries)

- npm `@openai/codex` CLI 0.146.1 on this Windows machine cannot complete **any** stdio MCP tool call (`user cancelled MCP tool call`; reproduced with a 0-second trivial MCP server in clean and stripped environments). The automated host-level gate therefore uses the official MCP SDK client over stdio; the server negotiates the exact protocol version Codex requests (2025-06-18). **The Codex Desktop app (the primary intended host) must still be verified manually after a restart** — listed as an untested boundary.
- `install.sh` (macOS/Linux) is verified by the POSIX-gated integration test and CI on ubuntu; it cannot run natively on this Windows machine.
- Windows ARM64 has no prebuilt binary yet (GitHub-hosted ARM64 Windows runners are unavailable); the installer fails with an explicit message.
- Binaries are unsigned; signature verification is transport-level (HTTPS + SHA-256 manifest).
- Real Luna latency varies by account, region, and service load; numbers above are this machine only.
- ModLens was not run (requires external Antigravity CLI login).
