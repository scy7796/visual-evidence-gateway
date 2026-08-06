"""Inspect built wheel/sdist contents before a public release."""
from __future__ import annotations

import argparse
import re
import tarfile
import zipfile
from pathlib import Path

FORBIDDEN_PARTS = {".env", "health.json", "__pycache__", ".pytest_cache", ".ruff_cache", ".venv", "build", "dist"}
FORBIDDEN_TEXT = {
    "personal path": re.compile(r"(?i)(?:[A-Z]:[/\\]Users[/\\](?!example\b|USERNAME\b)[^/\\\s]+|/Users/(?!example\b|USERNAME\b)[^/\s]+|/home/(?!example\b|USERNAME\b)[^/\s]+)"),
    "secret-like token": re.compile(r"(?i)\b(?:sk-|ghp_|gho_|glpat-|nvapi-)[A-Za-z0-9_-]{12,}\b"),
    "private key": re.compile(r"-----BEGIN\s+[A-Z0-9 ]*PRIVATE\s+KEY-----"),
    "legacy private backend": re.compile(r"(?i)\b(?:google-antigravity|codex[_ -]?luna)\b"),
}
TEXT_SUFFIXES = {".py", ".md", ".txt", ".toml", ".yaml", ".yml", ".json", ".ini", ".cfg"}


def _check_name(name: str, findings: list[str]) -> None:
    parts = Path(name).parts
    for part in parts:
        if part in FORBIDDEN_PARTS or part.endswith(".pyc"):
            findings.append(f"forbidden archive member: {name}")
    if Path(name).name == "config.yaml" and "examples" not in parts:
        findings.append(f"runtime config included: {name}")


def _check_text(name: str, data: bytes, findings: list[str]) -> None:
    if Path(name).suffix.lower() not in TEXT_SUFFIXES and Path(name).name not in {"LICENSE", "METADATA", "entry_points.txt"}:
        return
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return
    for label, pattern in FORBIDDEN_TEXT.items():
        if name.endswith("scripts/audit_release.py") or name.endswith("scripts/verify_artifacts.py"):
            continue
        if name.startswith("tests/") or "/tests/" in name:
            if label in {"secret-like token", "private key"}:
                continue
        if pattern.search(text):
            findings.append(f"{label}: {name}")


def inspect_wheel(path: Path, findings: list[str]) -> None:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        for name in names:
            _check_name(name, findings)
            if not name.endswith("/"):
                _check_text(name, archive.read(name), findings)
        required = {
            "visual_evidence_gateway/server.py",
            "visual_evidence_gateway/setup_cli.py",
            "visual_evidence_gateway/router/config.py",
            "visual_evidence_gateway/backends/codex_cli.py",
            "visual_evidence_gateway/prompts/visual_core.txt",
            "visual_evidence_gateway/schemas/vision-result.schema.json",
        }
        missing = sorted(required - set(names))
        findings.extend(f"wheel missing: {name}" for name in missing)
        if not missing:
            config_text = archive.read("visual_evidence_gateway/router/config.py").decode("utf-8", errors="replace")
            cli_text = archive.read("visual_evidence_gateway/backends/codex_cli.py").decode("utf-8", errors="replace")
            for marker in (
                '"via": "codex_cli"',
                '"model": "gpt-5.6-luna"',
                '"auth_mode": "chatgpt"',
                '"min_cli_version": "0.146.0"',
            ):
                if marker not in config_text:
                    findings.append(f"wheel default Luna contract missing: {marker}")
            for marker in (
                'forced_login_method=',
                'features.shell_tool=false',
                'features.multi_agent=false',
                'features.remote_plugin=false',
                'features.skill_mcp_dependency_install=false',
                'web_search="disabled"',
                'history.persistence="none"',
                'model_reasoning_effort=',
                'analytics.enabled=false',
                'otel.metrics_exporter="none"',
                'otel.trace_exporter="none"',
                'otel.log_user_prompt=false',
            ):
                if marker not in cli_text:
                    findings.append(f"wheel Codex hardening missing: {marker}")
        metadata_names = [name for name in names if name.endswith(".dist-info/METADATA")]
        entry_names = [name for name in names if name.endswith(".dist-info/entry_points.txt")]
        if len(metadata_names) != 1:
            findings.append("wheel must contain exactly one METADATA file")
        else:
            metadata = archive.read(metadata_names[0]).decode("utf-8", errors="replace")
            if "Name: visual-evidence-gateway" not in metadata or "Version: 0.5.0" not in metadata:
                findings.append("wheel metadata name/version mismatch")
            if not re.search(r"Requires-Dist: mcp(?:\s*)?\(<3,>=2\.0\)|Requires-Dist: mcp<3,>=2\.0", metadata):
                findings.append("wheel metadata does not pin MCP SDK to >=2.0,<3")
        if len(entry_names) != 1:
            findings.append("wheel must contain console entry points")
        else:
            entries = archive.read(entry_names[0]).decode("utf-8", errors="replace")
            for command in ("visual-evidence-gateway", "visual-evidence-gateway-mcp", "visual-evidence-gateway-healthcheck", "visual-evidence-gateway-probe", "visual-evidence-gateway-setup"):
                if command not in entries:
                    findings.append(f"wheel entry point missing: {command}")


def inspect_sdist(path: Path, findings: list[str]) -> None:
    with tarfile.open(path, "r:gz") as archive:
        members = [member for member in archive.getmembers() if member.isfile()]
        names = [member.name for member in members]
        for member in members:
            _check_name(member.name, findings)
            stream = archive.extractfile(member)
            if stream is not None:
                _check_text(member.name, stream.read(), findings)
        suffixes = ("/pyproject.toml", "/README.md", "/AUDIT_REPORT.md", "/install.sh", "/install.ps1", "/tests/test_security.py", "/tests/test_setup_cli.py", "/pre_release_validation/README.md", "/pre_release_validation/CODEX_TASK.md", "/pre_release_validation/run_validation.py")
        for suffix in suffixes:
            if not any(name.endswith(suffix) for name in names):
                findings.append(f"sdist missing: *{suffix}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dist", nargs="?", type=Path, default=Path("dist"))
    args = parser.parse_args(argv)
    wheels = sorted(args.dist.glob("*.whl"))
    sdists = sorted(args.dist.glob("*.tar.gz"))
    findings: list[str] = []
    if len(wheels) != 1:
        findings.append(f"expected one wheel, found {len(wheels)}")
    if len(sdists) != 1:
        findings.append(f"expected one sdist, found {len(sdists)}")
    for wheel in wheels:
        inspect_wheel(wheel, findings)
    for sdist in sdists:
        inspect_sdist(sdist, findings)
    if findings:
        print("Artifact verification failed:")
        for finding in sorted(set(findings)):
            print(f"- {finding}")
        return 1
    print("Artifact verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
