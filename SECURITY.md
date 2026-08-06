# Security policy

Use a private GitHub security advisory for vulnerability reports after the repository is created. Do not include credentials, private images, authentication files, private endpoints, or account usage data in public issues.

Supported line: `0.5.x`.

Reports should include the affected version, threat scenario, minimal reproduction, security impact, and suggested mitigation. Rotate any credential accidentally exposed during testing before submitting a report.

The default backend deliberately reuses local Codex ChatGPT authentication without copying it into this repository. Vulnerabilities that expose the Codex credential store, permit API-billing fallback despite `auth_mode: chatgpt`, escape configured path controls, or return unvalidated image instructions should be treated as security issues.
