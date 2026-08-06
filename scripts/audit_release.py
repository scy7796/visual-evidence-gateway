"""Fail a release when personal, secret, runtime, or build debris is present."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "build",
    "dist",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    # Runtime output of pre_release_validation/run_validation.py (contains
    # operator-machine paths by design); it is gitignored and must not fail the
    # source audit.
    "results",
}
TEXT_SUFFIXES = {".py", ".md", ".txt", ".toml", ".yaml", ".yml", ".json", ".ini", ".cfg"}

PERSONAL_PATTERNS = {
    "personal username/path": re.compile(r"(?i)(?:[A-Z]:[/\\]Users[/\\](?!example\b|USERNAME\b)[^/\\\s]+|/Users/(?!example\b|USERNAME\b)[^/\s]+|/home/(?!example\b|USERNAME\b)[^/\s]+)"),
    "private key block": re.compile(r"-----BEGIN\s+[A-Z0-9 ]*PRIVATE\s+KEY-----"),
    "credential-like token": re.compile(r"(?i)\b(?:sk-|ghp_|gho_|glpat-|nvapi-)[A-Za-z0-9_-]{12,}\b"),
    "personal account language": re.compile(r"(?i)\b(?:my|our)\s+chatgpt\s+(?:plus|pro)\b|account\s+quota|remaining\s+quota"),
    "legacy private role/provider marker": re.compile(r"(?i)\b(?:google-antigravity|codex[_ -]?luna)\b"),
    "placeholder GitHub owner": re.compile(r"github\.com/OWNER/"),
}

FORBIDDEN_NAMES = {".env", "config.yaml", "health.json"}


def main() -> int:
    findings: list[str] = []
    for path in ROOT.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        # Runtime output directories of pre_release_validation (results/,
        # results-benchmark/, or any custom --output name) are gitignored and
        # intentionally contain operator-machine paths.
        if any(part.startswith("results") for part in path.parts):
            continue
        if path.is_dir():
            continue
        rel = path.relative_to(ROOT)
        if path.name in FORBIDDEN_NAMES and not (rel.parts and rel.parts[0] == "examples"):
            findings.append(f"runtime/private file committed: {rel}")
        if path.suffix == ".pyc" or "__pycache__" in path.parts:
            findings.append(f"build debris committed: {rel}")
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {"LICENSE", ".gitignore", ".gitattributes", ".editorconfig"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for label, pattern in PERSONAL_PATTERNS.items():
            if rel in {Path("scripts/audit_release.py"), Path("scripts/verify_artifacts.py")}:
                continue
            for match in pattern.finditer(text):
                # Security tests intentionally contain synthetic secret fixtures.
                if label in {"credential-like token", "private key block"} and rel.parts and rel.parts[0] == "tests":
                    continue
                findings.append(f"{label}: {rel}:{text.count(chr(10), 0, match.start()) + 1}")
    if findings:
        print("Release audit failed:")
        for finding in sorted(set(findings)):
            print(f"- {finding}")
        return 1
    print("Release audit passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
