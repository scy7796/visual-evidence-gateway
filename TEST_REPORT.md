# Visual Evidence Gateway v0.5.0 — test report

Status: local code and packaging checks passed; cross-platform standalone binaries and real Luna access remain release-environment gates.

## Executed locally

- `pytest`: 201 tests collected; 200 passed and 1 official MCP SDK integration test skipped because the offline build environment does not provide MCP 2.x.
- POSIX installer integration: passed. A local fake GitHub Release was downloaded, SHA-256 verified, installed as one executable, and invoked as `setup --skip-probe` without Python or pip bootstrap.
- Python compilation: passed for `src`, `tests`, and `scripts`.
- Release-sensitive-content audit: passed.
- sdist and wheel: built successfully through the setuptools PEP 517 backend.
- Clean no-dependency wheel smoke test: `visual-evidence-gateway --version` returned `0.5.0`, and all five console entry points were present.

## Not claimed as locally passed

- PyInstaller executable construction, because PyInstaller is unavailable in the offline build environment.
- Windows PowerShell execution, because PowerShell is unavailable in the build container.
- GitHub Actions release upload.
- Real ChatGPT subscription login, Luna model availability, real pixel latency, and host-level MCP calls.

These items are explicitly handled by `.github/workflows/release-binaries.yml` and the existing pre-release validation package.
