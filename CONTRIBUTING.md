# Contributing

Keep the public package free of personal configuration, credentials, private endpoints, machine paths, account state, and generated runtime files. The routing core must remain transport-pluggable. The public default may be provider-specific when that contract is explicit, test-covered, fail-closed, and does not embed credentials or account state; alternative adapters must remain opt-in.

New backend behavior must implement the normalized `BackendResult` contract, fail closed on unresolved or unexpected model identity, recursively mask retained payloads, and include deterministic positive and adversarial tests.

Before a pull request:

```bash
pytest
ruff check .
python scripts/audit_release.py
python -m build
python -m twine check dist/*
python scripts/verify_artifacts.py
```

Do not commit populated `.env` files, real gateway/model identifiers, account or quota screenshots, health state, cache content, absolute local paths, probe output, wheels, source distributions, or virtual environments.
