"""Install and register VisionSieve without breaking pre-v1 installs."""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path
from typing import Optional

from visionsieve_mcp._compat import CONFIG_ENV, LEGACY_CONFIG_ENV, bridge_config_env
from visionsieve_mcp.healthcheck import main as healthcheck_main
from visionsieve_mcp.probe import main as probe_main
from visual_evidence_gateway import setup_cli as legacy

SERVER_NAME = "visionsieve"
OLD_SERVER_NAME = "visual-evidence-gateway"


def default_config_path() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA") or Path.home())
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "visionsieve" / "config.yaml"


def _server_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [str(Path(sys.executable).absolute()), "serve"]

    executable = "visionsieve.exe" if os.name == "nt" else "visionsieve"
    sibling = Path(sys.executable).with_name(executable)
    if sibling.is_file():
        return [str(sibling.absolute()), "serve"]
    discovered = shutil.which("visionsieve")
    if discovered:
        return [str(Path(discovered).absolute()), "serve"]

    old_executable = "visual-evidence-gateway.exe" if os.name == "nt" else "visual-evidence-gateway"
    old_sibling = Path(sys.executable).with_name(old_executable)
    if old_sibling.is_file():
        return [str(old_sibling.absolute()), "serve"]
    old_discovered = shutil.which("visual-evidence-gateway")
    if old_discovered:
        return [str(Path(old_discovered).absolute()), "serve"]
    return ["visionsieve", "serve"]


def _register(codex: str, config_path: Path) -> None:
    listing = legacy._run([codex, "mcp", "list"], timeout=30)
    if listing.returncode == 0:
        folded = listing.stdout.casefold()
        for name in (SERVER_NAME, OLD_SERVER_NAME):
            if name.casefold() in folded:
                legacy._run([codex, "mcp", "remove", name], timeout=30)

    command = _server_command()
    legacy._run(
        [
            codex,
            "mcp",
            "add",
            SERVER_NAME,
            "--env",
            f"{CONFIG_ENV}={config_path}",
            "--env",
            f"{LEGACY_CONFIG_ENV}={config_path}",
            "--",
            *command,
        ],
        timeout=30,
        check=True,
    )
    print(f"MCP registration: {SERVER_NAME} -> {' '.join(command)}")


def main(argv: Optional[list[str]] = None) -> int:
    bridge_config_env()
    selected_default = Path(
        os.environ.get(CONFIG_ENV)
        or os.environ.get(LEGACY_CONFIG_ENV)
        or default_config_path()
    )

    parser = argparse.ArgumentParser(
        description="Configure VisionSieve, verify ChatGPT subscription login, and register it with Codex"
    )
    parser.add_argument("--config", type=Path, default=selected_default, help="Private config path")
    parser.add_argument("--force-config", action="store_true", help="Replace an existing config with secure defaults")
    parser.add_argument("--no-register", action="store_true", help="Do not add the MCP server to Codex")
    parser.add_argument("--skip-probe", action="store_true", help="Skip the real pixel probe")
    parser.add_argument("--non-interactive", action="store_true", help="Fail instead of opening the ChatGPT login flow")
    args = parser.parse_args(argv)

    codex = shutil.which("codex")
    if not codex:
        print("ERROR: Codex CLI was not found. Install the official OpenAI CLI first.", file=sys.stderr)
        return 2

    config_path = args.config.expanduser().absolute()
    try:
        legacy._write_config(config_path, force=args.force_config)
        legacy._ensure_login(codex, non_interactive=args.non_interactive)
        if not args.no_register:
            _register(codex, config_path)
    except (OSError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    os.environ[CONFIG_ENV] = str(config_path)
    os.environ[LEGACY_CONFIG_ENV] = str(config_path)
    health_rc = healthcheck_main(["--config", str(config_path), "--check-connectivity"])
    if health_rc != 0:
        return health_rc
    if not args.skip_probe:
        probe_rc = probe_main(["--config", str(config_path), "--backend", "primary"])
        if probe_rc != 0:
            return probe_rc

    print("VisionSieve MCP is installed and registered.")
    print("Restart the MCP host, then use `vision.inspect` when the task depends on pixels.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
