"""VisionSieve MCP server entry point."""
from __future__ import annotations

from visionsieve_mcp._compat import bridge_config_env


def main() -> int:
    bridge_config_env()
    from visual_evidence_gateway.server import main as core_main

    return int(core_main() or 0)


if __name__ == "__main__":
    raise SystemExit(main())
