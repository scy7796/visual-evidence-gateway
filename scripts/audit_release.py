"""Fail a release when personal, secret, runtime, or build debris is present."""
from __future__ import annotations

import re
import subprocess
from collections.abc import Iterable
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
}
TEXT_SUFFIXES = {".py", ".md", ".txt", ".toml", ".yaml", ".yml", ".json", ".ini", ".cfg"}

PERSONAL_PATTERNS = {
    "personal username/path": re.compile(
        r"(?i)(?:[A-Z]:[/\\]Users[/\\](?!example\b|USERNAME\b)[^/\\\s]+|"
        r"/Users/(?!example\b|USERNAME\b)[^/\s]+|"
        r"/home/(?!example\b|USERNAME\b)[^/\s]+)"
    ),
    "private key block": re.compile(r"-----BEGIN\s+[A-Z0-9 ]*PRIVATE\s+KEY-----"),
    "credential-like token": re.compile(r"(?i)\b(?:sk-|ghp_|gho_|glpat-|nvapi-)[A-Za-z0-9_-]{12,}\b"),
    "personal account language": re.compile(
        r"(?i)\b(?:my|our)\s+chatgpt\s+(?:plus|pro)\b|account\s+quota|remaining\s+quota"
    ),
    "legacy private role/provider marker": re.compile(r"(?i)\b(?:google-antigravity|codex[_ -]?luna)\b"),
    "placeholder GitHub owner": re.compile(r"github\.com/OWNER/"),
}

FORBIDDEN_NAMES = {".env", "config.yaml", "health.json"}


def _tracked_files() -> list[Path] | None:
    """Return Git-tracked files, or None when Git metadata is unavailable.

    Auditing tracked files prevents local, ignored validation output from breaking a
    developer run while still catching any result file that was force-added to Git.
    Source archives without a .git directory use the filesystem fallback below.
    """

    try:
        completed = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        return None

    paths: list[Path] = []
    for raw in completed.stdout.split(b"\0"):
        if not raw:
            continue
        rel = Path(raw.decode("utf-8", errors="surrogateescape"))
        path = ROOT / rel
        if path.is_file():
            paths.append(path)
    return paths


def _candidate_files() -> Iterable[Path]:
    tracked = _tracked_files()
    if tracked is not None:
        yield from tracked
        return
    yield from (path for path in ROOT.rglob("*") if path.is_file())


def main() -> int:
    findings: list[str] = []
    for path in _candidate_files():
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        rel = path.relative_to(ROOT)

        if (
            len(rel.parts) >= 2
            and rel.parts[0] == "pre_release_validation"
            and rel.parts[1].startswith("results")
        ):
            findings.append(f"runtime validation output committed: {rel}")

        if path.name in FORBIDDEN_NAMES and not (rel.parts and rel.parts[0] == "examples"):
            findings.append(f"runtime/private file committed: {rel}")
        if path.suffix == ".pyc" or "__pycache__" in path.parts:
            findings.append(f"build debris committed: {rel}")
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {
            "LICENSE",
            ".gitignore",
            ".gitattributes",
            ".editorconfig",
        }:
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
