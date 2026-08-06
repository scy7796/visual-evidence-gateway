"""Unified command-line interface for VisionSieve MCP."""
from __future__ import annotations

import argparse
from typing import Optional

from visionsieve_mcp import __version__


def _dispatch(command: str, args: list[str]) -> int:
    if command == "serve":
        if args:
            raise SystemExit("visionsieve serve does not accept arguments")
        from visionsieve_mcp import server

        return int(server.main() or 0)
    if command == "setup":
        from visionsieve_mcp import setup_cli

        return int(setup_cli.main(args) or 0)
    if command == "healthcheck":
        from visionsieve_mcp import healthcheck

        return int(healthcheck.main(args) or 0)
    if command == "probe":
        from visionsieve_mcp import probe

        return int(probe.main(args) or 0)
    raise ValueError(f"unknown command: {command}")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="visionsieve",
        description="Install, configure, diagnose, or run VisionSieve MCP.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "command",
        nargs="?",
        choices=("serve", "setup", "healthcheck", "probe"),
        help="Action to run. Use `<command> --help` for command-specific options.",
    )
    known, remaining = parser.parse_known_args(argv)
    if known.command is None:
        parser.print_help()
        return 0
    return _dispatch(known.command, remaining)


if __name__ == "__main__":
    raise SystemExit(main())
