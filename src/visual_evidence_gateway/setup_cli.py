"""Interactive setup for Visual Evidence Gateway.

The setup command never reads or copies Codex credentials. It only asks the
Codex CLI to report its active authentication mode and registers this MCP
server through Codex's supported CLI interface.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

from visual_evidence_gateway.healthcheck import main as healthcheck_main
from visual_evidence_gateway.probe import main as probe_main
from visual_evidence_gateway.router.config import default_config_path

SERVER_NAME = "visual-evidence-gateway"
CONFIG_ENV = "VISUAL_EVIDENCE_GATEWAY_CONFIG"
_MAX_OUTPUT = 128 * 1024

_DEFAULT_CONFIG = """policy_version: 2
prompt_version: 3
project_root: "{cwd}"
cache_dir: null
health_file: null

backends:
  primary:
    enabled: true
    require_probe: false
    via: codex_cli
    command: codex
    model: "gpt-5.6-luna"
    auth_mode: chatgpt
    min_cli_version: "0.146.0"
    reasoning_effort: medium
    extra_args: [--ephemeral, --ignore-user-config]
    pass_env: []
    allow_cli_default_model: false
  verifier:
    enabled: false
  fallback:
    enabled: false

allowed_roots:
  - "{cwd}"

cache:
  store_raw: false
  store_full_text: false
  expose_local_refs: false
"""


def _run(args: list[str], *, timeout: int = 60, check: bool = False) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        args,
        stdin=None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
        shell=False,
    )
    if len(completed.stdout.encode("utf-8", errors="replace")) > _MAX_OUTPUT:
        completed.stdout = completed.stdout[-_MAX_OUTPUT:]
    if len(completed.stderr.encode("utf-8", errors="replace")) > _MAX_OUTPUT:
        completed.stderr = completed.stderr[-_MAX_OUTPUT:]
    if check and completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()[-1000:]
        raise RuntimeError(f"command failed ({completed.returncode}): {detail}")
    return completed


def _write_config(path: Path, *, force: bool) -> None:
    path = path.expanduser().absolute()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not force:
        print(f"config: keeping existing file at {path}")
        return
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(_DEFAULT_CONFIG, encoding="utf-8", newline="\n")
    try:
        os.chmod(temporary, 0o600)
    except OSError:
        pass
    os.replace(temporary, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    print(f"config: wrote {path}")


def _chatgpt_login_confirmed(codex: str) -> bool:
    result = _run([codex, "login", "status"], timeout=30)
    text = f"{result.stdout}\n{result.stderr}".casefold()
    return result.returncode == 0 and "logged in using chatgpt" in text


def _ensure_login(codex: str, *, non_interactive: bool) -> None:
    if _chatgpt_login_confirmed(codex):
        print("Codex authentication: ChatGPT subscription login confirmed")
        return
    if non_interactive:
        raise RuntimeError("Codex is not signed in with ChatGPT; run `codex login` and retry")
    print("Codex is not signed in with ChatGPT. Opening the official login flow...")
    login = subprocess.run([codex, "login"], check=False, shell=False)
    if login.returncode != 0 or not _chatgpt_login_confirmed(codex):
        raise RuntimeError("ChatGPT subscription login was not confirmed")
    print("Codex authentication: ChatGPT subscription login confirmed")


def _server_command() -> list[str]:
    """Return an absolute, shell-free command for the MCP server.

    Standalone builds register the same executable with the ``serve``
    subcommand. Python installations prefer the unified sibling launcher and
    retain the legacy server entry point as a compatibility fallback.
    """
    if getattr(sys, "frozen", False):
        return [str(Path(sys.executable).absolute()), "serve"]

    unified_name = "visual-evidence-gateway.exe" if os.name == "nt" else "visual-evidence-gateway"
    unified = Path(sys.executable).with_name(unified_name)
    if unified.is_file():
        return [str(unified.absolute()), "serve"]
    discovered = shutil.which("visual-evidence-gateway")
    if discovered:
        return [str(Path(discovered).absolute()), "serve"]

    legacy_name = "visual-evidence-gateway-mcp.exe" if os.name == "nt" else "visual-evidence-gateway-mcp"
    legacy = Path(sys.executable).with_name(legacy_name)
    if legacy.is_file():
        return [str(legacy.absolute())]
    discovered_legacy = shutil.which("visual-evidence-gateway-mcp")
    return [str(Path(discovered_legacy).absolute())] if discovered_legacy else ["visual-evidence-gateway-mcp"]


def _register(codex: str, config_path: Path) -> None:
    listing = _run([codex, "mcp", "list"], timeout=30)
    if listing.returncode == 0 and SERVER_NAME.casefold() in listing.stdout.casefold():
        _run([codex, "mcp", "remove", SERVER_NAME], timeout=30)
    command = _server_command()
    _run(
        [
            codex,
            "mcp",
            "add",
            SERVER_NAME,
            "--env",
            f"{CONFIG_ENV}={config_path}",
            "--",
            *command,
        ],
        timeout=30,
        check=True,
    )
    print(f"MCP registration: {SERVER_NAME} -> {' '.join(command)}")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Configure Visual Evidence Gateway, verify ChatGPT subscription login, and register it with Codex"
    )
    parser.add_argument("--config", type=Path, default=default_config_path(), help="Private config path")
    parser.add_argument("--force-config", action="store_true", help="Replace an existing config with secure defaults")
    parser.add_argument("--no-register", action="store_true", help="Do not add the MCP server to Codex")
    parser.add_argument("--skip-probe", action="store_true", help="Skip the real pixel probe")
    parser.add_argument("--non-interactive", action="store_true", help="Fail instead of opening the ChatGPT login flow")
    args = parser.parse_args(argv)

    codex = shutil.which("codex")
    if not codex:
        print("ERROR: Codex CLI was not found. Install it from the official OpenAI installer first.", file=sys.stderr)
        return 2

    config_path = args.config.expanduser().absolute()
    try:
        _write_config(config_path, force=args.force_config)
        _ensure_login(codex, non_interactive=args.non_interactive)
        if not args.no_register:
            _register(codex, config_path)
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    os.environ[CONFIG_ENV] = str(config_path)
    health_rc = healthcheck_main(["--config", str(config_path), "--check-connectivity"])
    if health_rc != 0:
        return health_rc
    if not args.skip_probe:
        probe_rc = probe_main(["--config", str(config_path), "--backend", "primary"])
        if probe_rc != 0:
            return probe_rc

    print("Visual Evidence Gateway is installed and registered.")
    print("Restart Codex/ChatGPT desktop, then use the `vision.inspect` MCP tool when pixels matter.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
